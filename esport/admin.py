from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Champion, Game, MatchDay, Match, MVPDayVote, Team, Tournament, Player, PlayerStats, Prediction, Roster, RosterPlayer
from .utils import get_possible_scores

import datetime

@admin.action(description="Close selected match(enter winner/scores)")
def close_matches(modeladmin, request, queryset):
    for match in queryset:
        match.is_closed = True
        match.save()

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "fullname", "country")
    search_fields = ("name", "fullname", "country")

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("game_number", "match", "winner", "loser")
    list_filter = ("match",)
    search_fields = ("match__blue_roster__team__name", "match__red_roster__team__name")
    ordering = ("match", "game_number")


class MatchAdminForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


        match = self.instance
        bo = match.best_of if match.pk else self.initial.get('best_of', 1)
        possible_scores = get_possible_scores(match) if match.pk else get_possible_scores(type('Dummy', (), {'best_of': bo})())
        choices = [("", "---")] + [
            (f"{w} - {l}", f"{w} - {l}") for w, l in possible_scores
        ]
        self.fields['score_str'] = forms.ChoiceField(
            choices=choices,
            required=False,
            label="Official score (format X - Y)",
            initial=match.score_str if match.pk else None
        )

class MatchInline(admin.TabularInline):
    form = MatchAdminForm
    model = Match
    extra = 0
    raw_id_fields = ("blue_roster", "red_roster", "winner", "loser")
    fields = (
        "blue_roster",
        "red_roster",
        "scheduled_hour",
        "best_of",
        "winner",
        "loser",
        "score_str",
        "is_closed",
        )
    show_change_link = True

@admin.register(MatchDay)
class MatchDayAdmin(admin.ModelAdmin):
    list_display = ("tournament", "date", "view_matches_link")
    list_filter = ("tournament",)
    ordering = ("-date",)
    inlines = [MatchInline]

    def view_matches_link(self, obj):
        url = (
            reverse('admin:esport_matchday_changelist')
            + f'?match_day__id__exact={obj.id}'
        )
        return format_html(f'<a href="{url}">View Matches</a>')
    view_matches_link.short_description = "Matches"

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

@admin.register(Champion)
class ChampionAdmin(admin.ModelAdmin):
    list_display = ("name", "champion_image")
    search_fields = ("name",)

    def champion_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:32px; object-fit:cover;">', obj.image.url)
        return "-"
    champion_image.short_description = "Image"

@admin.register(PlayerStats)
class PlayerStatsAdmin(admin.ModelAdmin):
    list_display = ("get_player_name", "get_team", "game", "get_match", "champion", "kills", "deaths", "assists")
    list_filter = ("champion", "roster_player__player", "game__match")
    search_fields = ("roster_player__player__name", "champion__name", "game__match")
    ordering = ("game", "roster_player")

    def get_player_name(self, obj):
        return obj.roster_player.player.name
    get_player_name.short_description = "Player"

    def get_team(self, obj):
        return obj.roster_player.roster.team.name
    get_team.short_description = "Team"

    def get_match(self, obj):
        return obj.game.match
    get_match.short_description = "Match"

    
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
    search_fields = ("user__username", "match__blue_roster__team__name", "match__red_roster__team__name")
    ordering = ("-timestamp",)

@admin.register(MVPDayVote)
class MVPDayVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "match_day", "fantasy_pick", "timestamp")
    list_filter = ("match_day__tournament", "fantasy_pick")
    search_fields = ("user__username", "match_day__tournament__name", "fantasy_pick__name")
    ordering = ("-timestamp",)

class RosterPlayerInline(admin.TabularInline):
    model = RosterPlayer
    extra = 2
    fields = ("player", "is_starter", "role")
    show_change_link = True

@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = ("team", "tournament", "year")
    inlines = [RosterPlayerInline]
    search_fields = ("team__name", "tournament__name", "year")
