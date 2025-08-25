import re
import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, time
import difflib
import unicodedata
from urllib.parse import quote
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from esport.models import Champion, Game, Match, MatchDay, PlayerStats, Roster, RosterPlayer, Tournament

# --------------------
# Normalization helpers
# --------------------
@lru_cache(maxsize=None)
def fix_champion(name):
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "").replace("é", "e")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"\s*(et\s*)?(willump)?$", "", name).strip()
    return name

@lru_cache(maxsize=None)
def normalize_team_name(name):
    name = name.strip()
    if name == "TT":
        name = "ThunderTalk Gaming"
    name = name.lower()
    name = name.replace("’", "").replace("'", "").replace("`", "")
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode("utf-8")
    name = re.sub(r"\bs?\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^(movistar|team|esports|gaming|club|fc|ac|the|-)+\s+", "", name)
    return name

# --------------------
# Scraping helpers
# --------------------
def fetch_game_data(session, url, game_number):
    try:
        return game_number, scrape_game_stats(session, url)
    except Exception as e:
        return game_number, {"error": str(e)}

def get_game_link(session, link, i):
    res = session.get(link)
    soup = BeautifulSoup(res.text, 'html.parser')
    nav = soup.find(id='gameMenuToggler')
    li_tags = nav.find_all('li')
    return li_tags[i+1].find('a')['href'].replace("..", "https://gol.gg")

def get_teams(session, link):
    url = link.replace("-game", "-summary")
    res = session.get(url)
    soup = BeautifulSoup(res.text, 'html.parser')
    divs = soup.find_all('div', class_="col-4 col-sm-5 text-center")
    if len(divs) < 2:
        raise Exception(f"Could not find both teams on page: {url}")
    return normalize_team_name(divs[0].get_text(strip=True)), normalize_team_name(divs[1].get_text(strip=True))

def find_closest_team_roster(scraped_team_name, normalized_map):
    if scraped_team_name in normalized_map:
        return normalized_map[scraped_team_name]
    choices = list(normalized_map.keys())
    match = difflib.get_close_matches(scraped_team_name, choices, n=1, cutoff=0.8)
    if match:
        return normalized_map[match[0]]
    for k, v in normalized_map.items():
        if scraped_team_name in k or k in scraped_team_name:
            return v
    return None

def parse_kda(kda_string):
    numbers = re.findall(r"\d+", kda_string)
    if len(numbers) < 3:
        return None, None, None
    return map(int, numbers[:3])

def scrape_game_stats(session, link):
    res = session.get(link)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, 'html.parser')
    blue_side_div = soup.find('div', class_="col-12 blue-line-header")
    player_data = []
    divs = soup.find_all('div', class_="col-12 col-md-6")
    for div in divs:
        div_players = [a.get_text() for a in div.find_all('a', class_="link-blanc")]
        div_champions = [img['alt'] for img in div.find_all('img', class_='champion_icon rounded-circle')]
        div_kdas = [td.get_text() for td in div.find_all('td', attrs={'style': 'text-align:center'})]
        for player, champion, kda in zip(div_players, div_champions, div_kdas):
            player_data.append({"player_name": player, "champion_name": champion, "kda": kda})
    return {"blue_side_text": blue_side_div.get_text() if blue_side_div else "", "player_stats": player_data}

# --------------------
# Persistence helpers
# --------------------
def save_game_and_stats(game_data, match, game_number, normalized_champions, roster_player_map, summary):
    blue_side_name = normalize_team_name(game_data['blue_side_text'].replace("WIN", "").replace("LOSS", ""))
    team_names = {r.team.name: r for r in [match.blue_roster, match.red_roster]}
    normalized_map = {normalize_team_name(k): v for k, v in team_names.items()}
    blue_side_roster = find_closest_team_roster(blue_side_name, normalized_map)
    if blue_side_roster == match.blue_roster:
        red_side_roster = match.red_roster
        side_swapped = False
    else:
        red_side_roster = match.blue_roster
        side_swapped = True
    if game_data['blue_side_text'].endswith("WIN"):
        winner, loser = blue_side_roster, red_side_roster
    else:
        winner, loser = red_side_roster, blue_side_roster

    obj_game, created_game = Game.objects.update_or_create(
        match=match,
        game_number=game_number,
        defaults={'winner': winner, 'loser': loser, 'side_swapped': side_swapped}
    )
    if created_game:
        summary['games_created'] += 1
    else:
        summary['games_skipped'] += 1

    stats_to_create = []
    for data in game_data['player_stats']:
        roster_player = roster_player_map.get(data['player_name'].lower())
        if not roster_player:
            summary['errors'] += 1
            summary['error_details'].append({"type": "roster_player_missing", "player": data['player_name'], "game": game_number})
            continue
        champion = normalized_champions.get(fix_champion(data['champion_name']))
        if not champion:
            summary['errors'] += 1
            summary['error_details'].append({"type": "champion_missing", "champion": data['champion_name'], "game": game_number})
            continue
        kills, deaths, assists = parse_kda(data['kda'])
        if None in (kills, deaths, assists):
            summary['stats_skipped'] += 1
            continue
        stats_to_create.append(PlayerStats(
            roster_player=roster_player,
            game=obj_game,
            champion=champion,
            kills=kills,
            deaths=deaths,
            assists=assists,
        ))
    PlayerStats.objects.bulk_create(stats_to_create, ignore_conflicts=True)
    summary['stats_created'] += len(stats_to_create)

def import_game(session, link, match, game_number, normalized_champions, roster_player_map, summary):
    game_data = scrape_game_stats(session, link)
    save_game_and_stats(game_data, match, game_number, normalized_champions, roster_player_map, summary)

# --------------------
# Command
# --------------------
class Command(BaseCommand):
    help = "Import matches stats from gol.gg"

    def handle(self, *args, **options):
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})

        summary = {"matches_processed": 0, "games_created": 0, "games_skipped": 0, "stats_created": 0, "stats_skipped": 0, "errors": 0, "error_details": []}

        
        normalized_champions = {fix_champion(c.name): c for c in Champion.objects.all()}

        for tournament in Tournament.objects.filter(year=2019).order_by('date_started'):
            self.stdout.write(tournament.name)
            all_roster_players = RosterPlayer.objects.filter(roster__tournament=tournament).select_related("player", "roster")
            global_roster_map = {rp.player.name.lower(): rp for rp in all_roster_players}

            rosters = Roster.objects.filter(tournament=tournament)
            team_name_to_roster = {r.team.name: r for r in rosters}
            normalized_map = {normalize_team_name(k): v for k,v in team_name_to_roster.items()}
            normalized_slug_map = {}
            for r in rosters:
                if r.team.slug:
                    normalized_slug_map[normalize_team_name(r.team.slug)]= r
            url = f"https://gol.gg/tournament/tournament-matchlist/{quote(tournament.name)}/"
            try:
                soup = BeautifulSoup(session.get(url).text, 'html.parser')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Request failed: {e}"))
                continue

            tbody = soup.find('tbody')
            if not tbody:
                continue
            for row in tbody.find_all('tr'):
                with transaction.atomic():
                    cols = row.find_all('td')
                    patch = cols[-2].get_text()
                    if patch == "" and tournament.date_ended > date.today():
                        continue
                    date_match = datetime.strptime(cols[-1].get_text(), "%Y-%m-%d").date()
                    matchday, _ = MatchDay.objects.get_or_create(date=date_match, tournament=tournament)

                    match_ref = cols[0].find('a')
                    if not match_ref:
                        continue
                    match_url = match_ref['href'].replace("..", "https://gol.gg").replace("summary/", "game/")
                    blue_team_str, red_team_str = get_teams(session, match_ref['href'].replace("..", "https://gol.gg"))

                    score_str = cols[2].get_text()
                    victory = row.find('td', class_="text_victory")
                    if not victory:
                        continue
                    score_stack = re.match(r"(\d+)\s*-\s*(\d+)", score_str)
                    blue_roster = find_closest_team_roster(blue_team_str, normalized_map)
                    red_roster = find_closest_team_roster(red_team_str, normalized_map)
                    if not blue_roster:
                        blue_roster = find_closest_team_roster(blue_team_str, normalized_slug_map)
                        if not blue_roster:
                            self.stdout.write(self.style.WARNING(f"Roster not found for:{blue_team_str}"))
                            continue
                    if not red_roster:
                        red_roster = find_closest_team_roster(red_team_str, normalized_slug_map)
                        if not red_roster:
                            self.stdout.write(self.style.WARNING(f"Roster not found for:{red_team_str}"))
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

                    match = Match.objects.filter(
                        Q(match_day=matchday, blue_roster=blue_roster, red_roster=red_roster) |
                        Q(match_day=matchday, blue_roster=red_roster, red_roster=blue_roster)
                    ).first()
                    if not match:
                        continue

                    roster_player_map = {k: v for k, v in global_roster_map.items() if v.roster in [match.blue_roster, match.red_roster]}

                    number_of_games = winner_score + loser_score
                    game_urls = [match_url] if match.best_of == 1 else [get_game_link(session, match_url, i) for i in range(number_of_games)]

                    with ThreadPoolExecutor(max_workers=4) as executor:
                        futures = [executor.submit(fetch_game_data, session, url, i+1) for i, url in enumerate(game_urls)]
                        for f in as_completed(futures):
                            game_number, game_data = f.result()
                            if "error" in game_data:
                                summary["errors"] += 1
                                continue
                            # DB writes happen here (main thread)
                            save_game_and_stats(game_data, match, game_number, normalized_champions, roster_player_map, summary)

                    summary['matches_processed'] += 1

        print("\n==== Import Summary ====")
        for k, v in summary.items():
            print(f"{k}: {v}")
