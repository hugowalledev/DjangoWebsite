from django.db import models
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from django.utils import timezone


class Tournament(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    date_started = models.DateField("date started")
    date_ended = models.DateField("date ended")
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
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="teams")
    def __str__(self):
        return self.name

class Player(models.Model):
    name = models.CharField(max_length=255)
    fullname = models.CharField(max_length=255, blank=True)
    photo = models.ImageField(upload_to="players")
    country = models.CharField(max_length=255)
    def __str__(self):
        return f"{self.name}"

class Roster(models.Model):
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
    roster = models.ForeignKey('Roster', on_delete=models.CASCADE, related_name='roster_players')
    player = models.ForeignKey('Player', on_delete=models.CASCADE)
    is_starter = models.BooleanField(default=True)
    role = models.CharField(max_length=32, blank=True)

    class Meta:
        unique_together = ('roster', 'player')

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

class PlayerStats(models.Model):
    roster_player = models.ForeignKey(RosterPlayer, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    champion = models.ForeignKey('Champion', on_delete=models.SET_NULL, null=True, blank=True, related_name="playerstats")
    kills = models.PositiveIntegerField(default=0)
    deaths = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)

    def kda(self):
        return (self.kills + self.assists) / max(1, self.deaths)

    def __str__(self):
        return f"{self.roster_player.player} in {self.match} ({self.champion or 'No Champion'})"

class Champion(models.Model):
    name = models.CharField(max_length=50, unique=True)
    image = models.ImageField(upload_to="champions", blank=True, null=True)

    def __str__(self):
        return self.name

from users.models import UserProfile


class Prediction(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)

    predicted_winner = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="predicted_match_wins")
    predicted_score = models.CharField(max_length=10)

    is_correct = models.BooleanField(null=True, blank=True)
    score_correct = models.BooleanField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "match")

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
        player_stats = PlayerStats.objects.filter(
            roster_player__player=self.fantasy_pick,
            match__match_day=self.match_day
        )
        total_kda = sum(stat.kda() for stat in player_stats)
        return total_kda

class MVPResetState(models.Model):
    tournament = models.OneToOneField(Tournament, on_delete=models.CASCADE)
    reset_id = models.PositiveIntegerField(default=0)