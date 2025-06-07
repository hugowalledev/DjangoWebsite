from django.contrib import admin

from .models import Team, Player, Match, Tournament

admin.site.register(Tournament)
admin.site.register(Match)
admin.site.register(Team)
admin.site.register(Player)