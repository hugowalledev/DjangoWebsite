import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
import difflib
from django.core.management.base import BaseCommand
from esport.models import  Champion, Game, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Team, Tournament
import unicodedata
from urllib.parse import quote
  
def get_game_link(link, headers, i):
    res = requests.get(link, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')


    nav = soup.find(id='gameMenuToggler')
    li_tags = nav.find_all('li')
    return li_tags[i+1].find('a')['href'].replace("..", "https://gol.gg")

def fix_champion(champion_name):
    if champion_name =="KSante":
        return "K'Santé"
    if champion_name == "Kaisa":
        return "Kai'Sa"
    if champion_name == "Chogath":
        return "Cho'Gath"
    if champion_name == "Nunu":
        return "Nunu et Willump"
    if champion_name == "Seraphine":
        return "Séraphine"
    if champion_name == "KhaZix":
        return "Kha'Zix"
    else:
        return champion_name

def create_game_and_stats(link, headers, match, game_number):
    res = requests.get(link, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    blue_side = soup.find('div', class_="col-12 blue-line-header")
    blue_side_name = blue_side.get_text().replace(" ","").replace("-","").replace("WIN", "").replace("LOSS", "")

    team_names = {r.team.name: r for r in [match.blue_roster, match.red_roster]}
    normalized_map = {normalize_team_name(k): v for k,v in team_names.items()}

    blue_side_roster = find_closest_team_roster(blue_side_name, normalized_map)
    red_side_roster = match.red_roster if blue_side_roster == match.blue_roster else match.blue_roster

    if blue_side.get_text().endswith("WIN"):
        winner = blue_side_roster
        loser = red_side_roster
    else:
        winner = red_side_roster
        loser = blue_side_roster

    obj_game, created_game = Game.objects.get_or_create(
                        match=match,
                        game_number=game_number,
                        defaults={'winner': winner, 'loser': loser}
                    )

    if created_game:
        print(f"[CREATED] Game: {winner.team.name} vs {loser.team.name} {game_number}")
    else:
        print(f"[SKIP] Game already exists: {winner.team.name} vs {loser.team.name} {game_number}")
    
    
    #players stats
    divs = soup.find_all('div', class_="col-12 col-md-6")
    players = []
    champions = []
    kdas = []

    for div in divs:
        players += [a.get_text() for a in div.find_all('a', class_="link-blanc")]
        champions += [img ['alt'] for img in div.find_all('img', class_='champion_icon rounded-circle')]
        kdas += [ td.get_text() for td in div.find_all('td', attrs={'style': 'text-align:center'})]

    for i in range(len(players)):
        player_name = players[i]
        champion_name = champions[i]
        kda = kdas[i]

        roster_player = RosterPlayer.objects.filter(roster=match.blue_roster, player__name__iexact=player_name).first()
        if not roster_player:
            # If not in blue, must be red
            roster_player = RosterPlayer.objects.filter(roster=match.red_roster, player__name__iexact=player_name).first()
        if not roster_player:
            print(f"Could not find roster_player for {player_name} in match {match}")
            continue
            
        # Get or create Champion
        print(champion_name)
        champion_name = fix_champion(champion_name)
        champion = Champion.objects.get(name=champion_name)

        # Parse KDA robustly
        kills, deaths, assists = map(int, kda.strip().split("/"))

        obj_stat, created_stat = PlayerStats.objects.get_or_create(
            roster_player=roster_player,
            game=obj_game,
            defaults={
                'champion': champion,
                'kills': kills,
                'deaths': deaths,
                'assists': assists,
            }
        )
        print(f"{'[CREATED]' if created_stat else '[SKIP]'} Stat for {player_name}: {kills}/{deaths}/{assists} as {champion_name}")
        

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
                date_ended__gte=datetime.today() + timedelta(days=-30),
                date_started__lte=date.today(),
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
                matchday, created_match = MatchDay.objects.get_or_create(
                    date=date_match,
                    tournament=tournament,
                )

                match_ref = cols[0].find('a')
                match_url = match_ref['href'].replace("..","https://gol.gg").replace("summary/", "game/")
                blue_team_str = cols[1].get_text()
                red_team_str = cols[3].get_text()
                score_str = cols[2].get_text()

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
                    self.stdout.write(self.style.WARNING(f"Game hasn't been played yet"))
                    continue
                
                    
                winner_str = row.find('td', class_="text_victory").get_text()
                score_stack = re.match(r"(\d+)\s*-\s*(\d+)", score_str)

                if blue_team_str == winner_str:
                    winner = blue_roster
                    winner_score = int(score_stack.group(1))
                    loser = red_roster
                    loser_score = int(score_stack.group(2))
                else:
                    winner = red_roster
                    winner_score = int(score_stack.group(2))
                    loser = blue_roster
                    loser_score = int(score_stack.group(1))

                best_of = 2*winner_score - 1
                print(blue_roster.team.name,red_roster.team.name)
                match, created_match = Match.objects.update_or_create(
                    match_day=matchday,
                    blue_roster=blue_roster,
                    red_roster=red_roster,
                    defaults={
                        'scheduled_hour': time(12,0),
                        'name': f"{blue_roster.team.name} VS {red_roster.team.name} ({tournament.name})",
                        'best_of': best_of,
                        'score_str': score_str,
                        'winner': winner,
                        'is_closed': True,
                        'winner_score': winner_score,
                        'loser_score': loser_score,
                    })
                print(f"match updated: {blue_roster.team.name} vs {red_roster.team.name} on {date_match}")

                number_of_games = winner_score + loser_score


                if match.best_of == 1:
                    create_game_and_stats(match_url, headers, match, 1)
                else:
                    for i in range(number_of_games):
                        create_game_and_stats(get_game_link(match_url, headers, i), headers, match, i+1)
