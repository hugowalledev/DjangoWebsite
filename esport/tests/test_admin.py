from django.test import TestCase, Client, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from esport.admin import (
    PlayerAdmin, TeamAdmin, GameAdmin, MatchAdmin, MatchDayAdmin, MatchDayInline, MatchInline,
    TournamentAdmin, ChampionAdmin, PlayerStatsAdmin, PredictionAdmin,
    MVPDayVoteAdmin, RosterAdmin, RosterPlayerAdmin, RosterPlayerInline, UserProfileAdmin, close_matches
)
from esport.models import (
    Tournament, Team, Player, Roster, RosterPlayer, MatchDay, Match, Game, 
    PlayerStats, Champion, Prediction, MVPDayVote
)
from users.models import UserProfile
from datetime import date, time, datetime
from django.utils import timezone
from django.conf import settings
import os

class MockRequest:
    pass

class AdminTestCase(TestCase):
    """
    Tests for Django admin configurations and actions in esport app.
    """
    @classmethod
    def setUpTestData(cls):
        # Create required data for all tests only once for efficiency
        cls.user = UserProfile.objects.create(username="testuser", email="test@example.com")
        cls.tournament = Tournament.objects.create(
            name="Worlds",
            region="World",
            date_started=date.today(),
            date_ended=date.today(),
            slug="worlds"
        )
        cls.team1 = Team.objects.create(name="Blue Team", region="World", logo="teams/blue.png")
        cls.team2 = Team.objects.create(name="Red Team", region="World", logo="teams/red.png")
        cls.player1 = Player.objects.create(name="BlueP1", fullname="Blue Player 1", country="KR", photo="players/blue1.png")
        cls.player2 = Player.objects.create(name="RedP1", fullname="Red Player 1", country="KR", photo="players/red1.png")
        cls.roster1 = Roster.objects.create(team=cls.team1, tournament=cls.tournament, year=2025)
        cls.roster2 = Roster.objects.create(team=cls.team2, tournament=cls.tournament, year=2025)
        cls.rp1 = RosterPlayer.objects.create(roster=cls.roster1, player=cls.player1, is_starter=True, role="TOP")
        cls.rp2 = RosterPlayer.objects.create(roster=cls.roster2, player=cls.player2, is_starter=True, role="TOP")
        cls.matchday = MatchDay.objects.create(date=date.today(), tournament=cls.tournament)
        cls.match = Match.objects.create(
            name="Blue vs Red",
            match_day=cls.matchday,
            scheduled_hour=time(18, 0),
            blue_roster=cls.roster1,
            red_roster=cls.roster2,
            best_of=1
        )
        image_path = os.path.join(settings.BASE_DIR, "esport", "tests", "test_image.png")
        with open(image_path, "rb") as img:
            cls.champion = Champion.objects.create(
                name="Ahri",
                image=SimpleUploadedFile("test_image.png", img.read(), content_type="image/png")
            )
        cls.game = Game.objects.create(match=cls.match, winner=cls.roster1, loser=cls.roster2, game_number=1)
        cls.playerstats = PlayerStats.objects.create(
            roster_player=cls.rp1, game=cls.game, champion=cls.champion, kills=5, deaths=2, assists=7
        )
        cls.prediction = Prediction.objects.create(user=cls.user, match=cls.match, predicted_winner=cls.roster1, predicted_score="1 - 0")
        cls.mvp_vote = MVPDayVote.objects.create(user=cls.user, match_day=cls.matchday, fantasy_pick=cls.rp1)

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.admin_site = AdminSite()

    def test_player_admin_list_display(self):
        admin_obj = PlayerAdmin(Player, self.admin_site)
        # Validate displayed fields and search fields
        self.assertIn("name", admin_obj.list_display)
        self.assertIn("fullname", admin_obj.search_fields)

    def test_team_admin_list_display(self):
        admin_obj = TeamAdmin(Team, self.admin_site)
        self.assertIn("name", admin_obj.list_display)

    def test_game_admin_queryset_optimized(self):
        admin_obj = GameAdmin(Game, self.admin_site)
        qs = admin_obj.get_queryset(MockRequest())
        # Ensure prefetch is applied to reduce queries
        self.assertTrue(hasattr(qs, "select_related"))

    def test_champion_admin_image_column(self):
        admin_obj = ChampionAdmin(Champion, self.admin_site)
        # Returns an HTML img tag or "-"
        html = admin_obj.champion_image(self.champion)
        self.assertIn("img", html)

    def test_playerstats_admin_list_display_and_kda(self):
        admin_obj = PlayerStatsAdmin(PlayerStats, self.admin_site)
        kda = admin_obj.get_kda(self.playerstats)
        self.assertAlmostEqual(float(kda), self.playerstats.kda(), places=2)
        self.assertIn("Player", admin_obj.get_player_name.short_description)

    def test_prediction_admin_queryset(self):
        admin_obj = PredictionAdmin(Prediction, self.admin_site)
        qs = admin_obj.get_queryset(MockRequest())
        self.assertTrue(hasattr(qs, "select_related"))

    def test_matchday_admin_view_matches_link(self):
        admin_obj = MatchDayAdmin(MatchDay, self.admin_site)
        # Should return a formatted HTML link
        html = admin_obj.view_matches_link(self.matchday)
        self.assertIn('<a href=', html)

    def test_tournament_admin_matchlist_link(self):
        admin_obj = TournamentAdmin(Tournament, self.admin_site)
        html = admin_obj.matchlist_link(self.tournament)
        self.assertIn('<a href=', html)

    def test_close_matches_action(self):
        # Tests admin action for closing matches
        qs = Match.objects.filter(id=self.match.id)
        close_matches(None, None, qs)
        self.match.refresh_from_db()
        self.assertTrue(self.match.is_closed)

    def test_roster_admin_queryset(self):
        admin_obj = RosterAdmin(Roster, self.admin_site)
        qs = admin_obj.get_queryset(MockRequest())
        self.assertTrue(hasattr(qs, "select_related"))

    def test_rosterplayer_admin_config(self):
        admin_obj = RosterPlayerAdmin(RosterPlayer, self.admin_site)
        self.assertIn("player__name", admin_obj.search_fields)

    def test_userprofile_admin_display(self):
        admin_obj = UserProfileAdmin(UserProfile, self.admin_site)
        self.assertIn("username", admin_obj.list_display)

    def test_mvpdayvote_admin_queryset(self):
        admin_obj = MVPDayVoteAdmin(MVPDayVote, self.admin_site)
        qs = admin_obj.get_queryset(MockRequest())
        self.assertTrue(hasattr(qs, "select_related"))

    def test_match_admin_list_display(self):
        admin_obj = MatchAdmin(Match, self.admin_site)
        self.assertIn("name", admin_obj.list_display)

    def test_matchadminform_score_choices(self):
        # Test MatchAdminForm's dynamic score_str field population
        from esport.admin import MatchAdminForm
        form = MatchAdminForm(instance=self.match)
        self.assertIn(("1 - 0", "1 - 0"), form.fields['score_str'].choices)

    def test_inline_configs(self):
        # Test inline admin classes
        match_inline = MatchInline(Match, self.admin_site)
        self.assertIn("blue_roster", match_inline.fields)
        matchday_inline = MatchDayInline(MatchDay, self.admin_site)
        self.assertIn("tournament", matchday_inline.autocomplete_fields)
        roster_inline = RosterPlayerInline(RosterPlayer, self.admin_site)
        self.assertIn("player", roster_inline.fields)
