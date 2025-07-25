from datetime import date, time
from django.test import TestCase
from esport.forms import MatchPredictionForm
from esport.models import Team, Match, Tournament, Roster, MatchDay

class MatchPredictionFormTest(TestCase):
    def setUp(self):
        # Set up minimal Tournament, MatchDay, Roster, and Team instances for testing
        self.tournament = Tournament.objects.create(
            name="Test Tournament",
            region="World",
            date_started="2025-01-01",
            date_ended="2025-12-31",
            slug="test-tournament"
        )
        self.matchday = MatchDay.objects.create(date=date(2025,6,15), tournament=self.tournament)
        self.team1 = Team.objects.create(name="Team Alpha", region="EU", logo="teams/a.png")
        self.team2 = Team.objects.create(name="Team Beta", region="EU", logo="teams/b.png")
        self.roster1 = Roster.objects.create(team=self.team1, tournament=self.tournament, year=2025)
        self.roster2 = Roster.objects.create(team=self.team2, tournament=self.tournament, year=2025)
        self.match = Match.objects.create(
            name="Alpha vs Beta",
            match_day=self.matchday,
            scheduled_hour=time(18,0),
            blue_roster=self.roster1,
            red_roster=self.roster2,
            best_of=1
        )

    def test_predicted_winner_queryset_limited_to_match_teams(self):
        """
        The 'predicted_winner' field should only allow selection between the two teams involved in the match.
        """
        form = MatchPredictionForm(match=self.match)
        qs = form.fields["predicted_winner"].queryset
        self.assertIn(self.team1, qs)
        self.assertIn(self.team2, qs)
        self.assertEqual(qs.count(), 2)

    def test_match_id_field_initialization(self):
        """
        The hidden match_id field should be initialized with the match's ID.
        """
        form = MatchPredictionForm(match=self.match)
        self.assertEqual(form.fields["match_id"].initial, self.match.id)

    def test_form_validation_with_valid_data(self):
        """
        The form should validate when provided with a valid winner and scores within allowed limits.
        """
        form = MatchPredictionForm(
            data={
                "match_id": self.match.id,
                "predicted_winner": self.team1.id,
                "predicted_score_winner": 2,
                "predicted_score_loser": 1,
            },
            match=self.match
        )
        self.assertTrue(form.is_valid())

    def test_form_rejects_out_of_range_scores(self):
        """
        The form should reject scores outside the allowed 0-5 range.
        """
        form = MatchPredictionForm(
            data={
                "match_id": self.match.id,
                "predicted_winner": self.team1.id,
                "predicted_score_winner": 10,   # Invalid, above max
                "predicted_score_loser": -2,    # Invalid, below min
            },
            match=self.match
        )
        self.assertFalse(form.is_valid())
        self.assertIn("predicted_score_winner", form.errors)
        self.assertIn("predicted_score_loser", form.errors)

    def test_form_requires_predicted_winner(self):
        """
        The form should require that a predicted winner be specified.
        """
        form = MatchPredictionForm(
            data={
                "match_id": self.match.id,
                "predicted_score_winner": 1,
                "predicted_score_loser": 0,
            },
            match=self.match
        )
        self.assertFalse(form.is_valid())
        self.assertIn("predicted_winner", form.errors)
