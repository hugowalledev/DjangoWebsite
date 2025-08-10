import os
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from esport.models import Tournament
from django.utils.text import slugify

def parse_liquipedia_dates(date_str):
    # Normalize dashes and whitespace
    date_str = date_str.replace('–', '-').replace('—', '-').replace('\u2013', '-').replace('\u2014', '-')
    date_str = re.sub(r'\s*-\s*', ' - ', date_str)  # normalize spaces around dash
    date_str = date_str.replace('\xa0', ' ').strip()

    if not date_str or not date_str.strip():
        return None, None
    # Remove "TBD", "Cancelled", etc
    if "TBD" in date_str or "Cancelled" in date_str:
        return None, None

    
    # Pattern 1: "May 1 - May 19, 2024"
    m = re.match(r"([A-Za-z]+) (\d{1,2}) - ([A-Za-z]+) (\d{1,2}), (\d{4})", date_str)
    if m:
        month1, day1, month2, day2, year = m.groups()
        start = datetime.strptime(f"{month1} {day1} {year}", "%b %d %Y").date()
        end = datetime.strptime(f"{month2} {day2} {year}", "%b %d %Y").date()
        return start, end

    # Pattern 2: "May 17 - 20, 2018"
    m = re.match(r"([A-Za-z]+) (\d{1,2}) - (\d{1,2}), (\d{4})", date_str)
    if m:
        month, day1, day2, year = m.groups()
        start = datetime.strptime(f"{month} {day1} {year}", "%b %d %Y").date()
        end = datetime.strptime(f"{month} {day2} {year}", "%b %d %Y").date()
        return start, end

    # Pattern 3: "Oct 1, 2023 - Nov 1, 2023"
    m = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4}) - ([A-Za-z]+) (\d{1,2}), (\d{4})", date_str)
    if m:
        month1, day1, year1, month2, day2, year2 = m.groups()
        start = datetime.strptime(f"{month1} {day1} {year1}", "%b %d %Y").date()
        end = datetime.strptime(f"{month2} {day2} {year2}", "%b %d %Y").date()
        return start, end

    # Pattern 4: "May 11, 2018" (single day)
    m = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})$", date_str)
    if m:
        start = datetime.strptime(date_str, "%b %d, %Y").date()
        return start, start

    # Pattern 5: "2023-11-01"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        return dt, dt

    if ' - ' in date_str:
        parts = date_str.split(' - ')
        if len(parts) == 2:
            start, end = parts
            year_match = re.search(r"\d{4}", end)
            if year_match and not re.search(r"\d{4}", start):
                start = f"{start}, {year_match.group(0)}"
            try:
                date_started = datetime.strptime(start.strip(), "%b %d, %Y").date()
                date_ended = datetime.strptime(end.strip(), "%b %d, %Y").date()
                print("Fallback: Inferred year from end for start date")
                return date_started, date_ended
            except Exception as e:
                print("Failed fallback:", e)
    
    return None, None

def fetch_and_save_logo(obj, image_url, field_name, tournament_name, style, debug_label=""):
    """
    Fetches an image from `image_url`, deletes the existing file (if any),
    and saves the new image to the specified field on `obj`.

    :param obj: Django model instance
    :param image_url: full image URL to download
    :param field_name: string, the name of the ImageField (e.g., 'logo' or 'logo_dark')
    :param tournament_name: used for filename generation
    :param style: self.style object from Django management command
    :param debug_label: optional tag for debug messages
    """
    field = getattr(obj, field_name)
    upload_dir = field.field.upload_to
    filename = f"{slugify(tournament_name)}{'-' + debug_label if debug_label else ''}.png"
    full_path = os.path.join(settings.MEDIA_ROOT, upload_dir, filename)

    # Remove existing file
    try:
        if os.path.exists(full_path):
            os.remove(full_path)
    except Exception as e:
        print(style.WARNING(f"Error deleting {full_path}: {e}"))

    # Download and save new image
    response = requests.get(image_url)
    if response.status_code == 200:
        field.save(filename, ContentFile(response.content), save=True)
        print(style.NOTICE(f"[DEBUG] {debug_label} logo saved: {field.name}"))
    else:
        print(style.NOTICE(f"[DEBUG] Could not fetch {debug_label} logo: {image_url}"))
def get_tournament_league(link, headers):
    res = requests.get(link, headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    div = soup.find(text="Series:")
    if not div:
        return None
    return div.findNext('div').get_text(strip=True)

class Command(BaseCommand):
    help = "Imports S-Tier tournaments from Liquipedia and saves to Tournament model."
    def handle(self, *args, **options):
        url = "https://liquipedia.net/leagueoflegends/S-Tier_Tournaments"
        headers={'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        grid_tables = soup.select("div.gridTable")
        count = 0
        for grid_table in grid_tables:
            for row in grid_table.select('.gridRow'):
                cells = row.find_all("div", class_="gridCell")
                if len(cells) < 1:
                    continue
                a_tags = cells[0].find_all('a')

                if not a_tags: 
                    continue
                tournament_link = a_tags[-1]
                tournament_name = tournament_link.text.strip()
                tournament_slug = slugify(tournament_name)
                
                
                liquipedia_url = "https://liquipedia.net" + tournament_link.get("href", "")
                date_str = cells[1].get_text(strip=True)
                start_date, end_date = parse_liquipedia_dates(date_str)
                tournament_league = get_tournament_league(liquipedia_url, headers)
                tournament_split = tournament_name.replace(str(start_date.year),"").replace(tournament_league,"").strip().replace(" ","_")
                obj, created = Tournament.objects.update_or_create(
                    slug=tournament_slug,
                    defaults={
                        'name': tournament_name,
                        'league': tournament_league,
                        'year': start_date.year,
                        'split': tournament_split,
                        'date_started': start_date,
                        'date_ended': end_date,
                        'liquipedia_url': liquipedia_url,
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(
                        f"Created: {tournament_name} | {start_date} - {end_date} | {liquipedia_url}"
                    ))
                    count += 1
                else:
                    self.stdout.write(self.style.NOTICE(
                        f"Exists: {tournament_name}"
                    ))

                tournament_dark = cells[0].find('span', class_="darkmode")
                tournament_logo = cells[0].find('img')
                # Light logo
                tournament_logo_url = f"https://liquipedia.net{tournament_logo['src']}"
                fetch_and_save_logo(obj, tournament_logo_url, "logo", tournament_name, self.style)

                # Dark logo
                if tournament_dark:
                    tournament_dark_logo = tournament_dark.find('img')
                    if tournament_dark_logo:
                        tournament_dark_logo_url = f"https://liquipedia.net{tournament_dark_logo['src']}"
                        fetch_and_save_logo(obj, tournament_dark_logo_url, "logo_dark", tournament_name, self.style, debug_label="dark")


        self.stdout.write(self.style.SUCCESS(f"\nImported {count} tournaments."))
 