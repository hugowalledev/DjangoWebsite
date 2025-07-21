import requests
import os
from bs4 import BeautifulSoup
import datetime
from datetime import date, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
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

class Command(BaseCommand):
    help = "Imports Teams and Players from tournaments from Liquipedia and saves them"
    def handle(self, *args, **options):

        headers = {'User-Agent': 'Mozilla/5.0'}
        for tournament in Tournament.objects.filter(date_ended__gte=date(2019,4,15), date_started__lte=date.today()+timedelta(days=5)).order_by('date_started'):
            url = tournament.liquipedia_url
            
            res = requests.get(url, headers=headers)
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
                exit()

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
                    # Get team name and link
                    center = card.find("center")
                    team_link_tag = center.find("a") if center else None
                    team_name = team_link_tag.text.strip() if team_link_tag else center.text.strip() if center else "Unknown"
                    team_link = f"https://liquipedia.net{team_link_tag['href']}" if team_link_tag and team_link_tag.get('href') else None
                    team_region = get_region(team_link, headers)
                    teamcard_inner = card.find('div', class_='teamcard-inner')
                    tables = teamcard_inner.find_all('table')
                    team_logo = tables[-1].find('img')
                    team_logo_url = f"https://liquipedia.net{team_logo['src']}" if team_logo and team_logo.get('src') else None
                    

                    obj_team, created_team = Team.objects.get_or_create(
                        name = team_name,
                        defaults={
                            'region': team_region,
                        }
                    )

                    filename = f"{slugify(team_name)}.png"
                    upload_dir = obj_team.logo.field.upload_to  # 'teams'
                    full_path = os.path.join(settings.MEDIA_ROOT, upload_dir, filename)

                    # Delete the existing file on disk if it exists (not just from the model)
                    if os.path.exists(full_path):
                        print(f"[DEBUG] Deleting file on disk: {full_path}")
                        os.remove(full_path)

                    # Now save the new logo
                    response = requests.get(team_logo_url)
                    if response.status_code == 200:
                        obj_team.logo.save(filename, ContentFile(response.content), save=True)
                        print(f"[DEBUG] New logo saved: {obj_team.logo.name}")
                    else:
                        print(f"[DEBUG] Could not fetch logo: {team_logo_url}")
                    obj_roster, created_roster = Roster.objects.get_or_create(
                        team = obj_team,
                        tournament = tournament,
                        year = year,
                    )
                    table = teamcard_inner.find('table', attrs={"data-toggle-area-content":"1"}) if teamcard_inner else None
                    if len(tables) == 4 :
                        table_sub = teamcard_inner.find('table', attrs={"data-toggle-area-content":"2"})
                    else:
                        table_sub = None    
                    
                    
                    players = set()
                    if table:
                        rows = table.find_all('tr')
                        for row in rows:
                            th = row.find('th')
                            td = row.find('td')
                            if not th or not td or td.has_attr('colspan'):
                                continue
                            # Get the role (from <img alt="RoleName"...>)
                            img = th.find('img')
                            role = img['alt'] if img else ""
                            # Get the player (from <a title="PlayerName"...>)
                            a_tags = td.find_all('a', title=True)
                            nationality = td.find('img')['alt']
                            nickname = a_tags[-1].get_text(strip=True) if a_tags else td.get_text(strip=True)
                            if not nickname or not role or nickname == "TBD":
                                continue

                            if nickname in players :
                                continue
                            players.add(nickname)

                            obj_player, created_player = Player.objects.get_or_create(
                                name=nickname,
                                defaults={"country": nationality}
                            )
                            try:
                                obj_rosterplayer, created_rosterplayer = RosterPlayer.objects.get_or_create(
                                    roster=obj_roster,
                                    player=obj_player,
                                    defaults={"is_starter": True, "role": role}
                                )
                                if created_rosterplayer:
                                    self.stdout.write(self.style.SUCCESS(
                                        f"Created: {nickname} | {role} | Roster: {team_name} tournament: {tournament.name}"
                                    ))
                                else:
                                    self.stdout.write(self.style.NOTICE(f"Exists: {nickname}"))
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f"Error for {nickname}: {str(e)}"))
                    if table_sub:
                        rows_sub = table_sub.find_all('tr')
                        for row in rows_sub:
                            th = row.find('th')
                            td = row.find('td')
                            if not th or not td or td.has_attr('colspan'):
                                continue
                            # Get the role
                            img = th.find('img')
                            role = img['alt'] if img else "Unknown"
                            # Get the player
                            a_tags = td.find_all('a', title=True)
                            nationality = td.find('img')['alt']
                            nickname = a_tags[-1].get_text(strip=True)

                            # Defensive
                            if not nickname or not role or nickname == "TBD":
                                continue

                            if nickname in players :
                                continue
                            players.add(nickname)

                            obj_player, created_player = Player.objects.get_or_create(
                                name=nickname,
                                defaults={"country": nationality}
                            )
                            try:
                                obj_rosterplayer, created_rosterplayer = RosterPlayer.objects.get_or_create(
                                    roster=obj_roster,
                                    player=obj_player,
                                    defaults={"is_starter": False, "role": role}
                                )
                                if created_rosterplayer:
                                    self.stdout.write(self.style.SUCCESS(
                                        f"Created: {nickname} | {role} | Roster: {team_name} tournament: {tournament.name}"
                                    ))
                                else:
                                    self.stdout.write(self.style.NOTICE(f"Exists: {nickname}"))
                            except Exception as e:
                                self.stdout.write(self.style.WARNING(f"Error for {nickname}: {str(e)}"))

            # Output all teams and their players
