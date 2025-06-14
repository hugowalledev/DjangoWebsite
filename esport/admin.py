from django.contrib import admin

from .models import Team, Player, Match, Tournament



class MatchInline(admin.StackedInline):
    model = Match
    extra = 1

class PlayerInline(admin.StackedInline):
    model = Player
    extra = 5

class TeamAdmin(admin.ModelAdmin):
    inlines = [PlayerInline]

class TournamentAdmin(admin.ModelAdmin):
    inlines = [MatchInline]
    prepopulated_fields = {"slug" : ("name",)}


admin.site.register(Tournament, TournamentAdmin)
admin.site.register(Team, TeamAdmin)