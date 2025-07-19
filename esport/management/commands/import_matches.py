import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
import difflib
from django.core.management.base import BaseCommand
from esport.models import  Champion, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Team, Tournament
import unicodedata
from urllib.parse import quote

def get_bo(link, headers):
    """
    Detect the 'Best Of' (BO1, BO3, BO5) from a page.
    Returns 1, 3, or 5 (default 1 if not found).
    """
    res = requests.get(link, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    for n in (1, 3, 5):
        if soup.find(text=f"BO{n}"):
            return n
    return 1

def normalize_team_name(name):
    # Lowercase, remove apostrophes/accents, trim spaces, remove sponsors
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"\bs?\b", "", name)   # remove stray s
    name = re.sub(r"\s+", " ", name).strip()
    # Remove prefixes like "movistar", "team", "esports", etc. (customize this)
    name = re.sub(r"^(movistar|team|esports|gaming|club|fc|ac|the)\s+", "", name)
    
    return name

def find_closest_team_roster(scraped_team_name, normalized_map):

    target_norm = normalize_team_name(scraped_team_name)
    # Try exact match first
    print(target_norm)
    if target_norm in normalized_map:
        return normalized_map[target_norm]

    # Fuzzy match
    choices = list(normalized_map.keys())
    match = difflib.get_close_matches(target_norm, choices, n=1, cutoff=0.6)
    if match:
        return normalized_map[match[0]]

    # Substring match as fallback
    for k, v in normalized_map.items():
        if target_norm in k or k in target_norm:
            return v

    return None

class Command(BaseCommand):
    help = "Import matches stats from gol.gg"
    def handle(self, *args, **options):
        headers = {'User-Agent': 'Mozilla/5.0'}

        for tournament in Tournament.objects.filter(
                date_ended__gte=datetime.today(),
                date_started__lte=date.today() + timedelta(days=5),
            ).order_by('date_started'):

            tournament_name_quoted = quote(tournament.name)
            
            rosters = Roster.objects.filter(tournament=tournament)
            team_name_to_roster = {r.team.name: r for r in rosters}
            normalized_map = {normalize_team_name(k): v for k,v in team_name_to_roster.items()}
            url = f"https://gol.gg/tournament/tournament-matchlist/{tournament_name_quoted}/"
            
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')

            tbody = soup.find('tbody')
            if not tbody:
                print("[DEBUG] <tbody> not found in page!")
                continue
            rows = tbody.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                date_str = cols[-1].get_text()
                
                date_match = datetime.strptime(date_str, "%Y-%m-%d").date()
                obj_matchday, created_matchday = MatchDay.objects.get_or_create(
                    date=date_match,
                    tournament=tournament,
                )
                match_ref = cols[0].find('a')
                match_name = match_ref.get_text()
                match_url = match_ref['href'].replace("..","https://gol.gg")
                blue_team_str = cols[1].get_text()
                red_team_str = cols[3].get_text()
                score_str = cols[2].get_text()

                bo_url = match_url.replace("preview/", "summary/")
                match_bo = get_bo(bo_url,headers)
                
                

                blue_roster = find_closest_team_roster(blue_team_str, normalized_map)
                red_roster = find_closest_team_roster(red_team_str, normalized_map)
                if not blue_roster:
                    self.stdout.write(self.style.WARNING(f"Roster not found for: {blue_team_str}"))
                    continue
                if not red_roster:
                    self.stdout.write(self.style.WARNING(f"Roster not found for:{red_team_str}"))
                    continue


                game_played = score_str != " - "

                if not game_played:
                    obj_match, created_match = Match.objects.get_or_create(
                        match_day=obj_matchday,
                        blue_roster=blue_roster,
                        red_roster=red_roster,
                        defaults={
                            'scheduled_hour': time(12,0),
                            'name': match_name,
                            'best_of': match_bo,
                            'golgg_url': match_url,
                        }
                    )
                    if created_match:
                        print(f"[CREATED] Upcoming match: {blue_roster.team.name} vs {red_roster.team.name} on {date_match}")
                    else:
                        print(f"[SKIP] Upcoming match already exists: {blue_roster.team.name} vs {red_roster.team.name} on {date_match}")
                else:
                    
                    winner_str = row.find('td', class_="text_victory").get_text()
                    score_stack = re.match(r"(\d+)\s*-\s*(\d+)", score_str)
                    if blue_team_str == winner_str:
                        winner = blue_roster
                        winner_score = score_stack.group(1)
                        loser = red_roster
                        loser_score = score_stack.group(2)
                    else:
                        winner = red_roster
                        winner_score = score_stack.group(2)
                        loser = blue_roster
                        loser_score = score_stack.group(1)
                        
                    obj_match, created_match = Match.objects.get_or_create(
                        match_day=obj_matchday,
                        blue_roster=blue_roster,
                        red_roster=red_roster,
                        defaults={
                            'scheduled_hour': time(12,0),
                            'name': match_name,
                            'best_of': match_bo,
                            'golgg_url': match_url,
                            'score_str': score_str,
                            'winner': winner,
                            'loser': loser,
                            'is_closed': True,
                            'winner_score': winner_score,
                            'loser_score': loser_score,
                        }
                    )
                    if created_match:
                        print(f"[CREATED] Upcoming match: {blue_roster.team.name} vs {red_roster.team.name} on {date_match}")
                    else:
                        print(f"[SKIP] Upcoming match already exists: {blue_roster.team.name} vs {red_roster.team.name} on {date_match}")




