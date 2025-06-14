from django.db import models
from django.contrib.auth.models import User
from esport.models import Player


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    points = models.IntegerField(default=0)
    selected_mvps = models.ManyToManyField(Player, blank=True)