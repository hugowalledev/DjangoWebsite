import time
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.files.base import ContentFile
from django.utils.text import slugify
from esport.models import Player, Roster, RosterPlayer, Team, Tournament

# ---------------------------------------------------------------------------
# Liquipedia rate-limiting
# Liquipedia asks for a descriptive User-Agent and recommends ~2 req/s max.
# We use a conservative 2-second delay between every request, with automatic
# back-off (up to 3 retries) when the server returns 429.
# ---------------------------------------------------------------------------
HEADERS = {
    'User-Agent': 'FantasyLoLBot/1.0 (personal project; contact via github)',
    'Accept-Encoding': 'gzip',
}
REQUEST_DELAY   = 2.0   # seconds between every request
RETRY_DELAYS    = [10, 30, 60]  # back-off schedule on 429


def lp_get(url):
    """
    GET a Liquipedia URL with rate-limiting and automatic 429 retry.
    Raises requests.RequestException on permanent failure.
    """
    # Detect redlink URLs immediately — these are Liquipedia "page doesn't exist"
    # edit links that will always 403. No point hitting the server at all.
    if 'redlink=1' in url or 'action=edit' in url:
        raise requests.RequestException(f"Skipping redlink/edit URL: {url}")

    for attempt, backoff in enumerate([0] + RETRY_DELAYS):
        if backoff:
            time.sleep(backoff)
        else:
            time.sleep(REQUEST_DELAY)
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            if res.status_code == 429:
                if attempt < len(RETRY_DELAYS):
                    continue          # retry after backoff
                res.raise_for_status()  # give up
            if res.status_code in (403, 404):
                # Permanent errors — no point retrying
                res.raise_for_status()
            res.raise_for_status()
            return res
        except requests.RequestException:
            if attempt == len(RETRY_DELAYS):
                raise
    # should never reach here
    raise requests.RequestException(f"All retries exhausted for {url}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_team_region_and_slug(link):
    try:
        res = lp_get(link)
    except requests.RequestException:
        return "Unknown", None
    soup = BeautifulSoup(res.text, 'html.parser')

    div = soup.find(text="Region:")
    if not div:
        div = soup.find(text="Location:")
    slug = soup.find(text="Abbreviation:")
    if not slug:
        if not div:
            return "Unknown", None
        return div.findNext('a')['title'], None
    return div.findNext('a')['title'], slugify(slug.findNext('div').get_text(strip=True))



def get_player_aliases(player_link):
    """
    Fetch a player's Liquipedia page and return their alternate IDs as a list.
    Looks for the 'Alternate IDs:' row in the player infobox.
    Returns an empty list if the field is absent or the request fails.
    """
    try:
        res = lp_get(player_link)
    except requests.RequestException:
        return []

    soup = BeautifulSoup(res.text, 'html.parser')

    # Find the infobox description cell labelled exactly "Alternate IDs:"
    label = soup.find('div', class_='infobox-description', string='Alternate IDs:')
    if not label:
        return []

    value_div = label.find_next_sibling('div')
    if not value_div:
        return []

    raw = value_div.get_text(separator=',', strip=True)
    # Split on commas, strip whitespace, deduplicate while preserving order
    seen = set()
    aliases = []
    for alias in raw.split(','):
        alias = alias.strip()
        if alias and alias not in seen:
            seen.add(alias)
            aliases.append(alias)
    return aliases

def save_team_logo(cmd, team, team_name, url, dark):
    if not url:
        return
    filename = f"{slugify(team_name)}{'_dark' if dark else ''}.png"
    response = lp_get(url)
    if response.status_code == 200:
        if dark:
            team.logo_dark.save(filename, ContentFile(response.content), save=True)
            cmd.stdout.write(cmd.style.NOTICE(f"[DEBUG] New logo saved: {team.logo_dark.name}"))
        else:
            team.logo.save(filename, ContentFile(response.content), save=True)
            cmd.stdout.write(cmd.style.NOTICE(f"[DEBUG] New logo saved: {team.logo.name}"))
    else:
        cmd.stdout.write(cmd.style.NOTICE(f"[DEBUG] Could not fetch logo: {url}"))


# ---------------------------------------------------------------------------
# 2025 format  (div.teamcard  /  wikitable rows)
# ---------------------------------------------------------------------------

def parse_player_table_2025(table, is_starter, already_seen):
    """Parse a 2025-style wikitable into player tuples."""
    players = []
    if not table:
        return players
    for row in table.find_all('tr'):
        th = row.find('th')
        td = row.find('td')
        if not th or not td or td.has_attr('colspan'):
            continue
        img = th.find('img')
        role = img['alt'] if img else ""
        a_tags = td.find_all('a', title=True)
        nationality = td.find('img')['alt'] if td.find('img') else ""
        nickname = a_tags[-1].get_text(strip=True) if a_tags else td.get_text(strip=True)
        if not nickname or not role or nickname == "TBD":
            continue
        if nickname in already_seen:
            continue
        # Build the player's Liquipedia link from the last <a> tag with a title
        player_link = None
        if a_tags:
            href = a_tags[-1].get('href', '')
            if href and not href.startswith('http'):
                player_link = f"https://liquipedia.net{href}"
        players.append((nickname, nationality, role, is_starter, player_link))
        already_seen.add(nickname)
    return players


def extract_card_info_2025(card):
    """
    Extract (team_name, team_link, logo_url, logo_dark_url,
             main_table, sub_table) from a 2025-style div.teamcard.
    Returns None on failure.
    """
    center = card.find("center")
    if not center:
        return None
    team_link_tag = center.find("a")
    if not team_link_tag:
        return None

    team_name = team_link_tag.get_text(strip=True)
    team_link = f"https://liquipedia.net{team_link_tag['href']}"

    teamcard_inner = card.find('div', class_='teamcard-inner')
    if not teamcard_inner:
        return None

    tables = teamcard_inner.find_all('table')
    if not tables:
        return None

    # Last table holds the logos
    logo_imgs = tables[-1].find_all('img')
    logo_url = f"https://liquipedia.net{logo_imgs[0]['src']}" if len(logo_imgs) > 0 else None
    logo_dark_url = f"https://liquipedia.net{logo_imgs[1]['src']}" if len(logo_imgs) > 1 else logo_url

    # Main roster is always data-toggle-area-content="1"
    main_table = teamcard_inner.find('table', attrs={"data-toggle-area-content": "1"})

    # Sub table detection: look for a toggle button that isn't "Staff"
    sub_table = None
    if len(tables) >= 4 and main_table:
        tr_tags = main_table.find_all('tr')
        for tr in reversed(tr_tags):
            spans = tr.find_all('span', attrs={'data-toggle-area-btn': True})
            if spans:
                target = next(
                    (s for s in spans if s.get_text(strip=True) not in ("Staff", "")),
                    None
                )
                if target:
                    area = target.get('data-toggle-area-btn')
                    if area and area != "1":
                        sub_table = teamcard_inner.find(
                            'table', attrs={"data-toggle-area-content": area}
                        )
                break

    return team_name, team_link, logo_url, logo_dark_url, main_table, sub_table


# ---------------------------------------------------------------------------
# 2026 format  (div.team-participant-card  /  div.team-participant-card__member)
# ---------------------------------------------------------------------------

def parse_player_members_2026(content_div, is_starter, already_seen):
    """Parse a 2026-style toggle-area-content div into player tuples."""
    players = []
    if not content_div:
        return players
    for member in content_div.find_all('div', class_='team-participant-card__member'):
        role_div = member.find('div', class_='team-participant-card__member-role-left')
        name_div = member.find('div', class_='team-participant-card__member-name')
        if not role_div or not name_div:
            continue

        role_img = role_div.find('img')
        role = role_img['alt'] if role_img else ""

        flag_span = name_div.find('span', class_='flag')
        flag_img = flag_span.find('img') if flag_span else None
        nationality = flag_img['alt'] if flag_img else ""

        name_span = name_div.find('span', class_='name')
        a_tag = name_span.find('a') if name_span else None
        nickname = a_tag.get_text(strip=True) if a_tag else ""

        if not nickname or not role or nickname == "TBD":
            continue
        if nickname in already_seen:
            continue

        # Build the player's Liquipedia link from the <a> tag in the name span
        player_link = None
        if a_tag:
            href = a_tag.get('href', '')
            if href and not href.startswith('http'):
                player_link = f"https://liquipedia.net{href}"
        players.append((nickname, nationality, role, is_starter, player_link))
        already_seen.add(nickname)
    return players


def extract_card_info_2026(card):
    """
    Extract (team_name, team_link, logo_url, logo_dark_url,
             main_content_div, sub_content_div) from a 2026-style
    div.team-participant-card. Returns None on failure.
    """
    header = card.find('div', class_='team-participant-card__header')
    if not header:
        return None

    name_span = header.find('span', class_='name')
    team_link_tag = name_span.find('a') if name_span else None
    if not team_link_tag:
        return None

    team_name = team_link_tag.get_text(strip=True)
    team_link = f"https://liquipedia.net{team_link_tag['href']}"

    # Logos live in the header
    light_span = header.find('span', class_='team-template-lightmode')
    dark_span = header.find('span', class_='team-template-darkmode')
    light_img = light_span.find('img') if light_span else None
    dark_img = dark_span.find('img') if dark_span else None

    if light_img:
        logo_url = f"https://liquipedia.net{light_img['src']}"
    else:
        # allmode logo used when there is no separate light/dark
        single = header.find('span', class_='team-template-image-icon')
        single_img = single.find('img') if single else None
        logo_url = f"https://liquipedia.net{single_img['src']}" if single_img else None

    if dark_img:
        logo_dark_url = f"https://liquipedia.net{dark_img['src']}"
    else:
        logo_dark_url = logo_url  # fall back to light

    # Content area
    content = card.find('div', class_='team-participant-card__content')
    if not content:
        return None

    # Detect pill labels to understand the tab layout
    pills = content.find_all('div', class_='switch-pill-option')
    pill_labels = [p.get_text(strip=True) for p in pills]
    has_subs = "Subs" in pill_labels

    # Main roster is always tab 1 when tabs exist …
    main_div = content.find('div', attrs={'data-toggle-area-content': '1'})

    if main_div is None:
        # No toggle tabs at all — the roster sits directly inside the content
        # div (common on older GPL-style 2026 pages). Use the content div
        # itself as the main_div so parse_player_members_2026 can find the
        # team-participant-card__member elements inside it.
        main_div = content

    # Subs tab is tab 2 when it exists; otherwise tab 2 is Staff → no subs
    sub_div = None
    if has_subs:
        sub_div = content.find('div', attrs={'data-toggle-area-content': '2'})

    return team_name, team_link, logo_url, logo_dark_url, main_div, sub_div


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(soup):
    """
    Return '2026' if the new participant-card layout is present,
    otherwise '2025' (classic teamcard layout).
    """
    if soup.find('div', class_='team-participant-card'):
        return '2026'
    return '2025'


def collect_cards(soup, part_h2, fmt):
    """
    Walk siblings after the section heading and return a flat list of card
    elements matching the detected format.

    In 2026 Liquipedia pages the <h2> is wrapped inside a
    div.mw-heading.mw-heading2 element, so we must walk the *wrapper's*
    siblings rather than the bare <h2>'s siblings (which has none).
    In 2025 pages the <h2> is a direct child of the content div, so we
    walk its siblings as before.
    """
    # Determine the correct starting node to walk siblings from.
    # If the h2 is inside a .mw-heading wrapper, use that wrapper.
    wrapper = part_h2.parent
    if wrapper and 'mw-heading' in wrapper.get('class', []):
        start = wrapper
    else:
        start = part_h2

    cards = []
    sibling = start
    while True:
        sibling = sibling.find_next_sibling()
        if sibling is None:
            break
        # Stop at the next section heading (bare h2 or wrapped h2)
        if sibling.name == 'h2':
            break
        if sibling.name == 'div' and 'mw-heading2' in sibling.get('class', []):
            break

        if fmt == '2026':
            cards.extend(sibling.find_all('div', class_='team-participant-card', recursive=True))
        else:
            cards.extend(sibling.find_all('div', class_='teamcard', recursive=True))
    return cards


# ---------------------------------------------------------------------------
# Django management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Imports Teams and Players from Liquipedia.\n\n"
        "Default (no flags): imports tournaments that are currently running or "
        "start within the next 7 days.\n"
        "  --year YYYY   : import all tournaments for a specific year\n"
        "  --all         : import every tournament in the DB (use with caution)\n"
        "  --pause N     : seconds to pause between tournaments (default 5)"
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--year',
            type=int,
            metavar='YYYY',
            help='Import all tournaments whose date_started falls in this year.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            help='Import every tournament in the database.',
        )
        parser.add_argument(
            '--pause',
            type=float,
            default=5.0,
            metavar='N',
            help='Seconds to pause between tournaments (default: 5). '
                 'Increase this if you keep hitting 429 errors.',
        )

    def handle(self, *args, **options):
        # lp_get() handles per-request rate-limiting and retries automatically.
        # The --pause flag adds an extra delay *between tournaments* so that
        # the burst of team-page + player-page requests for one tournament can
        # settle before we start the next one.
        inter_tournament_pause = options['pause']

        if options.get('all'):
            tournaments = Tournament.objects.all().order_by('date_started')
            self.stdout.write(self.style.WARNING(
                f"Importing ALL {tournaments.count()} tournaments. "
                f"This will take a very long time."
            ))
        elif options.get('year'):
            year = options['year']
            tournaments = Tournament.objects.filter(
                date_started__year=year,
            ).order_by('date_started')
            self.stdout.write(self.style.NOTICE(
                f"Importing {tournaments.count()} tournaments for {year}."
            ))
        else:
            tournaments = Tournament.objects.filter(
                date_ended__gte=date.today(),
                date_started__lte=date.today() + timedelta(days=7),
            ).order_by('date_started')
            self.stdout.write(self.style.NOTICE(
                f"Importing {tournaments.count()} currently active/upcoming tournaments."
            ))

        total = tournaments.count()
        for idx, tournament in enumerate(tournaments, start=1):
            self.stdout.write(self.style.NOTICE(
                f"[{idx}/{total}] Tournament: {tournament.name}"
            ))
            url = tournament.liquipedia_url

            try:
                res = lp_get(url)
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Request failed for {url}: {e}"))
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            year = tournament.year

            # ------------------------------------------------------------------
            # Locate the "Participating Teams / Participants" section
            # ------------------------------------------------------------------
            part_h2 = None
            for h2 in soup.find_all('h2'):
                text = h2.get_text()
                if any(kw in text for kw in ('Participating Teams', 'Participants', 'Participating Players')):
                    part_h2 = h2
                    break

            if not part_h2:
                self.stdout.write(self.style.WARNING("Participating Teams section not found, skipping."))
                continue

            # ------------------------------------------------------------------
            # Detect which HTML format this page uses
            # ------------------------------------------------------------------
            fmt = detect_format(soup)
            self.stdout.write(self.style.NOTICE(f"  → Detected layout format: {fmt}"))

            cards = collect_cards(soup, part_h2, fmt)
            if not cards:
                self.stdout.write(self.style.WARNING("  No team cards found, skipping."))
                continue

            # ------------------------------------------------------------------
            # Process each team card
            # ------------------------------------------------------------------
            for card in cards:
                with transaction.atomic():
                    # --- Extract card data depending on format ---
                    if fmt == '2026':
                        result = extract_card_info_2026(card)
                    else:
                        result = extract_card_info_2025(card)

                    if result is None:
                        self.stdout.write(self.style.WARNING("  Skipping malformed card."))
                        continue

                    team_name, team_link, logo_url, logo_dark_url, main_content, sub_content = result

                    # --- Region & slug from the team's own Liquipedia page ---
                    team_region, team_slug = get_team_region_and_slug(team_link)
                    if not team_region or team_region == "Unknown":
                        self.stdout.write(self.style.WARNING(f"  Region not found for {team_name}, skipping."))
                        continue
                    if not team_slug:
                        team_slug = slugify(team_name)

                    # --- Upsert Team ---
                    try:
                        obj_team, created_team = Team.objects.update_or_create(
                            name=team_name,
                            defaults={'region': team_region, 'slug': team_slug},
                        )
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"  DB error for team {team_name}: {e}"))
                        continue

                    save_team_logo(self, obj_team, team_name, logo_url, False)
                    save_team_logo(self, obj_team, team_name, logo_dark_url, True)

                    # --- Upsert Roster ---
                    obj_roster, _ = Roster.objects.get_or_create(
                        team=obj_team,
                        tournament=tournament,
                        year=year,
                    )

                    # --- Parse players ---
                    players_to_import = set()
                    players_data = []

                    if fmt == '2026':
                        players_data += parse_player_members_2026(main_content, True, players_to_import)
                        players_data += parse_player_members_2026(sub_content, False, players_to_import)
                    else:
                        players_data += parse_player_table_2025(main_content, True, players_to_import)
                        players_data += parse_player_table_2025(sub_content, False, players_to_import)

                    # --- Bulk-fetch existing DB objects for efficiency ---
                    # Build a map of name -> Player for all known players
                    # (both by current name and by any stored alias)
                    existing_players = Player.objects.filter(name__in=players_to_import)
                    existing_rps = RosterPlayer.objects.filter(roster=obj_roster)
                    player_map = {p.name: p for p in existing_players}
                    # Key by (player_id, roster_id) — stable across renames
                    rosterplayer_map = {(rp.player_id, rp.roster_id) for rp in existing_rps}

                    for nickname, nationality, role, is_starter, player_link in players_data:
                        # --- 1. Try to find an existing player ---
                        player = player_map.get(nickname)

                        if not player:
                            # Not found by current name — fetch aliases first so we can
                            # check whether this nickname is a known alias of an existing player.
                            aliases = []
                            if player_link:
                                aliases = get_player_aliases(player_link)

                            # Build the full set of names to search: current + all aliases
                            all_names = {nickname} | set(aliases)

                            # Check if any of those names match a player already in the DB
                            player = Player.objects.filter(name__in=all_names).first()

                            if not player:
                                # Also search inside aliases fields (handles the reverse case:
                                # player stored as "nuclearint" with no alias yet, now appearing
                                # as "nuc" whose Liquipedia page lists "Nuclearint" as an alias)
                                for alias in aliases:
                                    player = Player.objects.filter(aliases__icontains=alias).first()
                                    if player:
                                        self.stdout.write(self.style.NOTICE(
                                            f"  Matched {nickname} to existing player "
                                            f"'{player.name}' via alias '{alias}'"
                                        ))
                                        break

                            if not player:
                                # Last resort: look up by slug (the unique DB constraint).
                                # Catches players stored under a different name/capitalisation
                                # that would still produce the same slug.
                                player = Player.objects.filter(slug=slugify(nickname)).first()
                                if player:
                                    self.stdout.write(self.style.NOTICE(
                                        f"  Matched {nickname} to existing player "
                                        f"'{player.name}' via slug"
                                    ))

                            if player:
                                # Found via alias or slug — update name to the current
                                # in-game ID and refresh aliases
                                changed = False
                                if player.name != nickname:
                                    new_slug = slugify(nickname)
                                    # Check if the target slug is already taken by a
                                    # *different* player. This happens when e.g. the DB
                                    # has both "GoDlike" (found via alias) and a separate
                                    # "ackerman" record. In that case skip the rename —
                                    # the existing "ackerman" record is the right one.
                                    slug_conflict = Player.objects.filter(
                                        slug=new_slug
                                    ).exclude(pk=player.pk).first()
                                    if slug_conflict:
                                        self.stdout.write(self.style.NOTICE(
                                            f"  Skipping rename '{player.name}' → '{nickname}': "
                                            f"slug already taken by '{slug_conflict.name}' "
                                            f"(pk={slug_conflict.pk}). Using existing record."
                                        ))
                                        # Use the player that already owns the target slug
                                        player = slug_conflict
                                    else:
                                        self.stdout.write(self.style.NOTICE(
                                            f"  Renaming player '{player.name}' → '{nickname}'"
                                        ))
                                        player.name = nickname
                                        player.slug = new_slug
                                        changed = True
                                if aliases and player.aliases != ', '.join(aliases):
                                    player.aliases = ', '.join(aliases)
                                    changed = True
                                if changed:
                                    player.save()
                                player_map[nickname] = player

                            else:
                                # Genuinely new player — create them
                                if aliases:
                                    self.stdout.write(self.style.NOTICE(
                                        f"  Aliases for {nickname}: {', '.join(aliases)}"
                                    ))
                                # Use get_or_create on slug as the unique key to avoid
                                # IntegrityError on race conditions or repeated imports
                                player, created = Player.objects.get_or_create(
                                    slug=slugify(nickname),
                                    defaults={
                                        'name': nickname,
                                        'country': nationality,
                                        'aliases': ', '.join(aliases),
                                    },
                                )
                                if not created:
                                    # Slug already existed (shouldn't happen after the slug
                                    # lookup above, but be safe) — just update what we can
                                    update_fields = []
                                    if aliases and player.aliases != ', '.join(aliases):
                                        player.aliases = ', '.join(aliases)
                                        update_fields.append('aliases')
                                    if update_fields:
                                        player.save(update_fields=update_fields)
                                player_map[nickname] = player

                        else:
                            # Player found by name — update aliases if the field is still empty
                            if player_link and not getattr(player, 'aliases', None):
                                aliases = get_player_aliases(player_link)
                                if aliases:
                                    player.aliases = ', '.join(aliases)
                                    player.save(update_fields=['aliases'])
                                    self.stdout.write(self.style.NOTICE(
                                        f"  Updated aliases for {nickname}: {', '.join(aliases)}"
                                    ))

                        rp_key = (player.id, obj_roster.id)
                        if rp_key in rosterplayer_map:
                            self.stdout.write(self.style.NOTICE(f"  Exists: {nickname}"))
                        else:
                            RosterPlayer.objects.get_or_create(
                                roster=obj_roster,
                                player=player,
                                defaults={
                                    'is_starter': is_starter,
                                    'role': role,
                                },
                            )
                            rosterplayer_map.add(rp_key)
                            self.stdout.write(self.style.SUCCESS(
                                f"  Created: {nickname} | {role} | {obj_roster.team.name} @ {tournament.name}"
                            ))

            # Pause between tournaments to let Liquipedia breathe
            if idx < total and inter_tournament_pause > 0:
                self.stdout.write(self.style.NOTICE(
                    f"  Pausing {inter_tournament_pause}s before next tournament..."
                ))
                time.sleep(inter_tournament_pause)