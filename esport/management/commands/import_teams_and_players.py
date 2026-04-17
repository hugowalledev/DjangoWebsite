import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.files.base import ContentFile
from django.utils.text import slugify
from esport.models import Player, Roster, RosterPlayer, Team, Tournament


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_team_region_and_slug(link, headers):
    res = requests.get(link, headers=headers)
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


def save_team_logo(cmd, team, team_name, url, dark):
    if not url:
        return
    filename = f"{slugify(team_name)}{'_dark' if dark else ''}.png"
    response = requests.get(url)
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
        players.append((nickname, nationality, role, is_starter))
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

        players.append((nickname, nationality, role, is_starter))
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

    # Main roster is always tab 1
    main_div = content.find('div', attrs={'data-toggle-area-content': '1'})

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
    help = "Imports Teams and Players from tournaments via Liquipedia (supports 2025 & 2026 HTML layouts)"

    def handle(self, *args, **options):
        headers = {'User-Agent': 'Mozilla/5.0'}

        tournaments = Tournament.objects.filter(
            date_ended__gte=date.today(),
            date_started__lte=date.today() + timedelta(days=7),
        ).order_by('date_started')

        for tournament in tournaments:
            url = tournament.liquipedia_url

            try:
                res = requests.get(url, headers=headers)
                res.raise_for_status()
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Request failed for {url}: {e}"))
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            year = tournament.year
            self.stdout.write(self.style.NOTICE(f"Tournament: {tournament.name}"))

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
                    team_region, team_slug = get_team_region_and_slug(team_link, headers)
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
                    existing_players = Player.objects.filter(name__in=players_to_import)
                    existing_rps = RosterPlayer.objects.filter(roster=obj_roster)
                    player_map = {p.name: p for p in existing_players}
                    rosterplayer_map = {(rp.player.name, rp.roster_id): rp for rp in existing_rps}

                    for nickname, nationality, role, is_starter in players_data:
                        player = player_map.get(nickname)
                        rp_key = (nickname, obj_roster.id)

                        if not player:
                            player, _ = Player.objects.update_or_create(
                                name=nickname,
                                defaults={'country': nationality, 'slug': slugify(nickname)},
                            )
                            player_map[nickname] = player

                        if rp_key in rosterplayer_map:
                            self.stdout.write(self.style.NOTICE(f"  Exists: {nickname}"))
                        else:
                            RosterPlayer.objects.create(
                                roster=obj_roster,
                                player=player,
                                is_starter=is_starter,
                                role=role,
                            )
                            rosterplayer_map[rp_key] = True
                            self.stdout.write(self.style.SUCCESS(
                                f"  Created: {nickname} | {role} | {obj_roster.team.name} @ {tournament.name}"
                            ))