import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time, timedelta
import difflib
from django.core.management.base import BaseCommand
from django.db import transaction
from esport.models import  Champion, Game, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Team, Tournament
import unicodedata
from urllib.parse import quote
  
def get_game_link(link, headers, i):
    res = requests.get(link, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')


    nav = soup.find(id='gameMenuToggler')
    li_tags = nav.find_all('li')
    return li_tags[i+1].find('a')['href'].replace("..", "https://gol.gg")

def fix_champion(name):
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "").replace("é","e")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"\s*(et\s*)?(willump)?$", "", name).strip()
    
    return name

def normalize_team_name(name):
    # Lowercase, remove apostrophes/accents, trim spaces, remove sponsors
    name = name.strip()
    if name == "TT":
        name = "ThunderTalk Gaming"
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

def parse_kda(kda_string):
    numbers = re.findall(r"\d+", kda_string)
    if len(numbers) < 3:
        return None, None, None  # or raise
    return map(int, numbers[:3])

def scrape_game_stats(link, headers):
    try:
        res = requests.get(link, headers=headers)
        res.raise_for_status()  # Raises HTTPError if not 2xx
    except requests.RequestException as e:
        print(f"Request failed for {link}: {e}")
        return  # or handle accordingly
    soup = BeautifulSoup(res.text, 'html.parser')

    #Parse team name on blue_side
    blue_side_div = soup.find('div', class_="col-12 blue-line-header")
    if not blue_side_div:
        print(f"Could not find blue_side_div for {link}")

    #players stats
    player_data=[]
    divs = soup.find_all('div', class_="col-12 col-md-6")
    for div in divs:
        div_players = [a.get_text() for a in div.find_all('a', class_="link-blanc")]
        div_champions = [img ['alt'] for img in div.find_all('img', class_='champion_icon rounded-circle')]
        div_kdas = [ td.get_text() for td in div.find_all('td', attrs={'style': 'text-align:center'})]
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



def save_game_and_stats(game_data, match, game_number, normalized_champions, roster_player_map, summary):
    
    blue_side_text = game_data['blue_side_text']
    blue_side_name = blue_side_text.replace(" ","").replace("-","").replace("WIN", "").replace("LOSS", "")

    team_names = {r.team.name: r for r in [match.blue_roster, match.red_roster]}
    normalized_map = {normalize_team_name(k): v for k,v in team_names.items()}
    blue_side_name = normalize_team_name(blue_side_name)
    blue_side_roster = find_closest_team_roster(blue_side_name, normalized_map)

    if blue_side_roster == match.blue_roster :
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
                        defaults={'winner': winner, 'loser': loser, 'side_swapped': side_swapped}
                    )
    if created_game:
        summary['games_created'] += 1
    else:
        summary['games_skipped'] += 1 
    

    for data in game_data['player_stats']:
        player_name = data['player_name']
        champion_name = data['champion_name']
        kda = data['kda']

        roster_player = roster_player_map.get(player_name.lower())
        if not roster_player:
            summary['error_details'].append({
                "type": "roster_player_missing",
                "player_name": player_name,
                "team": team,
                "match": str(match),
                "game_number": game_number,
            })
            summary['errors'] += 1
            continue
            
        # Get Champion
        normalized_name = fix_champion(champion_name)
        champion = normalized_champions.get(normalized_name)
        if not champion:
            summary['error_details'].append({
                "type": "champion_missing",
                "champion_name": champion_name,
                "normalized_name": normalized_name,
                "player_name": player_name,
                "match": str(match),
                "game_number": game_number,
            })
            summary['errors'] += 1
            continue
        
        # Parse KDA
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
            }
        )
        if created_stat:
            summary['stats_created'] += 1
        else:
            summary['stats_skipped'] += 1

def import_game(link, headers, match, game_number, normalized_champions, roster_player_map, summary):
    parsed = scrape_game_stats(link, headers)
    save_game_and_stats(parsed, match, game_number, normalized_champions, roster_player_map, summary)


class Command(BaseCommand):
    help = "Import matches stats from gol.gg"
    def handle(self, *args, **options):

        summary = {
            'matches_processed': 0,
            'games_created': 0,
            'games_skipped': 0,
            'stats_created': 0,
            'stats_skipped': 0,
            'errors': 0,
            'error_details': [],
        }
        headers = {'User-Agent': 'Mozilla/5.0'}

        normalized_champions = {fix_champion(c.name): c for c in Champion.objects.all()}

        for tournament in Tournament.objects.filter(
                date_ended__gte=datetime.today() + timedelta(days=-30),
                date_started__lte=date.today(),
            ).order_by('date_started'):

            tournament_name_quoted = quote(tournament.name)
            
            rosters = Roster.objects.filter(tournament=tournament)
            team_name_to_roster = {r.team.name: r for r in rosters}
            normalized_map = {normalize_team_name(k): v for k,v in team_name_to_roster.items()}
            url = f"https://gol.gg/tournament/tournament-matchlist/{tournament_name_quoted}/"
            try:
                res = requests.get(url, headers=headers)
                res.raise_for_status()  # Raises HTTPError if not 2xx
            except requests.RequestException as e:
                print(f"Request failed for {url}: {e}")
                return  # or handle accordingly
            soup = BeautifulSoup(res.text, 'html.parser')

            tbody = soup.find('tbody')
            if not tbody:
                print("[DEBUG] <tbody> not found in page!")
                continue
            rows = tbody.find_all('tr')
            for row in rows:
                with transaction.atomic():
                    cols = row.find_all('td')
                    date_str = cols[-1].get_text()
                    
                    date_match = datetime.strptime(date_str, "%Y-%m-%d").date()
                    matchday, created_match = MatchDay.objects.get_or_create(
                        date=date_match,
                        tournament=tournament,
                    )
                    

                    match_ref = cols[0].find('a')
                    match_url = match_ref['href'].replace("..","https://gol.gg").replace("summary/", "game/")
                    blue_team_str = normalize_team_name(cols[1].get_text())
                    red_team_str = normalize_team_name(cols[3].get_text())
                    score_str = cols[2].get_text()
                    patch = cols[-2].get_text()

                    blue_roster = find_closest_team_roster(blue_team_str, normalized_map)
                    red_roster = find_closest_team_roster(red_team_str, normalized_map)
                    if not blue_roster:
                        self.stdout.write(self.style.WARNING(f"Roster not found for: {blue_team_str}"))
                        continue
                    if not red_roster:
                        self.stdout.write(self.style.WARNING(f"Roster not found for:{red_team_str}"))
                        continue



                    if patch == "":
                        continue
                    
                        
                    winner_str = normalize_team_name(row.find('td', class_="text_victory").get_text())
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
                    summary['matches_processed'] += 1

                    number_of_games = winner_score + loser_score

                    roster_player_map = {}
                    for rp in RosterPlayer.objects.filter(roster__in=[match.blue_roster, match.red_roster]):
                        roster_player_map[rp.player.name.lower()] = rp


                    if match.best_of == 1:
                        import_game(match_url, headers, match, 1, normalized_champions, roster_player_map, summary)
                    else:
                        for i in range(number_of_games):
                            import_game(get_game_link(match_url, headers, i), headers, match, i+1, normalized_champions, roster_player_map, summary)

        print("\n==== Import Summary ====")
        for k, v in summary.items():
            print(f"{k.replace('_', ' ').capitalize()}: {v}")
        if summary.get("error_details"):
            print("\n---- Error Details ----")
            for err in summary["error_details"]:
                if isinstance(err, dict):
                    err_type = err.get("type", "Unknown error")
                    details = ", ".join(f"{k}: {v}" for k, v in err.items() if k != "type")
                    print(f"[{err_type}] {details}")
                else:
                    print(err)