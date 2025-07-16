from django.db import models
from datetime import timedelta
from django.core.exceptions import ValidationError
import datetime

class Tournament(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    date_started = models.DateTimeField("date started")
    date_ended = models.DateTimeField("date ended")
    slug = models.SlugField(unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Team(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="teams")
    def __str__(self):
        return self.name

class Player(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="players")
    country = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    def __str__(self):
        return f"{self.name} ({self.team.name})"

class MatchDay(models.Model):
    date = models.DateField()
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="days")
    points_winner = models.PositiveSmallIntegerField(default=30)
    points_score = models.PositiveSmallIntegerField(default=15)
    
    class Meta:
        unique_together = ("date", "tournament")
    def __str__(self):
        return f"{self.date} - {self.tournament.name}"

class Match(models.Model):
    name = models.CharField(max_length=255)
    match_day = models.ForeignKey(MatchDay, on_delete=models.CASCADE, related_name="matches")
    scheduled_hour = models.TimeField()
    scheduled_time = models.DateTimeField(editable=False)
    red_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="red_team")
    blue_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="blue_team")
    best_of = models.PositiveSmallIntegerField(choices=[(1, "BO1"), (3, "BO3"), (5, "BO5")], default=1)

    winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="winner_team", blank=True, null=True)
    loser = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="loser_team", blank=True, null=True)
    winner_score = models.PositiveSmallIntegerField(null=True, blank=True)
    loser_score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_str = models.CharField(max_length=10, blank=True, null=True)

    is_closed = models.BooleanField(default=False)
    
    @property
    def tournament(self):
        return self.match_day.tournament
    def __str__(self):
        return f"{self.red_team.name} VS {self.blue_team.name} ({self.tournament.name})"
    def save(self, *args, **kwargs):
        self.scheduled_time = datetime.datetime.combine(self.match_day.date, self.scheduled_hour)
        super().save(*args, **kwargs)

class PlayerStats(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    champion = models.ForeignKey('Champion', on_delete=models.SET_NULL, null=True, blank=True, related_name="playerstats")
    kills = models.PositiveIntegerField(default=0)
    deaths = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)

    def kda(self):
        return (self.kills + self.assists) / max(1, self.deaths)

    def __str__(self):
        return f"{self.player} in {self.match} ({self.champion or 'No Champion'})"

class Champion(models.Model):
    name = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to="champions", blank=True, null=True)

    def __str__(self):
        return self.name

from users.models import UserProfile


class Prediction(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)

    predicted_winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="predicted_match_wins")
    predicted_score = models.CharField(max_length=10)

    is_correct = models.BooleanField(null=True, blank=True)
    score_correct = models.BooleanField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "match")

    def has_already_picked_mvp(user, player, tournament):
        return Prediction.objects.filter(
            user=user,
            fantasy_pick=player,
            match__tournament=tournament
        ).exists()

    def __str__(self):
        return f"{self.user.username} - {self.match}"

    def calculate_points(self):
        matchday = self.match.match_day
        points = 0
        if self.predicted_winner == self.match.winner:
            points += matchday.points_winner
        if self.predicted_score == self.match.score_str:
            points += matchday.points_score
        return points

class MVPDayVote(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match_day = models.ForeignKey(MatchDay, on_delete=models.CASCADE)
    fantasy_pick = models.ForeignKey(Player, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    reset_id = models.PositiveIntegerField(default=0)
    
    class Meta:
        unique_together = ("user", "match_day", "fantasy_pick", "reset_id")
    def calculate_points(self):
        # On récupère tous les matchs du joueur ce jour-là
        player_stats = PlayerStats.objects.filter(
            player=self.fantasy_pick,
            match__match_day=self.match_day
        )
        total_kda = sum(stat.kda() for stat in player_stats)
        return total_kda

class MVPResetState(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE)
    reset_id = models.PositiveIntegerField(default=0)