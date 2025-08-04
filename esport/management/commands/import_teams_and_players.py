import requests
import os
from bs4 import BeautifulSoup
import datetime
from datetime import date, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.core.files.base import ContentFile
from django.utils.text import slugify
from esport.models import Player, Roster, RosterPlayer, Team, Tournament

def get_region(link, headers):
    res = requests.get(link, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')

    div = soup.find(text="Region:")
    if not div:
        div = soup.find(text="Location:")
    if not div:
        return "Unknown"
    return div.findNext('a')['title']

def parse_player_table(table, is_starter, already_seen):
    """Parses a player table (starters or subs) and returns player data."""
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

class Command(BaseCommand):
    help = "Imports Teams and Players from tournaments from Liquipedia and saves them"
    def handle(self, *args, **options):

        headers = {'User-Agent': 'Mozilla/5.0'}
        for tournament in Tournament.objects.filter(date_ended__gte=date.today(), date_started__lte=date.today()+timedelta(days=7)).order_by('date_started'):
            url = tournament.liquipedia_url
            
            try:
                res = requests.get(url, headers=headers)
                res.raise_for_status()
            except requests.RequestException as e:
                print(f"Request failed for {url}: {e}")
                return

            soup = BeautifulSoup(res.text, 'html.parser')
            year = tournament.date_started.year
            self.stdout.write(self.style.NOTICE(
                                    f"Tournament: {tournament.name}"
                                ))

            # Find 'Participating Teams' <h2>
            part_h2 = None
            for h2 in soup.find_all('h2'):
                if 'Participating Teams' in h2.text:
                    part_h2 = h2
                    break
                if 'Participants' in h2.text:
                    part_h2 = h2
                    break
                if 'Participating Players' in h2.text:
                    part_h2 = h2
                    break

            if not part_h2:
                print("Participating Teams section not found!")
                continue

            # Go to the next elements after the h2
            teams_data = []
            sibling = part_h2

            while True:
                sibling = sibling.find_next_sibling()
                if sibling is None or sibling.name == "h2":
                    break

                # Find all teamcards under this sibling (if any)
                teamcards = sibling.find_all("div", class_="teamcard", recursive=True)
                for card in teamcards:
                    
                    with transaction.atomic():
                        # Get team name and link
                        center = card.find("center")
                        if not center:
                            self.stdout.write(self.style.WARNING(f"[WARNING] Team name missing in {tournament.name}, skipping teamcard."))
                            continue

                        team_link_tag = center.find("a")
                        if not team_link_tag:
                            self.stdout.write(self.style.WARNING(f"Team link not found"))
                            continue

                        team_name = team_link_tag.text.strip()
                        team_link = f"https://liquipedia.net{team_link_tag['href']}"
                        team_region = get_region(team_link, headers)
                        if not team_region or team_region == "Unknown":
                            self.stdout.write(self.style.WARNING(f"Team region not found"))
                            continue

                        teamcard_inner = card.find('div', class_='teamcard-inner')
                        if not teamcard_inner:
                            self.stdout.write(self.style.WARNING(f"TeamCard not found for {team_name}"))
                            continue
                        tables = teamcard_inner.find_all('table')
                        team_logo = tables[-1].find('img')
                        team_logo_url = f"https://liquipedia.net{team_logo['src']}"
                        
                        try:
                            obj_team, created_team = Team.objects.get_or_create(
                                name=team_name,
                                defaults={'region': team_region},
                            )
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"DB error for team {team_name}: {e}"))
                            continue

                        filename = f"{slugify(team_name)}.png"
                        upload_dir = obj_team.logo.field.upload_to  
                        full_path = os.path.join(settings.MEDIA_ROOT, upload_dir, filename)

                        # Delete the existing file on disk if it exists (not just from the model)
                        try:
                            if os.path.exists(full_path):
                                os.remove(full_path)
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"Error deleting {full_path}: {e}"))

                        # Now save the new logo
                        response = requests.get(team_logo_url)
                        if response.status_code == 200:
                            obj_team.logo.save(filename, ContentFile(response.content), save=True)
                            self.stdout.write(self.style.NOTICE(f"[DEBUG] New logo saved: {obj_team.logo.name}"))
                        else:
                            self.stdout.write(self.style.NOTICE(f"[DEBUG] Could not fetch logo: {team_logo_url}"))
                        obj_roster, created_roster = Roster.objects.get_or_create(
                            team = obj_team,
                            tournament = tournament,
                            year = year,
                        )
                        table = teamcard_inner.find('table', attrs={"data-toggle-area-content":"1"}) if teamcard_inner else None
                        table_sub = None
                        if len(tables) >= 4 :
                            tr_tags = table.find_all('tr')
                            tr = tr_tags[-1]
                            spans = tr.find_all('span')
                            if not spans:
                                tr = tr_tags[-2]
                                spans = tr.find_all('span')

                            if spans:
                                # Determine which span to use
                                target_span = spans[0] if spans[0].get_text().strip() != "Staff" else spans[1]
                                area = target_span.get('data-toggle-area-btn')

                                if area:
                                    table_sub = teamcard_inner.find('table', attrs={"data-toggle-area-content": area}) 
                            
                        


                        
                        players_to_import = set()
                        players_data = []

                        if table:
                            players_data += parse_player_table(table, True, players_to_import)

                        if table_sub:
                            players_data += parse_player_table(table_sub, False, players_to_import)
                        
                        existing_players = Player.objects.filter(name__in=players_to_import)
                        existing_rps = RosterPlayer.objects.filter(roster=obj_roster)
                        player_map = {p.name: p for p in existing_players}
                        rosterplayer_map = {(rp.player.name, rp.roster_id): rp for rp in existing_rps}
                        for nickname, nationality, role, is_starter in players_data:
                            player = player_map.get(nickname)  
                            rp_key = (nickname, obj_roster.id)      
                            if not player:
                                    player = Player.objects.create(name=nickname, country=nationality)
                                    player_map[nickname] = player
                            if rp_key in rosterplayer_map:
                                obj_rosterplayer = rosterplayer_map[rp_key]
                                created_rosterplayer = False
                            else:
                                obj_rosterplayer = RosterPlayer.objects.create(
                                    roster=obj_roster,
                                    player=player,
                                    is_starter=is_starter,
                                    role=role,
                                )
                                rosterplayer_map[rp_key] = obj_rosterplayer
                                created_rosterplayer = True
                            # Logging
                            if created_rosterplayer:
                                self.stdout.write(self.style.SUCCESS(
                                    f"Created: {nickname} | {role} | Roster: {obj_roster.team.name} tournament: {tournament.name}"
                                ))
                            else:
                                self.stdout.write(self.style.NOTICE(f"Exists: {nickname}"))
                            
