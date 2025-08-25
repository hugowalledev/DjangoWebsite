from django.core.management.base import BaseCommand
from esport.models import Tournament, Champion, Team

class Command(BaseCommand):
    help = "Fix static paths for tournament, champion, and team logos"

    def handle(self, *args, **kwargs):
        updated = 0

        for t in Tournament.objects.all():
            if t.logo and not t.logo.startswith("static/"):
                t.logo = f"static/tournaments/{t.logo.split('/')[-1]}"
                t.save()
                updated += 1

        for c in Champion.objects.all():
            if c.icon and not c.icon.startswith("static/"):
                c.icon = f"static/champions/{c.icon.split('/')[-1]}"
                c.save()
                updated += 1

        for team in Team.objects.all():
            if team.logo and not team.logo.startswith("static/"):
                team.logo = f"static/teams/{team.logo.split('/')[-1]}"
                team.save()
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"✅ Fixed {updated} paths."))