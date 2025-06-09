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
    logo = models.ImageField(upload_to="esport/static/teams")
    def __str__(self):
        return self.name

class Player(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="esport/static/players")
    country = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    def __str__(self):
        return self.name


class Match(models.Model):
    name = models.CharField(max_length=255)
    date = models.DateTimeField("date played")
    red_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="red_team")
    blue_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="blue_team")
    winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="winner_team", blank=True, null=True)
    loser = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="loser_team", blank=True, null=True)
    duration = models.DurationField(blank=True, default=timedelta(minutes=5))
    tournament = models.ForeignKey(Tournament,on_delete=models.CASCADE)
    slug = models.SlugField(default=f"{name}")
    def __str__(self):
        return f"{self.red_team.name} VS {self.blue_team.name}"
