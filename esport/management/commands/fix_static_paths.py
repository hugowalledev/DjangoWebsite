from django.core.management.base import BaseCommand
from esport.models import Tournament, Champion, Team

from django.core.management.base import BaseCommand
from esport.models import Tournament, Champion, Team

class Command(BaseCommand):
    help = "Fix static paths for tournament, champion, and team logos"

    def handle(self, *args, **kwargs):
        updated = 0

        for t in Tournament.objects.all():
            if t.logo and not t.logo.name.startswith("static/"):
                t.logo.name = f"static/tournaments/{t.logo.name.split('/')[-1]}"
                t.save()
                updated += 1
            if t.logo_dark and not t.logo_dark.name.startswith("static/"):
                t.logo_dark.name = f"static/tournaments/{t.logo_dark.name.split('/')[-1]}"
                t.save()
                updated += 1

        for c in Champion.objects.all():
            if c.image and not c.image.name.startswith("static/"):
                c.image.name = f"static/champions/{c.image.name.split('/')[-1]}"
                c.save()
                updated += 1

        for team in Team.objects.all():
            if team.logo and not team.logo.name.startswith("static/"):
                team.logo.name = f"static/teams/{team.logo.name.split('/')[-1]}"
                team.save()
                updated += 1
            if team.logo_dark and not team.logo_dark.name.startswith("static/"):
                team.logo_dark.name = f"static/teams/{team.logo_dark.name.split('/')[-1]}"
                team.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Fixed {updated} paths."))
