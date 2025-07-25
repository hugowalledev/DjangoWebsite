from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from esport.models import (
    Tournament, Team, Player, Roster, RosterPlayer, MatchDay, Match, Game,
    PlayerStats, Champion, Prediction, MVPDayVote, MVPResetState
)

from users.models import UserProfile

from datetime import date, timedelta, time
from django.conf import settings
import os

User = get_user_model()


class EsportViewsTestCase(TestCase):
    """
    Functional and integration tests for esport/views.py.
    Tests cover leaderboard, match list, prediction, fantasy, match details, and scoreboard views.
    """

    def setUp(self):
        # Create base test user and log in
        self.user = UserProfile.objects.create_user(username="testuser", password="testpass", email="test@example.com")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")

        # Set up objects for tournaments, teams, rosters, players, matchdays, matches, etc.
        self.tournament = Tournament.objects.create(
            name="Test Tourney", region="Test", date_started=date.today(), date_ended=date.today() + timedelta(days=7), slug="test-tourney"
        )
        self.team1 = Team.objects.create(name="Team Alpha", region="TST", logo="teams/alpha.png")
        self.team2 = Team.objects.create(name="Team Beta", region="TST", logo="teams/beta.png")

        self.roster1 = Roster.objects.create(team=self.team1, tournament=self.tournament, year=2025)
        self.roster2 = Roster.objects.create(team=self.team2, tournament=self.tournament, year=2025)

        self.players_team1 = [
            Player.objects.create(name=f"AlphaP{i}", fullname=f"Alpha {i}", country="KR", photo=f"players/alpha{i}.png")
            for i in range(1, 6)
        ]
        self.players_team2 = [
            Player.objects.create(name=f"BetaP{i}", fullname=f"Beta {i}", country="KR", photo=f"players/beta{i}.png")
            for i in range(1, 6)
        ]
        self.rp_team1 = [
            RosterPlayer.objects.create(roster=self.roster1, player=pl, is_starter=True, role="TOP")
            for pl in self.players_team1
        ]
        self.rp_team2 = [
            RosterPlayer.objects.create(roster=self.roster2, player=pl, is_starter=True, role="TOP")
            for pl in self.players_team2
        ]
        self.matchday = MatchDay.objects.create(date=date.today(), tournament=self.tournament)
        self.match = Match.objects.create(
            name="Alpha vs Beta",
            match_day=self.matchday,
            scheduled_hour=time(18, 0),
            blue_roster=self.roster1,
            red_roster=self.roster2,
            best_of=1
        )
        image_path = os.path.join(settings.BASE_DIR, "esport", "tests", "test_image.png")
        with open(image_path, "rb") as img:
            self.champion = Champion.objects.create(
                name="Ahri",
                image=SimpleUploadedFile("test_image.png", img.read(), content_type="image/png")
            )
        self.game = Game.objects.create(match=self.match, winner=self.roster1, loser=self.roster2, game_number=1)
        self.playerstat = PlayerStats.objects.create(
            roster_player=self.rp_team1[0], game=self.game, champion=self.champion, kills=5, deaths=2, assists=7
        )
        self.prediction = Prediction.objects.create(
            user=self.user, match=self.match, predicted_winner=self.roster1, predicted_score="1 - 0"
        )
        self.mvp_vote = MVPDayVote.objects.create(
            user=self.user, match_day=self.matchday, fantasy_pick=self.rp_team1[0], reset_id=0
        )
        self.reset_state = MVPResetState.objects.create(tournament=self.tournament, reset_id=0)

    def test_leaderboard_function(self):
        """
        Test that leaderboard computation returns correct user, match, and mvp points.
        """
        from esport.views import get_leaderboard
        leaderboard = get_leaderboard(self.tournament)
        self.assertTrue(any(entry['user'] == self.user for entry in leaderboard))
        self.assertTrue(any('points' in entry for entry in leaderboard))

    def test_tournament_list_view(self):
        """
        Test that the tournament list page renders with correct context for ongoing and past tournaments.
        """
        response = self.client.get(reverse("esport:tournamentlist"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("tournaments_going", response.context)
        self.assertIn("tournaments_past", response.context)

    def test_matchlist_view(self):
        """
        Test that the matchlist page loads upcoming and past matches, leaderboard, and user predictions.
        """
        url = reverse("esport:matchlist", args=[self.tournament.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("upcoming_matches", response.context)
        self.assertIn("past_matches", response.context)
        self.assertIn("leaderboard", response.context)
        self.assertIn("user_predictions", response.context)

    def test_prediction_view_get_and_post(self):
        """
        Test GET and POST of PredictionView for fantasy MVP picks and predictions.
        """
        url = reverse("esport:prediction", args=[self.tournament.slug])

        # GET
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("matchdays", response.context)
        self.assertIn("can_pick_mvp_today", response.context)

        # POST - test prediction and MVP save
        match = self.match
        match_id = match.id
        mvp_field = f"fantasy_{self.matchday.id}"
        winner_field = f"winner_{match_id}"
        score_field = f"score_{match_id}"
        post_data = {
            mvp_field: self.rp_team1[1].id,
            winner_field: self.roster1.id,
            score_field: "1 - 0",
        }
        response = self.client.post(url, post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        # After submission, Prediction and MVPDayVote should be present
        self.assertTrue(
            MVPDayVote.objects.filter(user=self.user, match_day=self.matchday, fantasy_pick=self.rp_team1[1]).exists()
        )
        self.assertTrue(
            Prediction.objects.filter(user=self.user, match=match, predicted_score="1 - 0").exists()
        )

    def test_match_detail_view(self):
        """
        Test that match detail page loads, shows games, blue/red players and stats.
        """
        url = reverse("esport:match_detail", args=[self.match.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("games_data", response.context)
        self.assertIn("blue_players", response.context)
        self.assertIn("red_players", response.context)
        self.assertIn("match", response.context)

    def test_tournament_scoreboard_view(self):
        """
        Test that the scoreboard view loads and users with predictions/mvp appear in the table.
        """
        url = reverse("esport:tournament_scoreboard", args=[self.tournament.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("scoreboard_rows", response.context)
        # Ensure current user is in the scoreboard
        self.assertTrue(
            any(row["user"] == self.user for row in response.context["scoreboard_rows"])
        )

    def test_prediction_view_unauth_redirect(self):
        """
        Ensure POST to PredictionView redirects to login if user is not authenticated.
        """
        self.client.logout()
        url = reverse("esport:prediction", args=[self.tournament.slug])
        response = self.client.post(url, {}, follow=False)
        self.assertEqual(response.status_code, 302)  # Should redirect to login

    def test_matchlist_view_404(self):
        """
        Ensure a 404 is returned if an invalid tournament slug is used.
        """
        url = reverse("esport:matchlist", args=["does-not-exist"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_match_detail_404(self):
        """
        Ensure a 404 is returned if an invalid match ID is used.
        """
        url = reverse("esport:match_detail", args=[999999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_tournament_scoreboard_404(self):
        """
        Ensure a 404 is returned for an invalid scoreboard slug.
        """
        url = reverse("esport:tournament_scoreboard", args=["bad-slug"])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirects_for_restricted_views(self):
        """
        Anonymous user should be redirected to login for prediction and fantasy pages.
        """
        self.client.logout()
        url = reverse("esport:prediction", args=[self.tournament.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        # Should be redirected to login page
        self.assertIn("/login", response.url)

    def test_fantasy_pick_hidden_if_match_already_started(self):
        """
        If a match for today has already started, MVP pick form should not be present.
        """
        # Set the match's scheduled time to the past to simulate match already started
        self.match.scheduled_hour = (timezone.now() - timedelta(hours=2)).time()
        self.match.save()
        url = reverse("esport:prediction", args=[self.tournament.slug])
        self.client.login(username="testuser", password="testpass")
        response = self.client.get(url)
        # The context should contain 'can_pick_mvp_today' as False
        self.assertIn("can_pick_mvp_today", response.context)
        self.assertFalse(response.context["can_pick_mvp_today"])

    def test_scoreboard_sorting(self):
        """
        Ensure users are sorted by total score descending in scoreboard.
        """
        # Create another user and give him more points
        user2 = UserProfile.objects.create_user(username="second", email="second@example.com", password="testpass2")
        Prediction.objects.create(user=user2, match=self.match, predicted_winner=self.roster1, predicted_score="1 - 0")
        self.match.winner = self.roster1
        self.match.score_str = "1 - 0"
        self.match.save()
        url = reverse("esport:tournament_scoreboard", args=[self.tournament.slug])
        self.client.login(username="second", password="testpass2")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        scoreboard = response.context["scoreboard_rows"]
        self.assertTrue(scoreboard[0]["total"] >= scoreboard[-1]["total"])

    def test_edge_case_no_matches(self):
        """
        If a tournament has no matches, matchlist and scoreboard should still work.
        """
        # Create a tournament with no matches
        t2 = Tournament.objects.create(
            name="Empty Tourney", region="Test", date_started=date.today(), date_ended=date.today() + timedelta(days=1), slug="empty"
        )
        url_matchlist = reverse("esport:matchlist", args=[t2.slug])
        url_scoreboard = reverse("esport:tournament_scoreboard", args=[t2.slug])
        response1 = self.client.get(url_matchlist)
        response2 = self.client.get(url_scoreboard)
        self.assertEqual(response1.status_code, 200)
        self.assertIn("upcoming_matches", response1.context)
        self.assertEqual(response2.status_code, 200)
        self.assertIn("scoreboard_rows", response2.context)
        self.assertEqual(response2.context["scoreboard_rows"], [])

    def test_matchlist_template_used(self):
        """
        Verify that the correct template is used for the matchlist view.
        """
        url = reverse("esport:matchlist", args=[self.tournament.slug])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "esport/matchlist.html")

    def test_scoreboard_template_used(self):
        """
        Verify that the correct template is used for the scoreboard view.
        """
        url = reverse("esport:tournament_scoreboard", args=[self.tournament.slug])
        response = self.client.get(url)
        self.assertTemplateUsed(response, "esport/tournament_scoreboard.html")

