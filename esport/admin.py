from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Tournament, MatchDay, Match, MVPDayVote, Team, Player, Prediction

import datetime

@admin.action(description="Close selected match(enter winner/scores)")
def close_matches(modeladmin, request, queryset):
    for match in queryset:
        match.is_closed = True
        match.save()

class PlayerInline(admin.TabularInline):
    model = Player
    extra = 5
    show_change_link = True

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = [PlayerInline]

class MatchInline(admin.TabularInline):
    model = Match
    extra = 1
    actions = [close_matches]
    fields = (
        "blue_team",
        "red_team",
        "scheduled_hour",
        "best_of",
        "winner",
        "winner_score",
        "is_closed",
        )
    readonly_fields = ()
    show_change_link = True

@admin.register(MatchDay)
class MatchDayAdmin(admin.ModelAdmin):
    list_display = ("tournament", "date")
    list_filter = ("tournament",)
    ordering = ("-date",)
    inlines = [MatchInline]

class MatchDayInline(admin.StackedInline):
    model = MatchDay
    extra = 0
    show_change_link = True

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "date_started", "date_ended", "matchlist_link")  # 👈 nouveau champ
    search_fields = ("name",)
    ordering = ("-date_started",)
    inlines = [MatchDayInline]

    def matchlist_link(self, obj):
        url = reverse('esport:matchlist', args=[obj.slug])
        return format_html('<a href="{}" target="_blank">Voir les matchs à venir</a>', url)
    matchlist_link.short_description = "Matchs à venir"

@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "match",
        "predicted_winner",
        "predicted_score",
        "timestamp",
    )
    list_filter = ("match__match_day__tournament", "user")
    search_fields = ("user__username", "match__team1__name", "match__team2__name")
    ordering = ("-timestamp",)

@admin.register(MVPDayVote)
class MVPDayVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "match_day", "fantasy_pick", "timestamp")
    list_filter = ("match_day__tournament", "fantasy_pick")
    search_fields = ("user__username", "match_day__tournament__name", "fantasy_pick__name")
    ordering = ("-timestamp",)