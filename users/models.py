from django.contrib.auth.models import AbstractUser
from django.db import models


class UserProfile(AbstractUser):
    
    avatar = models.ImageField(upload_to="users/static/avatars/", null=True, blank=True)

    def __str__(self):
        return self.username