import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
import difflib
from django.core.management.base import BaseCommand
from esport.models import  Champion, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Team, Tournament
import unicodedata
from urllib.parse import quote

def normalize_team_name(name):
    # Lowercase, remove apostrophes/accents, trim spaces, remove sponsors
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "").replace(" ","")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"\bs?\b", "", name)   # remove stray s
    name = re.sub(r"\s+", " ", name).strip()
    # Remove prefixes like "movistar", "team", "esports", etc. (customize this)
    name = re.sub(r"^(movistar|team|esports|club|fc|ac|the)\s+", "", name)
    
    return name

def find_closest_team_roster(scraped_team_name, normalized_map, cutoff):

    target_norm = normalize_team_name(scraped_team_name)
    # Try exact match first
    
    print(target_norm)

    if target_norm in normalized_map:
        return normalized_map[target_norm]

    # Fuzzy match
    choices = list(normalized_map.keys())
    match = difflib.get_close_matches(target_norm, choices, n=1, cutoff=cutoff)
    if match:
        return normalized_map[match[0]]

    # Substring match as fallback
    for k, v in normalized_map.items():
        if target_norm in k or k in target_norm:
            return v

    return None

def get_date(date_str):
    # Month mapping: French, English, and more
    months = {
        # French
        'janvier': 1, 'janv.': 1,
        'février': 2, 'févr.': 2,
        'mars': 3,
        'avril': 4,
        'mai': 5,
        'juin': 6, 'jun': 6,
        'juillet': 7, 'juil.': 7, 'jul': 7,
        'août': 8,
        'septembre': 9, 'sept.': 9,
        'octobre': 10, 'oct.': 10,
        'novembre': 11, 'nov.': 11,
        'décembre': 12, 'déc.': 12,
        # English/International
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
        # Spanish
        'enero': 1, 'ene.': 1,
        'febrero': 2, 'feb.': 2,
        'marzo': 3, 'mar.': 3,
        'abril': 4, 'abr.': 4,
        'mayo': 5, 'may.': 5,
        'junio': 6, 'jun.': 6,
        'julio': 7, 'jul.': 7,
        'agosto': 8, 'ago.': 8,
        'septiembre': 9, 'sep.': 9,
        'octubre': 10, 'oct.': 10,
        'noviembre': 11, 'nov.': 11,
        'diciembre': 12, 'dic.': 12,
        # Romanian
        'ian.': 1, 'feb.': 2, 'mart.': 3, 'apr.': 4, 'mai': 5, 'iun.': 6,
        'iul.': 7, 'aug.': 8, 'sept.': 9, 'oct.': 10, 'nov.': 11, 'dec.': 12,
    }

    today = date.today()
    date_str = date_str.strip().lower()
    
    if date_str in ["aujourd'hui", "plus tôt aujourd'hui", "today"]:
        return today
    if date_str == "hier" or date_str == "yesterday":
        return today - timedelta(days=1)
    if date_str == "demain" or date_str == "tomorrow":
        return today + timedelta(days=1)
    
    # Case 1: "14 juin", "jun 14", "14 juil.", "jul 14"
    match = re.match(r"^(\d{1,2})\s*([a-zéû.]+)$", date_str)
    if match:
        day, month_str = int(match.group(1)), match.group(2)
        month = months.get(month_str)
        if month:
            return date(today.year, month, day)
    
    match = re.match(r"^([a-zéû.]+)\s*(\d{1,2})$", date_str)
    if match:
        month_str, day = match.group(1), int(match.group(2))
        month = months.get(month_str)
        if month:
            return date(today.year, month, day)
    
    # Case 2: "14 thg 6" (Vietnamese: 'thg' means 'month')
    match = re.match(r"^(\d{1,2})\s*thg\s*(\d{1,2})$", date_str)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        return date(today.year, month, day)
    
    # Case 3: "14. 6." or "14.6." (Czech/German style)
    match = re.match(r"^(\d{1,2})\.\s*(\d{1,2})\.$", date_str)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        return date(today.year, month, day)

    # Case 4: "6月14日" (Chinese/Japanese: month, day)
    match = re.match(r"^(\d{1,2})月(\d{1,2})日$", date_str)
    if match:
        month, day = int(match.group(1)), int(match.group(2))
        return date(today.year, month, day)

    # Case 5: "14. 6." (sometimes with no trailing dot)
    match = re.match(r"^(\d{1,2})\.\s*(\d{1,2})\.?$", date_str)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        return date(today.year, month, day)

    raise ValueError(f"Unrecognized date format: {date_str}")

def get_tournament(league, tournaments):
    for tournament in tournaments:
        if league.lower() in tournament.name.lower():
            return tournament
    return None

class Command(BaseCommand):
    help = "Import matches stats from gol.gg"
    def handle(self, *args, **options):

        headers = {
            "Accept-Language": "fr-FR,fr;q=0.9",
            'User-Agent': 'Mozilla/5.0',
            }
        url = "https://lolesports.com/fr-FR/leagues/emea_masters,first_stand,lck,lcp,lcs,lec,lpl,lta_cross,lta_n,lta_s,msi,worlds"

        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')

        sects = soup.find_all('section' , attrs={"data-tag": True})


        tournaments = Tournament.objects.filter(
                date_ended__gte=datetime.today(),
                date_started__lte=date.today() + timedelta(days=5),
            )
        rosters_map = set()

        for sect in sects:
            date_matches = get_date(sect['data-date'])
            if date_matches > date.today():



                divs = []
                for sib in sect.find_next_siblings():
                    if sib.name == "section" or sib.get_text()=="Charger plus":
                        break
                    if sib.name == "div":
                        divs.append(sib)

                for div in divs:
                    footer = div.find('footer')
                    league_str = footer.find('img')['alt']
                    tournament = get_tournament(league_str, tournaments)

                    obj_matchday, created_matchday = MatchDay.objects.get_or_create(
                        date=date_matches,
                        tournament=tournament,
                    )

                    rosters = Roster.objects.filter(tournament=tournament)
                    team_name_to_roster = {r.team.name: r for r in rosters}
                    normalized_map = {normalize_team_name(k): v for k,v in team_name_to_roster.items()}
                    

                    bo_str = footer.find_all('p')[-1].get_text()
                    time = div.find('time')
                    dt = datetime.fromisoformat(time['datetime'].replace("Z", "+00:00"))
                    img_tags = div.find_all('img')
                    blue_str = img_tags[0]['alt']
                    red_str = img_tags[1]['alt']
                    


                    blue_roster = find_closest_team_roster(blue_str, normalized_map, 0.6)
                    red_roster = find_closest_team_roster(red_str, normalized_map, 0.6)
                    if not blue_roster:
                        blue_alt_str = img_tags[0].parent.get_text()
                        blue_roster = find_closest_team_roster(blue_alt_str, normalized_map, 0.9)
                        if not blue_roster:
                            self.stdout.write(self.style.WARNING(f"Roster not found for : {blue_str}"))
                            continue
                    if not red_roster:
                        red_alt_str = img_tags[1].parent.get_text()
                        red_roster = find_closest_team_roster(red_alt_str, normalized_map, 0.9)
                        if not red_roster :
                            self.stdout.write(self.style.WARNING(f"Roster not found for:{red_str}"))
                            continue

                    match_name = f"{blue_roster.team.name} VS {red_roster.team.name} ({tournament.name})"

                    obj_match, created_match = Match.objects.get_or_create(
                        match_day=obj_matchday,
                        blue_roster=blue_roster,
                        red_roster=red_roster,
                        defaults={
                            'scheduled_hour': dt.time(),
                            'name': match_name,
                            'best_of': int(bo_str[-1]),
                        }
                    )
                    if created_match:
                        print(f"[CREATED] Upcoming match: {blue_roster.team.name} vs {red_roster.team.name} on {date_matches}")
                    else:
                        print(f"[SKIP] Upcoming match already exists: {blue_roster.team.name} vs {red_roster.team.name} on {date_matches}")
                    



