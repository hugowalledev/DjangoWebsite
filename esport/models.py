from django.db import models


class Tournament(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255)
    date_started = models.DateTimeField("date started")
    def __str__(self):
        return self.name


class Team(models.Model):
    name = models.CharField(max_length=255)
    logo = models.ImageField(upload_to="teams")
    def __str__(self):
        return self.name

class Player(models.Model):
    name = models.CharField(max_length=255)
    photo = models.ImageField(upload_to="players")
    country = models.CharField(max_length=255)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    def __str__(self):
        return self.name


class Match(models.Model):
    name = models.CharField(max_length=255)
    date = models.DateTimeField("date played")
    teams = models.ManyToManyField(Team)
    winner = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="winner_team")
    loser = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="loser_team")
    duration = models.DurationField()
    tournament = models.ForeignKey(Tournament,on_delete=models.CASCADE)
    def __str__(self):
        return f"{self.teams.all()[0].name} VS {self.teams.all()[1].name}"
