import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
import difflib
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from esport.models import Match, MatchDay, Roster, RosterPlayer, Tournament
from esport.utils import normalize_team_name


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

# Comprehensive month name → number map covering every language lolesports
# uses depending on the visitor's browser locale. The Accept-Language header
# forces French but the site sometimes mixes languages, so we cover them all.
MONTHS = {
    # French
    'janvier': 1, 'janv': 1,
    'février': 2, 'fevrier': 2, 'fevr': 2,
    'mars': 3,
    'avril': 4, 'avr': 4,
    'mai': 5,
    'juin': 6,
    'juillet': 7, 'juil': 7,
    'août': 8, 'aout': 8,
    'septembre': 9, 'sept': 9,
    'octobre': 10, 'oct': 10,
    'novembre': 11, 'nov': 11,
    'décembre': 12, 'decembre': 12, 'déc': 12, 'dec': 12,
    # English
    'january': 1, 'jan': 1,
    'february': 2, 'feb': 2,
    'march': 3, 'mar': 3,
    'april': 4, 'apr': 4,
    'may': 5,
    'june': 6, 'jun': 6,
    'july': 7, 'jul': 7,
    'august': 8, 'aug': 8,
    'september': 9, 'sep': 9,
    'october': 10,
    'november': 11,
    'december': 12,
    # Spanish
    'enero': 1, 'ene': 1,
    'febrero': 2,
    'marzo': 3,
    'abril': 4, 'abr': 4,
    'mayo': 5,
    'junio': 6,
    'julio': 7,
    'agosto': 8, 'ago': 8,
    'septiembre': 9,
    'octubre': 10,
    'noviembre': 11,
    'diciembre': 12, 'dic': 12,
    # Portuguese
    'janeiro': 1,
    'fevereiro': 2,
    'março': 3, 'marco': 3,
    'junho': 6,
    'julho': 7,
    'setembro': 9,
    'novembro': 11,
    'dezembro': 12,
    # German
    'januar': 1,
    'februar': 2,
    'märz': 3, 'marz': 3,
    'mai': 5,
    'juni': 6,
    'juli': 7,
    'august': 8,
    'oktober': 10,
    'dezember': 12,
    # Italian
    'gennaio': 1,
    'febbraio': 2,
    'marzo': 3,
    'aprile': 4,
    'maggio': 5,
    'giugno': 6,
    'luglio': 7,
    'agosto': 8,
    'settembre': 9,
    'ottobre': 10,
    'novembre': 11,
    'dicembre': 12,
    # Korean (romanised, just in case)
    'wol': 1,
}

# Relative date keywords across all locales lolesports uses
TODAY_WORDS = {
    "today", "aujourd'hui", "plus tôt aujourd'hui", "hoy", "hoje", "heute",
    "oggi", "今日",
}
YESTERDAY_WORDS = {
    "yesterday", "hier", "ayer", "ontem", "gestern", "ieri", "昨日",
}
TOMORROW_WORDS = {
    "tomorrow", "demain", "mañana", "amanhã", "morgen", "domani", "明日",
}


def get_date(date_str):
    """
    Parse lolesports date strings into a Python date object.

    lolesports returns dates in the visitor's browser locale, which can be
    anything. We normalise the string first (strip accents, lowercase, remove
    punctuation) and try several patterns:
      - relative keywords: today/hier/ayer/…
      - "<day> <month_name>"   e.g. "17 abr", "18 avril"
      - "<month_name> <day>"   e.g. "Apr 18"
      - ISO-like: "2026-04-18" (fallback)
    """
    import unicodedata

    today = date.today()
    raw = date_str.strip()
    normalised = unicodedata.normalize('NFKD', raw).encode('ASCII', 'ignore').decode('utf-8')
    normalised = normalised.lower().strip().rstrip('.')

    if normalised in TODAY_WORDS or raw.lower() in TODAY_WORDS:
        return today
    if normalised in YESTERDAY_WORDS or raw.lower() in YESTERDAY_WORDS:
        return today - timedelta(days=1)
    if normalised in TOMORROW_WORDS or raw.lower() in TOMORROW_WORDS:
        return today + timedelta(days=1)

    # Remove ordinal suffixes (1st, 2nd, 3rd, 21st …)
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', normalised)
    # Remove dots used as abbreviation markers (abr. → abr)
    cleaned = cleaned.replace('.', ' ').strip()
    # Collapse multiple spaces
    cleaned = re.sub(r'\s+', ' ', cleaned)

    # Try "<number> <word>" → day month
    m = re.match(r'^(\d{1,2})\s+([a-z]+)$', cleaned)
    if m:
        day, month_word = int(m.group(1)), m.group(2)
        month = MONTHS.get(month_word)
        if month:
            # If the resulting date is more than 6 months in the past, assume
            # it's next year (handles year-end schedule)
            d = date(today.year, month, day)
            if (today - d).days > 180:
                d = date(today.year + 1, month, day)
            return d

    # Try "<word> <number>" → month day
    m = re.match(r'^([a-z]+)\s+(\d{1,2})$', cleaned)
    if m:
        month_word, day = m.group(1), int(m.group(2))
        month = MONTHS.get(month_word)
        if month:
            d = date(today.year, month, day)
            if (today - d).days > 180:
                d = date(today.year + 1, month, day)
            return d

    # ISO format fallback
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    except ValueError:
        pass

    raise ValueError(f"Unrecognised date format: {date_str!r} (normalised: {cleaned!r})")


# ---------------------------------------------------------------------------
# Team / tournament lookup helpers
# ---------------------------------------------------------------------------

def find_closest_team_roster(scraped_team_name, normalized_map, cutoff=0.8):
    target_norm = normalize_team_name(scraped_team_name)

    if target_norm in normalized_map:
        return normalized_map[target_norm]

    choices = list(normalized_map.keys())
    match = difflib.get_close_matches(target_norm, choices, n=1, cutoff=cutoff)
    if match:
        return normalized_map[match[0]]

    # Substring fallback
    for k, v in normalized_map.items():
        if target_norm in k or k in target_norm:
            return v

    return None


def get_tournament(league_str, tournaments):
    """
    Match a lolesports league name (e.g. "LEC", "La Ligue Française") to a
    Tournament in the DB. Uses case-insensitive substring matching first,
    then fuzzy matching as a fallback.
    """
    league_norm = normalize_team_name(league_str)

    # Exact substring match
    for t in tournaments:
        if league_norm in normalize_team_name(t.name):
            return t

    # Fuzzy match
    choices = {normalize_team_name(t.name): t for t in tournaments}
    matches = difflib.get_close_matches(league_norm, choices.keys(), n=1, cutoff=0.6)
    if matches:
        return choices[matches[0]]

    return None


# ---------------------------------------------------------------------------
# Best-of extraction
# ---------------------------------------------------------------------------

def parse_best_of(best_of_str):
    """
    Extract the best-of number from a lolesports footer string.
    Examples: "SÉRIE DE 1", "BEST OF 3", "BO5", "SÉRIE DE 5"
    Returns an int or None if not parseable.
    """
    m = re.search(r'(\d+)\s*$', best_of_str.strip())
    if m:
        return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Import upcoming matches from lolesports.com"

    def handle(self, *args, **options):
        headers = {
            # Force French locale to get consistent (though not guaranteed)
            # date strings. get_date() handles all locales anyway.
            "Accept-Language": "fr-FR,fr;q=0.9",
            "User-Agent": "Mozilla/5.0",
        }
        url = (
            "https://lolesports.com/fr-FR/leagues/"
            "emea_masters,first_stand,lck,lcp,lcs,lec,lpl,"
            "lta_cross,lta_n,lta_s,msi,worlds"
        )

        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"Request failed: {e}"))
            return

        soup = BeautifulSoup(res.text, 'html.parser')
        sects = soup.find_all('section', attrs={"data-tag": True})
        if not sects:
            self.stdout.write(self.style.WARNING(
                "No <section data-tag=…> found — lolesports HTML may have changed."
            ))
            return

        # --- Load active/upcoming tournaments and their rosters ---
        now = timezone.now().date()
        tournaments = list(
            Tournament.objects.filter(
                date_ended__gte=now,
                date_started__lte=now + timedelta(days=5),
            )
        )

        if not tournaments:
            self.stdout.write(self.style.WARNING("No active tournaments found in DB."))
            return

        # Build per-tournament roster maps once
        tournament_roster_cache = {}
        for tournament in tournaments:
            rosters = Roster.objects.filter(tournament=tournament).select_related('team')
            tournament_roster_cache[tournament.pk] = {
                "tournament": tournament,
                "normalized_map": {normalize_team_name(r.team.name): r for r in rosters},
                "slug_map": {
                    normalize_team_name(r.team.slug): r
                    for r in rosters if r.team.slug
                },
            }

        summary = {"created": 0, "skipped": 0, "errors": 0}

        for date_sect in sects:
            raw_date_str = date_sect.get('data-date', '')

            # --- Parse the section date ---
            try:
                section_date = get_date(raw_date_str)
            except ValueError as e:
                self.stdout.write(self.style.WARNING(f"  Date parse failed: {e}"))
                continue

            # Only process upcoming matches (today and future)
            # Past sections have no time tags and we can't create useful matches
            if section_date < now:
                continue

            self.stdout.write(self.style.NOTICE(
                f"\n--- {raw_date_str!r} → {section_date} ---"
            ))

            # Collect match divs until the next section
            match_divs = []
            for sib in date_sect.find_next_siblings():
                if sib.name == 'section':
                    break
                if sib.get_text(strip=True) in ('Charger plus', 'Load more', 'Ver más'):
                    break
                if sib.name == 'div':
                    match_divs.append(sib)

            for div in match_divs:
                with transaction.atomic():
                    # --- Extract footer data (league name, best-of) ---
                    footer = div.find('footer')
                    if not footer:
                        continue

                    footer_imgs = footer.find_all('img')
                    footer_ps = footer.find_all('p')
                    if not footer_imgs or not footer_ps:
                        continue

                    league_str = footer_imgs[0].get('alt', '')
                    best_of_str = footer_ps[-1].get_text(strip=True)
                    best_of = parse_best_of(best_of_str)
                    if best_of is None:
                        self.stdout.write(self.style.WARNING(
                            f"  Could not parse best-of from {best_of_str!r}, skipping."
                        ))
                        continue

                    # --- Match this league to a DB tournament ---
                    tournament = get_tournament(league_str, tournaments)
                    if not tournament:
                        self.stdout.write(self.style.WARNING(
                            f"  No tournament found for league {league_str!r}, skipping."
                        ))
                        summary['errors'] += 1
                        continue

                    cache = tournament_roster_cache[tournament.pk]
                    normalized_map = cache['normalized_map']
                    slug_map = cache['slug_map']

                    # --- Extract scheduled time (only present for upcoming matches) ---
                    time_tag = div.find('time')
                    if not time_tag or not time_tag.get('datetime'):
                        # Past match with no time — shouldn't reach here since
                        # we filtered section_date < now above, but be safe
                        continue

                    try:
                        scheduled_dt = datetime.fromisoformat(
                            time_tag['datetime'].replace('Z', '+00:00')
                        )
                    except ValueError as e:
                        self.stdout.write(self.style.WARNING(
                            f"  Could not parse datetime {time_tag['datetime']!r}: {e}"
                        ))
                        continue

                    # --- Extract team names from img alt attributes ---
                    # The match div has: [team1_logo, team2_logo, league_logo]
                    # Team logos come before the league logo in the footer
                    # The team imgs are in the main div body, not the footer
                    team_imgs = [
                        img for img in div.find_all('img')
                        if img not in footer_imgs
                    ]
                    if len(team_imgs) < 2:
                        self.stdout.write(self.style.WARNING(
                            f"  Could not find 2 team images in match div, skipping."
                        ))
                        continue

                    blue_team_name = team_imgs[0].get('alt', '')
                    red_team_name = team_imgs[1].get('alt', '')

                    # --- Resolve rosters ---
                    blue_roster = find_closest_team_roster(blue_team_name, normalized_map)
                    if not blue_roster:
                        blue_roster = find_closest_team_roster(blue_team_name, slug_map, cutoff=0.9)
                    if not blue_roster:
                        # Try the parent element text as a fallback name
                        parent_text = team_imgs[0].parent.get_text(strip=True)
                        blue_roster = find_closest_team_roster(parent_text, normalized_map, cutoff=0.9)
                    if not blue_roster:
                        self.stdout.write(self.style.WARNING(
                            f"  Roster not found for: {blue_team_name!r}"
                        ))
                        summary['errors'] += 1
                        continue

                    red_roster = find_closest_team_roster(red_team_name, normalized_map)
                    if not red_roster:
                        red_roster = find_closest_team_roster(red_team_name, slug_map, cutoff=0.9)
                    if not red_roster:
                        parent_text = team_imgs[1].parent.get_text(strip=True)
                        red_roster = find_closest_team_roster(parent_text, normalized_map, cutoff=0.9)
                    if not red_roster:
                        self.stdout.write(self.style.WARNING(
                            f"  Roster not found for: {red_team_name!r}"
                        ))
                        summary['errors'] += 1
                        continue

                    # --- Roster completeness check ---
                    blue_count = RosterPlayer.objects.filter(
                        roster=blue_roster, is_starter=True
                    ).count()
                    red_count = RosterPlayer.objects.filter(
                        roster=red_roster, is_starter=True
                    ).count()
                    if blue_count < 5:
                        self.stdout.write(self.style.WARNING(
                            f"  Roster incomplete ({blue_count}/5): {blue_team_name!r}"
                        ))
                        continue
                    if red_count < 5:
                        self.stdout.write(self.style.WARNING(
                            f"  Roster incomplete ({red_count}/5): {red_team_name!r}"
                        ))
                        continue

                    # --- Create match ---
                    obj_matchday, _ = MatchDay.objects.get_or_create(
                        date=section_date,
                        tournament=tournament,
                    )

                    match_name = (
                        f"{blue_roster.team.name} VS "
                        f"{red_roster.team.name} ({tournament.name})"
                    )

                    obj_match, created = Match.objects.get_or_create(
                        match_day=obj_matchday,
                        blue_roster=blue_roster,
                        red_roster=red_roster,
                        defaults={
                            'name': match_name,
                            'scheduled_hour': scheduled_dt.time(),
                            'best_of': best_of,
                        },
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS(
                            f"  [CREATED] {blue_roster.team.name} vs "
                            f"{red_roster.team.name} — {scheduled_dt.strftime('%H:%M')} BO{best_of}"
                        ))
                        summary['created'] += 1
                    else:
                        summary['skipped'] += 1

        self.stdout.write(
            f"\n==== Done ==== "
            f"created={summary['created']}  "
            f"skipped={summary['skipped']}  "
            f"errors={summary['errors']}"
        )