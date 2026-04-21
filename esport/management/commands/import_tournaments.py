import re
import time
import calendar
import requests
from datetime import datetime, date
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from esport.models import Tournament

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {'User-Agent': 'Mozilla/5.0'}
REQUEST_DELAY = 2.0   # seconds between Liquipedia requests

# Liquipedia S-Tier listing URL — append ?year=YYYY for historical pages
LP_STIER_URL = "https://liquipedia.net/leagueoflegends/S-Tier_Tournaments"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def lp_get(url, retry_delays=(10, 30, 60)):
    """Rate-limited GET with retry on 429 / timeout."""
    for attempt, backoff in enumerate([0] + list(retry_delays)):
        if backoff:
            print(f"  [LP] backing off {backoff}s (attempt {attempt + 1})...")
            time.sleep(backoff)
        else:
            time.sleep(REQUEST_DELAY)
        try:
            res = requests.get(url, headers=HEADERS, timeout=(10, 30))
            if res.status_code == 429:
                if attempt < len(retry_delays):
                    continue
                res.raise_for_status()
            res.raise_for_status()
            return res
        except requests.exceptions.Timeout:
            if attempt < len(retry_delays):
                print(f"  [LP] timeout, will retry...")
                continue
            raise
    raise requests.RequestException(f"All retries exhausted for {url}")


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _last_day(year, month):
    return calendar.monthrange(year, month)[1]


def _try_parse(s, fmt):
    try:
        return datetime.strptime(s.strip(), fmt).date()
    except ValueError:
        return None


def parse_liquipedia_dates(date_str):
    """
    Parse a Liquipedia tournament date string into (start_date, end_date).

    Handles all formats seen in practice, including TBA end dates:
      "May 1 - May 19, 2024"      full range
      "Oct 1, 2023 - Nov 1, 2023" full range with explicit years
      "May 17 - 20, 2018"         same-month range
      "May 11, 2018"              single day
      "2023-11-01"                ISO
      "Apr 04 - Jun TBA, 2026"    known start, TBA end month
      "Jul - Sep, 2026"           month-only range
      "Jun TBA, 2026"             single TBA month
      "TBA" / "TBD"               fully unknown -> (None, None)
    """
    if not date_str or not date_str.strip():
        return None, None

    s = date_str.strip()

    if re.fullmatch(r'(TBA|TBD)', s, re.IGNORECASE):
        return None, None

    # ISO date must be checked BEFORE dash normalisation
    m = re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        d = _try_parse(s, "%Y-%m-%d")
        if d:
            return d, d

    # Normalise unicode dashes then space-pad
    for ch in ('\u2013', '\u2014', '\u2212'):
        s = s.replace(ch, '-')
    s = re.sub(r'\s*-\s*', ' - ', s)
    s = s.replace('\xa0', ' ').strip()

    year_m = re.search(r'\b(20\d{2})\b', s)
    year = int(year_m.group(1)) if year_m else date.today().year

    def month_num(mo_str):
        d = _try_parse(mo_str, "%b") or _try_parse(mo_str, "%B")
        return (d.month, _last_day(year, d.month)) if d else None

    def parse_half(part, is_end=False):
        part = re.sub(r'\b20\d{2}\b', '', part).strip().rstrip(',').strip()
        if re.fullmatch(r'(TBA|TBD)', part, re.IGNORECASE):
            return None
        m = re.match(r'([A-Za-z]+)\s+(\d{1,2})$', part)
        if m:
            mo = month_num(m.group(1))
            if mo:
                return date(year, mo[0], int(m.group(2)))
        m = re.match(r'([A-Za-z]+)(?:\s+(?:TBA|TBD))?$', part, re.IGNORECASE)
        if m:
            mo = month_num(m.group(1))
            if mo:
                return date(year, mo[0], mo[1] if is_end else 1)
        m = re.fullmatch(r'(\d{1,2})', part)
        if m:
            return int(m.group(1))
        return None

    if ' - ' in s:
        left, right = s.split(' - ', 1)

        # Right side is bare day number: "Month Day - Day, Year"
        right_bare = re.sub(r'\b20\d{2}\b', '', right).strip().rstrip(',').strip()
        if re.fullmatch(r'\d{1,2}', right_bare):
            start = parse_half(left, is_end=False)
            if isinstance(start, date):
                return start, date(year, start.month, int(right_bare))

        start = parse_half(left, is_end=False)
        end   = parse_half(right, is_end=True)

        if isinstance(start, date) and isinstance(end, date):
            return start, end
        if isinstance(start, date) and end is None:
            end = date(start.year, start.month, _last_day(start.year, start.month))
            print(f"  [dates] TBA end — using end of month: {end}")
            return start, end

    # No separator — single date or month
    end_result   = parse_half(s, is_end=True)
    start_result = parse_half(s, is_end=False)
    if isinstance(end_result, date):
        if isinstance(start_result, date) and start_result != end_result:
            return start_result, end_result   # month-only: 1st → last
        return end_result, end_result

    print(f"  [dates] Could not parse: {date_str!r}")
    return None, None


def get_tournament_league(link):
    """Fetch the tournament page and return the Series name, or None."""
    try:
        res = lp_get(link)
    except requests.RequestException as e:
        print(f"  [LP] get_tournament_league failed for {link}: {e}")
        return None
    soup = BeautifulSoup(res.text, 'html.parser')
    div = soup.find(string="Series:")
    if not div:
        return None
    nxt = div.find_next('div')
    return nxt.get_text(strip=True) if nxt else None


def fetch_and_save_logo(obj, image_url, field_name, tournament_name, style, label=""):
    filename = f"{slugify(tournament_name)}{'-' + label if label else ''}.png"
    try:
        response = requests.get(image_url, timeout=15)
        if response.status_code == 200:
            field = getattr(obj, field_name)
            field.save(filename, ContentFile(response.content), save=True)
            print(style.NOTICE(f"  Logo saved: {field.name}"))
        else:
            print(style.NOTICE(f"  Could not fetch logo ({response.status_code}): {image_url}"))
    except requests.RequestException as e:
        print(style.NOTICE(f"  Logo fetch failed: {e}"))


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = (
        "Import S-Tier tournaments from Liquipedia.\n\n"
        "Default: scrapes the current S-Tier page (recent + upcoming).\n"
        "  --year YYYY : scrape the S-Tier page filtered to that year\n"
        "  --all       : scrape years from 2012 to current year"
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            '--year',
            type=int,
            metavar='YYYY',
            help='Import S-Tier tournaments for a specific year.',
        )
        group.add_argument(
            '--all',
            action='store_true',
            help='Import S-Tier tournaments for all years (2012 → now).',
        )

    def handle(self, *args, **options):
        if options.get('all'):
            years = list(range(2012, date.today().year + 1))
            self.stdout.write(self.style.WARNING(
                f"Importing all years: {years[0]}–{years[-1]}"
            ))
        elif options.get('year'):
            years = [options['year']]
            self.stdout.write(self.style.NOTICE(f"Importing year {years[0]}"))
        else:
            years = [None]   # None → current page, no year filter
            self.stdout.write(self.style.NOTICE("Importing current S-Tier page"))

        total_created = 0
        total_skipped = 0

        for year in years:
            if year:
                url = f"{LP_STIER_URL}?year={year}"
            else:
                url = LP_STIER_URL

            self.stdout.write(self.style.NOTICE(f"\n--- {url} ---"))

            try:
                res = lp_get(url)
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Request failed: {e}"))
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            grid_tables = soup.select("div.table2.tournaments-listing")

            if not grid_tables:
                self.stdout.write(self.style.WARNING("No tournament table found on page."))
                continue

            for grid_table in grid_tables:
                for row in grid_table.select("tr.table2__row--body"):
                    cells = row.find_all("td", recursive=False)
                    if len(cells) < 3:
                        continue

                    tournament_link = cells[1].find("a")
                    if not tournament_link:
                        continue

                    tournament_name = tournament_link.get_text(strip=True)
                    tournament_slug = slugify(tournament_name)
                    liquipedia_url  = "https://liquipedia.net" + tournament_link.get("href", "")
                    date_str        = cells[2].get_text(strip=True)

                    start_date, end_date = parse_liquipedia_dates(date_str)

                    if not start_date:
                        self.stdout.write(self.style.WARNING(
                            f"  Skipping {tournament_name!r}: could not parse dates from {date_str!r}"
                        ))
                        continue

                    # Enforce year filter — Liquipedia's ?year= param is not strict
                    # and can return tournaments from adjacent years
                    if year and start_date.year != year:
                        continue

                    # If end date is TBA, end_date is set to end of the month
                    # but flag it so we know to re-import once the date is confirmed
                    tba_end = end_date and 'tba' in date_str.lower()

                    # Fetch the league/series name from the tournament page
                    tournament_league = get_tournament_league(liquipedia_url)

                    tournament_split = (
                        tournament_name
                        .replace(str(start_date.year), "")
                        .replace(tournament_league or "", "")
                        .strip()
                        .replace(" ", "_")
                    )

                    obj, created = Tournament.objects.update_or_create(
                        slug=tournament_slug,
                        defaults={
                            'name':           tournament_name,
                            'league':         tournament_league or "",
                            'year':           start_date.year,
                            'split':          tournament_split,
                            'date_started':   start_date,
                            'date_ended':     end_date,
                            'liquipedia_url': liquipedia_url,
                        },
                    )

                    if created:
                        flag = " [end date TBA — will need updating]" if tba_end else ""
                        self.stdout.write(self.style.SUCCESS(
                            f"  Created: {tournament_name} | "
                            f"{start_date} → {end_date}{flag}"
                        ))
                        total_created += 1
                    else:
                        self.stdout.write(self.style.NOTICE(
                            f"  Exists: {tournament_name}"
                        ))
                        total_skipped += 1

                    # Save logos
                    icon_cell = cells[0]
                    light_span = icon_cell.find(
                        lambda tag: tag.name == "span"
                        and "league-icon-small-image" in tag.get("class", [])
                        and "darkmode" not in tag.get("class", [])
                    )
                    if light_span:
                        img = light_span.find("img")
                        if img:
                            fetch_and_save_logo(
                                obj, "https://liquipedia.net" + img["src"],
                                "logo", tournament_name, self.style,
                            )

                    dark_span = icon_cell.find(
                        lambda tag: tag.name == "span"
                        and "league-icon-small-image" in tag.get("class", [])
                        and "darkmode" in tag.get("class", [])
                    )
                    if dark_span:
                        img = dark_span.find("img")
                        if img:
                            fetch_and_save_logo(
                                obj, "https://liquipedia.net" + img["src"],
                                "logo_dark", tournament_name, self.style, label="dark",
                            )

            if len(years) > 1:
                # Inter-year pause to be polite to Liquipedia
                time.sleep(5)

        self.stdout.write(self.style.SUCCESS(
            f"\n==== Done ==== created={total_created}  skipped={total_skipped}"
        ))