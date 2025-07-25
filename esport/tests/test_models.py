# esport/tests/test_models.py

from django.test import TestCase
from django.utils import timezone
from datetime import date, datetime, time
from esport.models import (
    Tournament, Team, Player, Roster, RosterPlayer, MatchDay, Match, Game,
    PlayerStats, Champion, Prediction, MVPDayVote, MVPResetState
)
from users.models import UserProfile

class ModelTests(TestCase):
    """
    Test suite for esport.models. Each test validates
    model instantiation, relationships, custom methods, and constraints.
    """

    def setUp(self):
        """
        Initializes a minimal, valid test database for all model relationships.
        """
        # Create a sample user profile
        self.user = UserProfile.objects.create(username="testuser", email="test@example.com")

        # Create a tournament and teams
        self.tournament = Tournament.objects.create(
            name="Worlds 2025",
            region="World",
            date_started=date.today(),
            date_ended=date.today(),
            slug="worlds-2025"
        )
        self.team1 = Team.objects.create(name="Blue Team", region="World", logo="teams/blue.png")
        self.team2 = Team.objects.create(name="Red Team", region="World", logo="teams/red.png")

        # Create players and rosters for each team
        self.players_team1 = []
        self.players_team2 = []
        for i in range(1, 6):
            self.players_team1.append(
                Player.objects.create(
                    name=f"BlueP{i}", fullname=f"Blue Player {i}", country="KR", photo=f"players/blue{i}.png"
                )
            )
            self.players_team2.append(
                Player.objects.create(
                    name=f"RedP{i}", fullname=f"Red Player {i}", country="KR", photo=f"players/red{i}.png"
                )
            )
        self.roster1 = Roster.objects.create(team=self.team1, tournament=self.tournament, year=2025)
        self.roster2 = Roster.objects.create(team=self.team2, tournament=self.tournament, year=2025)

        self.rp_team1 = []
        self.rp_team2 = []
        for i in range(5):
            self.rp_team1.append(RosterPlayer.objects.create(
                roster=self.roster1, player=self.players_team1[i], is_starter=True, role=["TOP","JNG","MID","ADC","SUP"][i]
            ))
            self.rp_team2.append(RosterPlayer.objects.create(
                roster=self.roster2, player=self.players_team2[i], is_starter=True, role=["TOP","JNG","MID","ADC","SUP"][i]
            ))

        # MatchDay and Match instance
        self.matchday = MatchDay.objects.create(date=date.today(), tournament=self.tournament)
        self.match = Match.objects.create(
            name="Blue vs Red",
            match_day=self.matchday,
            scheduled_hour=time(18, 0),
            blue_roster=self.roster1,
            red_roster=self.roster2,
            best_of=3
        )

        # Sample champion, game, player stats, prediction, mvp vote
        self.champion = Champion.objects.create(name="Ahri")
        self.game = Game.objects.create(match=self.match, winner=self.roster1, loser=self.roster2, game_number=1)
        self.game = Game.objects.create(match=self.match, winner=self.roster1, loser=self.roster2, game_number=2)
        self.playerstats = PlayerStats.objects.create(
            roster_player=self.rp_team1[0],
            game=self.game,
            champion=self.champion,
            kills=5, deaths=2, assists=7
        )
        self.prediction = Prediction.objects.create(
            user=self.user, match=self.match, predicted_winner=self.roster1, predicted_score="2 - 0"
        )
        self.mvp_vote = MVPDayVote.objects.create(user=self.user, match_day=self.matchday, fantasy_pick=self.rp_team1[0])

    def test_string_representation(self):
        """
        Validates __str__ for all major models.
        """
        self.assertIn("Blue Team", str(self.team1))
        self.assertIn("BlueP1", str(self.players_team1[0]))
        self.assertIn("Worlds 2025", str(self.tournament))
        self.assertIn("Blue Team", str(self.roster1))
        self.assertIn("Ahri", str(self.champion))
        self.assertIn("Blue Team", str(self.match))
        self.assertIn("testuser", str(self.prediction))
        self.assertIn("BlueP1", str(self.playerstats))

    def test_unique_roster_player(self):
        """
        Verifies the unique_together constraint on (roster, player) in RosterPlayer.
        """
        with self.assertRaises(Exception):
            RosterPlayer.objects.create(roster=self.roster1, player=self.players_team1[0])

    def test_roster_methods(self):
        """
        Confirms that starters() and subs() work as expected.
        """
        starters = list(self.roster1.starters())
        self.assertEqual(len(starters), 5)
        subs = list(self.roster1.subs())
        self.assertEqual(len(subs), 0)

    def test_match_save_sets_scheduled_time(self):
        """
        Ensures that Match.save() always sets scheduled_time based on scheduled_hour and matchday.
        """
        self.match.scheduled_hour = time(15, 0)
        self.match.save()
        self.assertIsNotNone(self.match.scheduled_time)

    def test_kda_calculation(self):
        """
        Validates the PlayerStats.kda() method for proper computation.
        """
        self.assertEqual(self.playerstats.kda(), 6.0)  # (5+7)/2

    def test_prediction_points(self):
        """
        Ensures calculate_points on Prediction returns correct values when predictions are right.
        """
        self.match.winner = self.roster1
        self.match.score_str = "2 - 0"
        self.match.save()
        points = self.prediction.calculate_points()
        self.assertTrue(points > 0)
        # If one prediction is right, should receive points
        self.prediction.predicted_score = "2 - 1"
        self.prediction.save()
        points = self.prediction.calculate_points()
        self.assertTrue(points > 0)

        self.prediction.predicted_winner = self.roster2
        self.prediction.predicted_score = "2 - 0"
        self.prediction.save()
        self.assertTrue(points > 0)
        # If prediction is wrong, should not receive points
        self.prediction.predicted_score = "2 - 1"
        self.prediction.save()
        self.assertEqual(self.prediction.calculate_points(), 0)

    def test_mvpdayvote_points(self):
        """
        Validates the MVPDayVote.calculate_points logic for fantasy picks.
        """
        points = self.mvp_vote.calculate_points()
        self.assertEqual(points, self.playerstats.kda())

    def test_champion_uniqueness(self):
        """
        Checks the uniqueness constraint on the Champion name.
        """
        with self.assertRaises(Exception):
            Champion.objects.create(name="Ahri")

    def test_match_unique_together(self):
        """
        Verifies unique_together on Game (match, game_number).
        """
        with self.assertRaises(Exception):
            Game.objects.create(match=self.match, winner=self.roster1, loser=self.roster2, game_number=1)

    def test_mvpresetstate_creation(self):
        """
        Confirms MVPResetState can be created and is unique per tournament.
        """
        reset = MVPResetState.objects.create(tournament=self.tournament, reset_id=1)
        self.assertEqual(reset.tournament, self.tournament)
        with self.assertRaises(Exception):
            MVPResetState.objects.create(tournament=self.tournament, reset_id=2)

    def test_tournament_slug_auto_generation(self):
        """
        Verifies that Tournament.slug is auto-generated if not provided.
        """
        tournament = Tournament.objects.create(
            name="Test Cup",
            region="EU",
            date_started=date.today(),
            date_ended=date.today()
        )
        self.assertTrue(tournament.slug.startswith("test-cup"))

    def test_match_properties(self):
        """
        Validates the .tournament, .blue_team, and .red_team properties on Match.
        """
        self.assertEqual(self.match.tournament, self.tournament)
        self.assertEqual(self.match.blue_team, self.team1)
        self.assertEqual(self.match.red_team, self.team2)

    # Add further tests as you add new models or methods

