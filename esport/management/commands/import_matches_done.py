import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta, time as dt_time
import difflib
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.db.models import Q
from esport.models import Champion, Game, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Tournament
from esport.utils import normalize_team_name
import unicodedata
from urllib.parse import quote


# Known Liquipedia league name → gol.gg league name mappings
LEAGUE_NAME_MAP = {
    'lcs/europe':              'EU LCS',
    'lcs/north_america':       'NA LCS',
    'lec':                     'LEC',
    'lcs':                     'LCS',
    'lck':                     'LCK',
    'lpl':                     'LPL',
    'lms':                     'LMS',
    'lcp':                     'LCP',
    'worlds':                  'World Championship',
    'world_championship':      'World Championship',
    'mid-season_invitational': 'Mid-Season Invitational',
    'msi':                     'Mid-Season Invitational',
    'intel_extreme_masters':   'IEM',
    'garena_premier_league':   'GPL',
    'champions':               'OGN Champions',
}

SEASON_MAP = {
    'spring':  'Spring',
    'summer':  'Summer',
    'winter':  'Winter',
    'fall':    'Fall',
    'split_1': 'Split 1',
    'split_2': 'Split 2',
    'split_3': 'Split 3',
}


def gol_url_from_name(gol_name):
    return f"https://gol.gg/tournament/tournament-matchlist/{quote(gol_name)}/"


def resolve_gol_url(session, tournament_name, year):
    """
    Find the correct gol.gg matchlist URL for a tournament.

    gol.gg naming conventions:
      - Up to 2024:  season before year  →  "EU LCS Spring 2014"
      - 2025+:       year before season  →  "LEC 2025 Winter"

    Strategy:
      1. Parse the Liquipedia name into (league, season) components
      2. Generate candidate gol.gg names using both orderings
      3. Try each URL; return the first that yields a match table
      4. Fall back to raw tournament.name if nothing works
    """
    parts = re.split(r'/', tournament_name)
    parts_lower = [p.lower().replace(' ', '_') for p in parts]
    year_str = str(year)

    # Detect league via mapping (try longest prefix first)
    league = None
    for i in range(len(parts_lower)):
        for length in range(min(3, len(parts_lower) - i), 0, -1):
            key = '/'.join(parts_lower[i:i + length])
            if key in LEAGUE_NAME_MAP:
                league = LEAGUE_NAME_MAP[key]
                break
        if league:
            break

    # Detect season
    season = None
    for part in parts_lower:
        clean = part.replace('-', '_')
        if clean in SEASON_MAP:
            season = SEASON_MAP[clean]
            break
    if not season:
        for part in parts_lower:
            m = re.search(r'split[_\s]?(\d)', part)
            if m:
                season = f"Split {m.group(1)}"
                break

    # Fall back league name: name minus year and season
    if not league:
        league = tournament_name.replace('/', ' ').replace('_', ' ')
        league = league.replace(year_str, '').strip()
        if season:
            league = league.replace(season, '').strip()
        league = ' '.join(league.split())  # collapse any double spaces

    # Build candidates — try both orderings
    candidates = []
    if league and season:
        candidates.append(f"{league} {season} {year_str}")   # pre-2025
        candidates.append(f"{league} {year_str} {season}")   # 2025+
    elif league:
        candidates.append(f"{league} {year_str}")
    # Also try the raw cleaned-up name
    candidates.append(tournament_name.replace('/', ' ').replace('_', ' '))

    # Collapse any double spaces introduced by name parsing
    candidates = [' '.join(c.split()) for c in candidates]

    for name in candidates:
        url = gol_url_from_name(name)
        try:
            res = session.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                tbody = soup.find('tbody')
                rows = tbody.find_all('tr') if tbody else []
                match_links = soup.find_all('a', href=lambda h: h and 'match-matchlist' in h)
                if rows or match_links:
                    time.sleep(REQUEST_DELAY)
                    return url, name
        except requests.RequestException:
            pass
        time.sleep(REQUEST_DELAY)

    return None, None



# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {'User-Agent': 'Mozilla/5.0'}
REQUEST_DELAY  = 5.0                   # seconds between every gol.gg request
RETRY_DELAYS   = [30, 60, 120]         # back-off on timeout / 429
# Tuple: (connect timeout, read timeout) — covers both failure modes
TIMEOUT        = (15, 45)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gol_get(session, url):
    """
    GET a gol.gg URL with a polite delay and automatic retry on:
      - ConnectTimeout / ReadTimeout / RemoteDisconnected
      - HTTP 429 (explicit rate limit)

    Uses a (connect, read) timeout tuple so both failure modes are covered.
    Raises requests.RequestException after all retries are exhausted.
    """
    for attempt, backoff in enumerate([0] + RETRY_DELAYS):
        if backoff:
            print(f"  [gol.gg] rate limited — waiting {backoff}s (attempt {attempt + 1}/{len(RETRY_DELAYS)})...")
            time.sleep(backoff)
        else:
            time.sleep(REQUEST_DELAY)
        try:
            res = session.get(url, headers=HEADERS, timeout=TIMEOUT)
            if res.status_code == 429:
                # Explicit rate limit — always retry with backoff
                if attempt < len(RETRY_DELAYS):
                    continue
                res.raise_for_status()
            res.raise_for_status()
            return res
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectionError,  # covers RemoteDisconnected
        ):
            if attempt < len(RETRY_DELAYS):
                print(f"  [gol.gg] connection error, will retry after backoff...")
                continue
            raise


def ensure_db_connection():
    """
    Force-close the DB connection so Django opens a fresh one on the next
    query. Called after any long gol.gg wait (30-120s backoff) to prevent
    'SSL connection has been closed unexpectedly' from PostgreSQL.

    connection.ensure_connection() is not enough — it only pings but won't
    recover a connection that PostgreSQL has already killed server-side.
    Unconditional close() is safe: Django will reconnect automatically.
    """
    connection.close()


def fix_champion(name):
    name = name.lower()
    name = name.replace("'", "").replace("\u2019", "").replace("`", "").replace("\xe9", "e")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r"\s*(et\s*)?(willump)?$", "", name).strip()
    return name


def normalize_player_name(name):
    """Return a normalised, punctuation-free lowercase key for player lookup."""
    if not name:
        return ""
    name = name.strip().lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r"[^a-z0-9]", "", name)
    return name  # ← was missing in the original


def find_closest_team_roster(scraped_team_name, normalized_map):
    """Try exact → fuzzy → substring match against a {normalised_name: roster} map."""
    target_norm = normalize_team_name(scraped_team_name)

    if target_norm in normalized_map:
        return normalized_map[target_norm]

    choices = list(normalized_map.keys())
    match = difflib.get_close_matches(target_norm, choices, n=1, cutoff=0.8)
    if match:
        return normalized_map[match[0]]

    for k, v in normalized_map.items():
        if target_norm in k or k in target_norm:
            return v

    return None


def build_roster_player_map(all_roster_players):
    """
    Build a normalised-name → RosterPlayer map that includes:
      - the player's current name
      - every alias stored in player.aliases
    Aliases are comma-separated strings stored on the Player model.
    """
    roster_player_map = {}
    for rp in all_roster_players:
        names = [rp.player.name]
        if getattr(rp.player, 'aliases', None):
            names += [a.strip() for a in rp.player.aliases.split(',') if a.strip()]
        for n in names:
            key = normalize_player_name(n)
            if key:
                roster_player_map[key] = rp
    return roster_player_map


def find_roster_player(scraped_name, roster_player_map):
    """Exact then fuzzy match of a scraped player name against the roster map."""
    target = normalize_player_name(scraped_name)
    if not target:
        return None
    if target in roster_player_map:
        return roster_player_map[target]
    matches = difflib.get_close_matches(
        target, list(roster_player_map.keys()), n=1, cutoff=0.8
    )
    if matches:
        return roster_player_map[matches[0]]
    return None


def parse_kda(kda_string):
    numbers = re.findall(r"\d+", kda_string)
    if len(numbers) < 3:
        return None, None, None
    return tuple(int(x) for x in numbers[:3])


# ---------------------------------------------------------------------------
# gol.gg scraping
# ---------------------------------------------------------------------------

def get_game_link(session, link, i):
    """Return the URL for the i-th game (0-indexed) within a match page."""
    res = gol_get(session, link)
    soup = BeautifulSoup(res.text, 'html.parser')
    nav = soup.find(id='gameMenuToggler')
    if not nav:
        raise ValueError(f"gameMenuToggler not found on {link}")
    li_tags = nav.find_all('li')
    return li_tags[i + 1].find('a')['href'].replace("..", "https://gol.gg")


def get_teams(session, link):
    """Fetch the summary page and return (blue_team_name, red_team_name)."""
    url = link.replace("-game", "-summary")
    res = gol_get(session, url)
    soup = BeautifulSoup(res.text, 'html.parser')
    divs = soup.find_all('div', class_="col-4 col-sm-5 text-center")
    if len(divs) < 2:
        raise ValueError(f"Could not find both teams on page: {url}")
    blue = normalize_team_name(divs[0].get_text(strip=True))
    red = normalize_team_name(divs[1].get_text(strip=True))
    return blue, red


def scrape_game_stats(session, link):
    """
    Fetch a single game page and return a dict with blue_side_text and
    player_stats, or None on any failure.
    """
    try:
        res = gol_get(session, link)
    except requests.RequestException as e:
        print(f"Request failed for {link}: {e}")
        return None

    soup = BeautifulSoup(res.text, 'html.parser')

    blue_side_div = soup.find('div', class_="col-12 blue-line-header")
    if not blue_side_div:
        print(f"Could not find blue_side_div for {link}")
        return None   # previously continued and crashed on get_text()

    player_data = []
    divs = soup.find_all('div', class_="col-12 col-md-6")
    for div in divs:
        div_players = [a.get_text() for a in div.find_all('a', class_="link-blanc")]
        div_champions = [img['alt'] for img in div.find_all('img', class_='champion_icon rounded-circle')]
        div_kdas = [td.get_text() for td in div.find_all('td', attrs={'style': 'text-align:center'})]
        for player, champion, kda in zip(div_players, div_champions, div_kdas):
            player_data.append({
                "player_name": player,
                "champion_name": champion,
                "kda": kda,
            })

    return {
        "blue_side_text": blue_side_div.get_text(),
        "player_stats": player_data,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_game_and_stats(game_data, match, game_number, normalized_champions,
                        roster_player_map, summary):
    blue_side_text = game_data['blue_side_text']
    blue_side_name = (
        blue_side_text
        .replace(" ", "").replace("-", "")
        .replace("WIN", "").replace("LOSS", "")
    )

    team_names = {r.team.name: r for r in [match.blue_roster, match.red_roster]}
    normalized_map = {normalize_team_name(k): v for k, v in team_names.items()}
    blue_side_name = normalize_team_name(blue_side_name)
    blue_side_roster = find_closest_team_roster(blue_side_name, normalized_map)

    if blue_side_roster == match.blue_roster:
        red_side_roster = match.red_roster
        side_swapped = False
    else:
        red_side_roster = match.blue_roster
        side_swapped = True

    if blue_side_text.endswith("WIN"):
        winner = blue_side_roster
        loser = red_side_roster
    else:
        winner = red_side_roster
        loser = blue_side_roster

    obj_game, created_game = Game.objects.update_or_create(
        match=match,
        game_number=game_number,
        defaults={'winner': winner, 'loser': loser, 'side_swapped': side_swapped},
    )
    if created_game:
        summary['games_created'] += 1
    else:
        summary['games_skipped'] += 1

    for data in game_data['player_stats']:
        player_name = data['player_name']
        champion_name = data['champion_name']
        kda = data['kda']

        roster_player = find_roster_player(player_name, roster_player_map)
        if not roster_player:
            summary['error_details'].append({
                "type": "roster_player_missing",
                "player_name": player_name,
                "match": str(match),
                "game_number": game_number,
            })
            summary['errors'] += 1
            continue

        normalized_name = fix_champion(champion_name)
        champion = normalized_champions.get(normalized_name)
        if not champion:
            summary['error_details'].append({
                "type": "champion_missing",
                "champion_name": champion_name,
                "normalized_name": normalized_name,
                "match": str(match),
                "game_number": game_number,
            })
            summary['errors'] += 1
            continue

        kills, deaths, assists = parse_kda(kda)
        if None in (kills, deaths, assists):
            summary['stats_skipped'] += 1
            continue

        obj_stat, created_stat = PlayerStats.objects.get_or_create(
            roster_player=roster_player,
            game=obj_game,
            defaults={
                'champion': champion,
                'kills': kills,
                'deaths': deaths,
                'assists': assists,
            },
        )
        if created_stat:
            summary['stats_created'] += 1
        else:
            summary['stats_skipped'] += 1


def import_game(session, link, match, game_number, normalized_champions,
                roster_player_map, summary):
    parsed = scrape_game_stats(session, link)
    # Scraping may have spent 30-120s in backoff — reconnect before writing
    ensure_db_connection()
    if parsed is None:
        summary['errors'] += 1
        try:
            match_str = str(match)
        except Exception:
            match_str = f"match_id={match.pk}"
        summary['error_details'].append({
            "type": "scrape_failed",
            "link": link,
            "match": match_str,
            "game_number": game_number,
        })
        return
    save_game_and_stats(parsed, match, game_number, normalized_champions,
                        roster_player_map, summary)


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Import finished match stats from gol.gg.\n\n"
        "Default: tournaments active within the past 5 days.\n"
        "  --year YYYY : import all finished tournaments for that year\n"
        "  --all       : import every finished tournament in the DB"
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--year',
            type=int,
            metavar='YYYY',
            help='Import all finished tournaments whose date_started falls in this year.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            help='Import every finished tournament in the database.',
        )

    def handle(self, *args, **options):
        session = requests.Session()
        session.headers.update(HEADERS)

        summary = {
            'matches_processed': 0,
            'games_created': 0,
            'games_skipped': 0,
            'stats_created': 0,
            'stats_skipped': 0,
            'errors': 0,
            'error_details': [],
        }

        normalized_champions = {fix_champion(c.name): c for c in Champion.objects.all()}
        now = timezone.now().date()

        # --- Tournament selection ---
        if options.get('all'):
            tournaments = Tournament.objects.filter(
                date_ended__lte=now
            ).order_by('date_started')
            self.stdout.write(self.style.WARNING(
                f"Importing ALL {tournaments.count()} finished tournaments."
            ))
        elif options.get('year'):
            year = options['year']
            tournaments = Tournament.objects.filter(
                date_started__year=year,
                date_ended__lte=now,
            ).order_by('date_started')
            self.stdout.write(self.style.NOTICE(
                f"Importing {tournaments.count()} finished tournaments for {year}."
            ))
        else:
            tournaments = Tournament.objects.filter(
                date_ended__gte=now - timedelta(days=5),
                date_started__lte=now + timedelta(days=5),
            ).order_by('date_started')
            self.stdout.write(self.style.NOTICE(
                f"Importing {tournaments.count()} recent/active tournaments."
            ))

        total = tournaments.count()
        for idx, tournament in enumerate(tournaments, start=1):
            self.stdout.write(self.style.NOTICE(
                f"[{idx}/{total}] {tournament.name}"
            ))

            year = tournament.date_started.year
            rosters = Roster.objects.filter(tournament=tournament)
            normalized_map = {
                normalize_team_name(r.team.name): r for r in rosters
            }
            normalized_slug_map = {
                normalize_team_name(r.team.slug): r
                for r in rosters if r.team.slug
            }

            all_roster_players = (
                RosterPlayer.objects
                .filter(roster__tournament=tournament)
                .select_related("player", "roster", "roster__team")
            )

            # Build roster player map once per tournament (includes aliases)
            roster_player_map = build_roster_player_map(all_roster_players)

            # Resolve the correct gol.gg URL — naming differs from Liquipedia
            # and changed in 2025 (year moved from after season to before it).
            gol_url, gol_name = resolve_gol_url(session, tournament.name, year)
            if gol_url:
                self.stdout.write(self.style.NOTICE(
                    f"  gol.gg match: '{gol_name}' → {gol_url}"
                ))
            else:
                # Last resort: use the tournament name verbatim
                gol_url = gol_url_from_name(tournament.name)
                self.stdout.write(self.style.WARNING(
                    f"  gol.gg URL not resolved, falling back to: {gol_url}"
                ))

            try:
                res = gol_get(session, gol_url)
                soup = BeautifulSoup(res.text, 'html.parser')
            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"  Request failed: {e}"))
                continue

            tbody = soup.find('tbody')
            if not tbody:
                self.stdout.write(self.style.WARNING("  No match table found, skipping."))
                continue

            rows = tbody.find_all('tr')
            total_rows = len(rows)

            def print_progress(current, total, t_name):
                """Print an inline progress bar that updates in place."""
                bar_width = 30
                filled = int(bar_width * current / total) if total else bar_width
                bar = '█' * filled + '░' * (bar_width - filled)
                pct = int(100 * current / total) if total else 100
                # \r returns to line start without newline so it overwrites itself
                print(f"\r  [{bar}] {pct:3d}% ({current}/{total}) {t_name[:30]}", end='', flush=True)

            print_progress(0, total_rows, tournament.name)
            for row_idx, row in enumerate(rows, start=1):
                # --- Phase 1: parse HTML row (no DB, no network) ---
                cols = row.find_all('td')
                if not cols:
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                patch = cols[-2].get_text(strip=True)
                if not patch and tournament.date_ended > date.today():
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                try:
                    date_match = datetime.strptime(
                        cols[-1].get_text(strip=True), "%Y-%m-%d"
                    ).date()
                except ValueError as e:
                    self.stdout.write(self.style.WARNING(
                        f"  [SKIP] date parse failed: {cols[-1].get_text(strip=True)!r} ({e})"
                    ))
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                match_ref = cols[0].find('a')
                if not match_ref:
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                match_url = (
                    match_ref['href']
                    .replace("..", "https://gol.gg")
                    .replace("summary/", "game/")
                )

                score_str = cols[2].get_text(strip=True)
                victory_td = row.find('td', class_="text_victory")
                if not victory_td:
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                # --- Phase 2: network calls to gol.gg (outside any atomic) ---
                try:
                    blue_team_str, red_team_str = get_teams(
                        session,
                        match_ref['href'].replace("..", "https://gol.gg"),
                    )
                except (ValueError, requests.RequestException) as e:
                    self.stdout.write(self.style.WARNING(f"  get_teams failed: {e}"))
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                winner_str = normalize_team_name(victory_td.get_text())
                score_match = re.match(r"(\d+)\s*-\s*(\d+)", score_str)
                if not score_match:
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                # Resolve rosters (in-memory, no DB)
                blue_roster = find_closest_team_roster(blue_team_str, normalized_map)
                if not blue_roster:
                    blue_roster = find_closest_team_roster(blue_team_str, normalized_slug_map)
                if not blue_roster:
                    self.stdout.write(self.style.WARNING(
                        f"  Roster not found for: {blue_team_str}"
                    ))
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                red_roster = find_closest_team_roster(red_team_str, normalized_map)
                if not red_roster:
                    red_roster = find_closest_team_roster(red_team_str, normalized_slug_map)
                if not red_roster:
                    self.stdout.write(self.style.WARNING(
                        f"  Roster not found for: {red_team_str}"
                    ))
                    print_progress(row_idx, total_rows, tournament.name)
                    continue

                if blue_team_str == winner_str:
                    winner = blue_roster
                    winner_score = int(score_match.group(1))
                    loser = red_roster
                    loser_score = int(score_match.group(2))
                else:
                    winner = red_roster
                    winner_score = int(score_match.group(2))
                    loser = blue_roster
                    loser_score = int(score_match.group(1))

                best_of = 2 * winner_score - 1
                number_of_games = winner_score + loser_score

                # --- Phase 3: DB writes for match metadata (short atomic) ---
                ensure_db_connection()
                with transaction.atomic():
                    matchday, _ = MatchDay.objects.get_or_create(
                        date=date_match,
                        tournament=tournament,
                    )

                    match = Match.objects.select_related(
                        'match_day__tournament',
                        'blue_roster__team',
                        'red_roster__team',
                    ).filter(
                        Q(match_day=matchday, blue_roster=blue_roster, red_roster=red_roster) |
                        Q(match_day=matchday, blue_roster=red_roster, red_roster=blue_roster)
                    ).first()

                    if match:
                        match.score_str = score_str
                        match.winner = winner
                        match.is_closed = True
                        match.winner_score = winner_score
                        match.loser_score = loser_score
                        if match.blue_roster != blue_roster:
                            match.blue_roster, match.red_roster = (
                                match.red_roster, match.blue_roster
                            )
                        match.save()
                    elif tournament.date_ended <= date.today():
                        match_name = (
                            f"{blue_roster.team.name} VS "
                            f"{red_roster.team.name} ({tournament.name})"
                        )
                        match, _ = Match.objects.get_or_create(
                            match_day=matchday,
                            blue_roster=blue_roster,
                            red_roster=red_roster,
                            defaults={
                                'name': match_name,
                                'scheduled_time': date_match,
                                'scheduled_hour': dt_time(12, 0),
                                'best_of': best_of,
                                'score_str': score_str,
                                'winner': winner,
                                'is_closed': True,
                                'winner_score': winner_score,
                                'loser_score': loser_score,
                            },
                        )
                    else:
                        self.stdout.write(
                            f"  [SKIP] {blue_team_str} VS {red_team_str} "
                            f"on {date_match} — not in DB and tournament not finished."
                        )
                        print_progress(row_idx, total_rows, tournament.name)
                        continue

                # --- Phase 4: per-game network + DB (each game is independent) ---
                # ensure_db_connection() is called inside import_game, after
                # scraping, so no atomic block is open when the connection drops.
                if match.best_of == 1:
                    import_game(
                        session, match_url, match, 1,
                        normalized_champions, roster_player_map, summary,
                    )
                else:
                    for i in range(number_of_games):
                        try:
                            game_url = get_game_link(session, match_url, i)
                        except (ValueError, requests.RequestException, IndexError) as e:
                            self.stdout.write(self.style.WARNING(
                                f"  get_game_link failed for game {i+1}: {e}"
                            ))
                            summary['errors'] += 1
                            continue
                        import_game(
                            session, game_url, match, i + 1,
                            normalized_champions, roster_player_map, summary,
                        )

                summary['matches_processed'] += 1
                print_progress(row_idx, total_rows, tournament.name)

            # Move to next line after the progress bar finishes
            print()

        # Final summary
        self.stdout.write("\n==== Import Summary ====")
        for k, v in summary.items():
            if k != 'error_details':
                self.stdout.write(f"{k.replace('_', ' ').capitalize()}: {v}")
        if summary['error_details']:
            self.stdout.write("\n---- Error Details ----")
            for err in summary['error_details']:
                if isinstance(err, dict):
                    err_type = err.get("type", "unknown")
                    details = ", ".join(
                        f"{k}: {v}" for k, v in err.items() if k != "type"
                    )
                    self.stdout.write(f"[{err_type}] {details}")
                else:
                    self.stdout.write(str(err))