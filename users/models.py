from django.db import models
from django.contrib.auth.models import User
from esport.models import Player


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    
    def __str__(self):
        return self.user.username