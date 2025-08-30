import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
import difflib
from django.core.management.base import BaseCommand
from django.db import transaction
from esport.models import  Champion, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Team, Tournament
import unicodedata
from urllib.parse import quote

def normalize_team_name(name):
    # Lowercase, remove apostrophes/accents, trim spaces, remove sponsors
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "").replace(" ","")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"^(movistar|team|esports|club|fc|ac|the)\s+", "", name)
    
    return name

def find_closest_team_roster(scraped_team_name, normalized_map, cutoff):

    target_norm = normalize_team_name(scraped_team_name)
    # Try exact match first
    
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
    }

    today = date.today()
    date_str = date_str.strip().lower()
    
    if date_str in ["aujourd'hui", "plus tôt aujourd'hui", "today"]:
        return today
    if date_str == "hier" or date_str == "yesterday":
        return today - timedelta(days=1)
    if date_str == "demain" or date_str == "tomorrow":
        return today + timedelta(days=1)
    
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

        try:
            res = requests.get(url, headers=headers)
            res.raise_for_status()  # Raises HTTPError if not 2xx
        except requests.RequestException as e:
            print(f"Request failed for {url}: {e}")
            return  # or handle accordingly
        soup = BeautifulSoup(res.text, 'html.parser')

        sects = soup.find_all('section' , attrs={"data-tag": True})
        if not sects:
            print("[DEBUG] no <section data-tag=True> found in page!")
            


        tournaments = Tournament.objects.filter(
                date_ended__gte=datetime.today(),
                date_started__lte=date.today() + timedelta(days=5),
            )
        
        tournament_roster_cache = {}
        for tournament in tournaments:
            rosters = Roster.objects.filter(tournament=tournament)
            normalized_map = {normalize_team_name(r.team.name): r for r in rosters}
            tournament_roster_cache[tournament.pk] = {
                "normalized_map": normalized_map
            }
        
        for date_sect in sects:
            with transaction.atomic():
                date_matches = get_date(date_sect['data-date'])
                print(date_matches, date_sect['data-date'])
                if date_matches > date.today():



                    match_divs = []
                    for sib in date_sect.find_next_siblings():
                        if sib.name == "section" or sib.get_text()=="Charger plus":
                            break
                        if sib.name == "div":
                            match_divs.append(sib)

                    for div in match_divs:
                        match_footer = div.find('footer')
                        if not match_footer:
                            print("[DEBUG] no <match_footer> found")
                            continue
                        league_str = match_footer.find('img')['alt']
                        tournament = get_tournament(league_str, tournaments)
                        
                        cache = tournament_roster_cache[tournament.pk]
                        normalized_map = cache["normalized_map"]

                        obj_matchday, created_matchday = MatchDay.objects.get_or_create(
                            date=date_matches,
                            tournament=tournament,
                        )

                        
                        

                        best_of_str = match_footer.find_all('p')[-1].get_text()
                        match_time_tag = div.find('time')
                        scheduled_datetime = datetime.fromisoformat(match_time_tag['datetime'].replace("Z", "+00:00"))
                        team_logo_imgs = div.find_all('img')
                        if not best_of_str:
                            print("[DEBUG] no <p> found (best_of_str)")
                            continue

                        if not match_time_tag:
                            print("[DEBUG] no <match_time_tag> found")
                            continue

                        if not team_logo_imgs:
                            print("[DEBUG] no <team_logo_imgs> found")
                            continue

                        blue_team_name = team_logo_imgs[0]['alt']
                        red_team_name = team_logo_imgs[1]['alt']
                        


                        blue_roster = find_closest_team_roster(blue_team_name, normalized_map, 0.8)
                        red_roster = find_closest_team_roster(red_team_name, normalized_map, 0.8)
                        if not blue_roster:
                            blue_alt_str = team_logo_imgs[0].parent.get_text()
                            blue_roster = find_closest_team_roster(blue_alt_str, normalized_map, 0.9)
                            if not blue_roster:
                                self.stdout.write(self.style.WARNING(f"Roster not found for : {blue_team_name}"))
                                continue
                        if not red_roster:
                            red_alt_str = team_logo_imgs[1].parent.get_text()
                            red_roster = find_closest_team_roster(red_alt_str, normalized_map, 0.9)
                            if not red_roster :
                                self.stdout.write(self.style.WARNING(f"Roster not found for:{red_team_name}"))
                                continue
                        blue_roster_players = RosterPlayer.objects.filter(roster=blue_roster)
                        red_roster_players = RosterPlayer.objects.filter(roster=red_roster)
                        
                        if blue_roster_players.count() < 5:
                            self.stdout.write(self.style.WARNING(f"Team not complete yet:{blue_team_name}"))
                            continue
                        if red_roster_players.count()< 5 :
                            self.stdout.write(self.style.WARNING(f"Team not complete yet:{red_team_name}"))
                            continue

                        match_name = f"{blue_roster.team.name} VS {red_roster.team.name} ({tournament.name})"

                        obj_match, created_match = Match.objects.get_or_create(
                            match_day=obj_matchday,
                            blue_roster=blue_roster,
                            red_roster=red_roster,
                            defaults={
                                'scheduled_hour': scheduled_datetime.time(),
                                'name': match_name,
                                'best_of': int(best_of_str[-1]),
                            }
                        )
                        if created_match:
                            print(f"[CREATED] Upcoming match: {blue_roster.team.name} vs {red_roster.team.name} on {date_matches}")
                        else:
                            print(f"[SKIP] Upcoming match already exists: {blue_roster.team.name} vs {red_roster.team.name} on {date_matches}")
