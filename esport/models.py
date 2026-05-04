"""
Data models for the Pronostiqueurs All-Star e-sports prediction platform.

Covers the full hierarchy: Tournament → MatchDay → Match → Game → PlayerStats,
plus the prediction/fantasy-pick system (Prediction, MVPDayVote).
"""

from .utils import OverwriteStorage
from django.db import models
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.deconstruct import deconstructible

overwrite_storage = OverwriteStorage()

class Tournament(models.Model):
    """A League of Legends tournament (e.g. LEC Spring 2024). Rosters and MatchDays hang off this."""
    name = models.CharField(max_length=255)
    league = models.CharField(max_length=255, blank=True, null=True)
    split = models.CharField(max_length=255, blank=True, null=True)
    year = models.PositiveIntegerField(blank=True, null=True)
    date_started = models.DateField("date started")
    date_ended = models.DateField("date ended")
    logo = models.ImageField(upload_to="tournaments", blank=True, null=True, storage=overwrite_storage)
    logo_dark = models.ImageField(upload_to="tournaments", blank=True, null=True, storage=overwrite_storage)
    liquipedia_url = models.URLField(blank=True, null=True)
    slug = models.SlugField(unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Team(models.Model):
    """An e-sports organisation. Teams compete across multiple tournaments via Rosters."""
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="teams", storage=overwrite_storage)
    logo_dark = models.ImageField(upload_to="teams", blank=True, null=True, storage=overwrite_storage)
    slug = models.SlugField(unique=True, blank=True, null=True)

    def __str__(self):
        return self.name

class Player(models.Model):
    """An individual pro player. Linked to Rosters via RosterPlayer; lp_slug maps to Liquipedia."""
    name = models.CharField(max_length=255)
    aliases = models.CharField(max_length=255, blank=True, default="")
    fullname = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="players", blank=True, null=True, storage=overwrite_storage)
    country = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True, null=True)
    lp_slug = models.CharField(max_length=255, blank=True, default='', db_index=True)
    def __str__(self):
        return f"{self.name}"

class Roster(models.Model):
    """A team's lineup for a specific tournament and year. One Team can have many Rosters over time."""
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE)
    year = models.PositiveIntegerField()

    def starters(self):
        return self.roster_players.filter(is_starter=True)
    
    def subs(self):
        return self.roster_players.filter(is_starter=False)

    def __str__(self):
        # Shows "Team Name (Tournament Year)"
        return f"{self.team.name} ({self.tournament.name} {self.year})"

class RosterPlayer(models.Model):
    """Join table between Roster and Player. Tracks role and starter/sub status."""
    roster = models.ForeignKey('Roster', on_delete=models.CASCADE, related_name='roster_players')
    player = models.ForeignKey('Player', on_delete=models.CASCADE)
    is_starter = models.BooleanField(default=True)
    role = models.CharField(max_length=32, blank=True)

    class Meta:
        unique_together = ('roster', 'player')

class MatchDay(models.Model):
    """A single day of play within a tournament. Defines the point values awarded for that day's predictions."""
    date = models.DateField()
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="days")
    points_winner = models.PositiveSmallIntegerField(default=30)
    points_score = models.PositiveSmallIntegerField(default=15)
    
    class Meta:
        unique_together = ("date", "tournament")
    def __str__(self):
        return f"{self.date} - {self.tournament.name}"

class Match(models.Model):
    """
    A best-of series between two Rosters on a MatchDay.

    scheduled_time is derived from match_day.date + scheduled_hour on save.
    winner/loser/score fields are populated when the match is closed by an admin.
    """
    name = models.CharField(max_length=255)
    match_day = models.ForeignKey(MatchDay, on_delete=models.CASCADE, related_name="matches")
    scheduled_hour = models.TimeField(null=True, blank=True)
    scheduled_time = models.DateTimeField(editable=False)
    blue_roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="blue_matches")
    red_roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="red_matches")
    best_of = models.PositiveSmallIntegerField(choices=[(1, "BO1"), (3, "BO3"), (5, "BO5")], default=1)

    winner = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="winner_team", blank=True, null=True)
    loser = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="loser_team", blank=True, null=True)
    winner_score = models.PositiveSmallIntegerField(null=True, blank=True)
    loser_score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_str = models.CharField(max_length=10, blank=True, null=True)

    is_closed = models.BooleanField(default=False)

    golgg_url = models.URLField(blank=True, null=True)
    
    @property
    def tournament(self):
        return self.match_day.tournament
    @property
    def blue_team(self):
        return self.blue_roster.team
    @property
    def red_team(self):
        return self.red_roster.team
    def __str__(self):
        return f"{self.blue_roster.team.name} VS {self.red_roster.team.name} ({self.tournament.name})"
    def save(self, *args, **kwargs):
        self.scheduled_time = timezone.make_aware(datetime.combine(self.match_day.date, self.scheduled_hour))
        super().save(*args, **kwargs)

class Game(models.Model):
    """One individual game within a Match (e.g. Game 2 of a BO3). side_swapped=True means teams swapped blue/red from the match default."""
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    winner = models.ForeignKey(Roster, on_delete=models.CASCADE, null = True, related_name="game_winner")
    loser = models.ForeignKey(Roster, on_delete=models.CASCADE, null = True, related_name="game_loser")
    game_number = models.PositiveIntegerField()
    side_swapped = models.BooleanField(default=False)

    def __str__(self):
        return f"Game {self.game_number} of {self.match}"
    class Meta:
        unique_together = ('match', 'game_number')

class PlayerStats(models.Model):
    """KDA stats for a single player in a single Game. Used to calculate MVP fantasy scores."""
    roster_player = models.ForeignKey(RosterPlayer, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, null=True)
    champion = models.ForeignKey('Champion', on_delete=models.SET_NULL, null=True, blank=True, related_name="playerstats")
    kills = models.PositiveIntegerField(default=0)
    deaths = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)

    def kda(self):
        """Returns (kills + assists) / max(1, deaths) to avoid division by zero."""
        return (self.kills + self.assists) / max(1, self.deaths)

    def __str__(self):
        return f"{self.roster_player.player} in {self.game.match} Game {self.game.game_number} ({self.champion or 'No Champion'})"
    

class Champion(models.Model):
    """A League of Legends champion, imported from the Riot Data Dragon API."""
    name = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to="champions", blank=True, null=True, storage=overwrite_storage)

    def __str__(self):
        return self.name

from users.models import UserProfile


class Prediction(models.Model):
    """A user's prediction for a Match: who wins and the exact score (e.g. '2 - 1'). One per user per match."""
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)

    predicted_winner = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="predicted_match_wins")
    predicted_score = models.CharField(max_length=10)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "match")

    def __str__(self):
        return f"{self.user.username} - {self.match}"
    
    @property
    def reversed_score_str(self):
        if self.predicted_score and " - " in self.predicted_score:
            parts = self.predicted_score.split(" - ")
            if len(parts) == 2:
                return f"{parts[1]} - {parts[0]}"
        return None

    def calculate_points(self):
        """
        Awards points_winner if the predicted winner is correct.
        Awards points_score if the exact score matches (order-insensitive via reversed_score_str).
        Both values come from the MatchDay, so they can vary between days.
        """
        matchday = self.match.match_day
        points = 0

        if self.predicted_winner == self.match.winner:
            points += matchday.points_winner

        if self.predicted_score == self.match.score_str or self.reversed_score_str == self.match.score_str:
            points += matchday.points_score

        return points


class MVPDayVote(models.Model):
    """
    A user's fantasy pick for a MatchDay: one RosterPlayer whose KDA across all games that day earns points.

    reset_id tracks the current pick period — when an admin resets picks, reset_id increments
    and all old votes become read-only history.
    """
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match_day = models.ForeignKey(MatchDay, on_delete=models.CASCADE)
    fantasy_pick = models.ForeignKey(RosterPlayer, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    reset_id = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ("user", "match_day", "fantasy_pick", "reset_id")
    def calculate_points(self):
        """Sums the KDA of the picked player across every game played on this MatchDay."""
        player_stats = PlayerStats.objects.filter(
            roster_player=self.fantasy_pick,
            game__match__match_day=self.match_day
        )
        total_kda = sum(stat.kda() for stat in player_stats)
        return total_kda

class MVPResetState(models.Model):
    """Tracks the current reset_id per tournament. Incrementing reset_id invalidates all existing MVPDayVotes for new picks."""
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE)
    reset_id = models.PositiveIntegerField(default=0)