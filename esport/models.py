from django.db import models


class Player(models.Model):
    player_name = models.CharField(mac_length=100)
    