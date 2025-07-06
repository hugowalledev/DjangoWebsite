from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Tournament, MatchDay, Match, MVPDayVote, Team, Player, Prediction

### 🎯 INLINE POUR LES JOUEURS DANS UNE ÉQUIPE ###
class PlayerInline(admin.TabularInline):
    model = Player
    extra = 5
    show_change_link = True

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    inlines = [PlayerInline]

### 🎯 INLINE POUR LES MATCHS DANS UN MATCHDAY ###
class MatchInline(admin.TabularInline):
    model = Match
    extra = 1
    fields = ("blue_team", "red_team", "scheduled_time", "best_of")
    show_change_link = True

@admin.register(MatchDay)
class MatchDayAdmin(admin.ModelAdmin):
    list_display = ("tournament", "date")
    list_filter = ("tournament",)
    ordering = ("-date",)
    inlines = [MatchInline]

### 🎯 INLINE POUR LES JOURNÉES DANS UN TOURNOI ###
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

### 🎯 ADMIN POUR LES PRÉDICTIONS ###
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