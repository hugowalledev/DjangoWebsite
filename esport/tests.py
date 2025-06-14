from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Tournament, Team, Player, Match

def create_tournament(name, region, days, slug):
    """
    Create a tournament with `name`, `region` it takes place, published the
    given number of `days`offset to now ( negative for past and positive for
    the ones incoming) and `slug`.
    """
    time = timezone.now() + datetime.timedelta(days=days)
    return Tournament.objects.create(name=name, region=region, date = time, slug=slug)

class TournamentEventsViewTests(TestCase):
    def test_no_tournaments(self):
        """
        If no tournaments exist, an appropriate message is displayed.
        """
        response = self.client.get(reverse("esport:tournamentlist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No tournament now")
        self.assertQuerySetEqual(response.context["tournaments_going"],[])
    