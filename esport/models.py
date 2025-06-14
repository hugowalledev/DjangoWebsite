from django.db import models
from datetime import timedelta

class Tournament(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    date_started = models.DateTimeField("date started")
    slug = models.SlugField(default=f"{name}")
    def __str__(self):
        return self.name


class Team(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="esport/static/teams")
    def __str__(self):
        return self.name

class Player(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="esport/static/players")
    country = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    def __str__(self):
        return f"{self.name} ({self.team.name})"

class MatchDay(models.Model):
    date = models.DateField()
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name="days")

    class Meta:
        unique_together = ("date", "tournament")

    def __str__(self):
        return f"{self.date} - {self.tournament.name}"
    

class Match(models.Model):
    name = models.CharField(max_length=255)
    tournament = models.ForeignKey(Tournament,on_delete=models.CASCADE)
    match_day = models.ForeignKey(MatchDay, on_delete=models.CASCADE, related_name="matches")
    scheduled_time = models.DateTimeField()
    red_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="red_team")
    blue_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="blue_team")
    best_of = models.PositiveSmallIntegerField(choices=[(1, "BO1"), (3, "BO3"), (5, "BO5")], default=1)

    
    winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="winner_team", blank=True, null=True)
    loser = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="loser_team", blank=True, null=True)
    winner_score = models.PositiveSmallIntegerField(null=True, blank=True)
    loser_score = models.PositiveSmallIntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.red_team.name} VS {self.blue_team.name} ({self.tournament.name})"

class PlayerStats(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)
    kills = models.PositiveIntegerField(default=0)
    deaths = models.PositiveIntegerField(default=0)
    assists = models.PositiveIntegerField(default=0)

    def kda(self):
        return (self.kills + self.assists) / max(1, self.deaths)


from users.models import UserProfile


class Prediction(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    match = models.ForeignKey(Match, on_delete=models.CASCADE)

    predicted_winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="predicted_match_wins")
    predicted_score_winner = models.PositiveSmallIntegerField()
    predicted_score_loser = models.PositiveSmallIntegerField()

    fantasy_pick = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True)

    is_correct = models.BooleanField(null=True, blank=True)
    score_correct = models.BooleanField(null=True, blank=True)
    points_awarded = models.FloatField(null=True, blank=True)
    mvp_points = models.FloatField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "match")

    def has_already_picked_mvp(user, player, tournament):
        return Prediction.objects.filter(
            user=user,
            fantasy_pick=player,
            match__tournament=tournament
        ).exist()

    def __str__(self):
        return f"{self.user.username} - {self.match} - MVP : {self.fantasy_pick}"
