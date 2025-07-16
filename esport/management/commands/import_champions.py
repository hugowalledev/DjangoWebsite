from django.core.management.base import BaseCommand
import requests
from esport.models import Champion
from django.core.files.base import ContentFile

class Command(BaseCommand):
    help = "Import or update League of Legends champions from Riot Data Dragon."

    def handle(self, *args, **options):
        versions = requests.get("https://ddragon.leagueoflegends.com/api/versions.json").json()
        latest_version = versions[0]
        self.stdout.write(self.style.SUCCESS(f"Latest patch: {latest_version}"))

        champion_data = requests.get(
            f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/data/fr_FR/champion.json"
        ).json()["data"]

        created, updated = 0, 0

        for champ in champion_data.values():
            name = champ["name"]
            image_filename = champ["image"]["full"]
            image_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/img/champion/{image_filename}"

            img_resp = requests.get(image_url)
            image_content = ContentFile(img_resp.content, name=image_filename) if img_resp.status_code == 200 else None

            obj, was_created = Champion.objects.get_or_create(name=name)
            if image_content:
                obj.image.save(image_filename, image_content, save=True)
            else:
                obj.save()
            if was_created:
                created+=1
            else:
                updated+=1
        self.stdout.write(self.style.SUCCESS(f"Champions imported! Created: {created}, Updated: {updated}"))