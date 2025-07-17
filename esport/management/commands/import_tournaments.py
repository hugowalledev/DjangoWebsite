import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup
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

    # Pattern 6: If "Month Day, Year" appears in end only, try using it for both start and end
    if ' - ' in date_str:
        parts = date_str.split(' - ')
        if len(parts) == 2:
            start, end = parts
            # Fill in year for start if not present
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

class Command(BaseCommand):
    help = "Imports S-Tier tournaments from Liquipedia and saves to Tournament model."
    def handle(self, *args, **options):
        url = "https://liquipedia.net/leagueoflegends/S-Tier_Tournaments"
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(res.text, 'html.parser')
        grid_tables = soup.select("div.gridTable")
        count = 0
        # Loop through years and tournament tables
        for grid_table in grid_tables:
            for row in grid_table.select('.gridRow'):
                cells = row.find_all("div", class_="gridCell")
                if len(cells) < 1:
                    continue
                # Tournament Name
                a_tags = cells[0].find_all('a')
                if not a_tags: 
                    continue
                tournament_link = a_tags[-1]
                tournament_name = tournament_link.text.strip()
                tournament_slug = slugify(tournament_name)
                liquipedia_url = "https://liquipedia.net" + tournament_link.get("href", "")
                # Date String
                date_str = cells[1].get_text(strip=True)
                # Parse dates
                start_date, end_date = parse_liquipedia_dates(date_str)
                
                # Save to Django ORM
                obj, created = Tournament.objects.get_or_create(
                    slug=tournament_slug,
                    defaults={
                        'name': tournament_name,
                        'region': '',  # You may parse region if desired
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
        self.stdout.write(self.style.SUCCESS(f"\nImported {count} tournaments."))
    # --- Usage ---
    # In Django shell: >>> fetch_and_populate_tournaments()
