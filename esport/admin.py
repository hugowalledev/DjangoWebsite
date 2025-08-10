from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from .models import Champion, Game, MatchDay, Match, MVPDayVote, Team, Tournament, Player, PlayerStats, Prediction, Roster, RosterPlayer
from .utils import get_possible_scores
from users.models import UserProfile
import datetime

@admin.action(description="Close selected match (enter winner/scores)")
def close_matches(modeladmin, request, queryset):
    for match in queryset:
        match.is_closed = True
        match.save()

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "fullname", "country")
    search_fields = ("name", "fullname", "country")
    list_display_links = ("name",)

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    list_display_links = ("name",)

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("game_number", "match", "winner", "loser")
    list_filter = ("match",)
    search_fields = ("match__blue_roster__team__name", "match__red_roster__team__name")
    ordering = ("match", "game_number")
    autocomplete_fields = ("match", "winner", "loser")
    list_select_related = True
    list_display_links = ("game_number", "match")
    list_per_page = 30

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'match',
            'winner__team',
            'loser__team',
        )

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
            initial=match.score_str if match.pk else None,
            help_text="Select the official match score in the format X - Y"
        )

class MatchInline(admin.TabularInline):
    form = MatchAdminForm
    model = Match
    extra = 0
    autocomplete_fields = ("blue_roster", "red_roster", "winner", "loser")
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

@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    list_display = ("name", "blue_roster", "red_roster", "scheduled_hour")
    autocomplete_fields = ("blue_roster", "red_roster", "winner", "loser")
    list_display_links = ("name",)
    list_per_page = 30

@admin.register(MatchDay)
class MatchDayAdmin(admin.ModelAdmin):
    list_display = ("tournament", "date", "view_matches_link")
    list_filter = ("tournament",)
    ordering = ("-date",)
    inlines = [MatchInline]
    search_fields = ("tournament__name", "date")
    autocomplete_fields = ("tournament",)
    list_select_related = True
    date_hierarchy = "date"
    list_display_links = ("tournament", "date")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "tournament"
        )

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
    autocomplete_fields = ("tournament",)

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ("name", "date_started", "date_ended")
    search_fields = ("name",)
    ordering = ("-date_started",)
    inlines = [MatchDayInline]
    list_display_links = ("name",)
    date_hierarchy = "date_started"

@admin.register(Champion)
class ChampionAdmin(admin.ModelAdmin):
    list_display = ("name", "champion_image")
    search_fields = ("name",)
    list_display_links = ("name",)

    def champion_image(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:32px; object-fit:cover;">', obj.image.url)
        return "-"
    champion_image.short_description = "Image"

@admin.register(PlayerStats)
class PlayerStatsAdmin(admin.ModelAdmin):
    list_display = (
        "get_player_name", "get_team", "game", "get_match", "champion", "kills", "deaths", "assists", "get_kda"
    )
    list_filter = ("champion", "roster_player__player", "game__match")
    search_fields = ("roster_player__player__name", "champion__name", "game__match")
    ordering = ("game", "roster_player")
    autocomplete_fields = ("roster_player", "game", "champion")
    list_select_related = True
    list_per_page = 50
    list_display_links = ("get_player_name", "game")
    readonly_fields = ("get_kda",)

    fieldsets = (
        (None, {
            "fields": (
                "roster_player",
                "game",
                "champion",
                ("kills", "deaths", "assists"),
                "get_kda"
            ),
        }),
    )

    def get_player_name(self, obj):
        return obj.roster_player.player.name
    get_player_name.short_description = "Player"

    def get_team(self, obj):
        return obj.roster_player.roster.team.name
    get_team.short_description = "Team"

    def get_match(self, obj):
        return obj.game.match
    get_match.short_description = "Match"

    def get_kda(self, obj):
        return f"{obj.kda():.2f}"
    get_kda.short_description = "KDA (computed)"
    get_kda.help_text = "Kills + Assists / max(1, Deaths)"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "roster_player__player",
            "roster_player__roster__team",
            "game",
            "game__match",
            "champion",
        )

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
    autocomplete_fields = ("user", "match", "predicted_winner")
    list_select_related = True
    list_display_links = ("user", "match")
    date_hierarchy = "timestamp"
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "user",
            "match",
            "predicted_winner",
            "match__blue_roster__team",
            "match__red_roster__team",
        )

@admin.register(MVPDayVote)
class MVPDayVoteAdmin(admin.ModelAdmin):
    list_display = ("user", "match_day", "fantasy_pick", "timestamp")
    list_filter = ("match_day__tournament", "fantasy_pick")
    search_fields = ("user__username", "match_day__tournament__name", "fantasy_pick__name")
    ordering = ("-timestamp",)
    autocomplete_fields = ("user", "match_day", "fantasy_pick")
    list_select_related = True
    list_display_links = ("user", "match_day")
    date_hierarchy = "timestamp"
    list_per_page = 50

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'user',
            'match_day',
            'match_day__tournament',
            'fantasy_pick__player',
        )

@admin.register(RosterPlayer)
class RosterPlayerAdmin(admin.ModelAdmin):
    search_fields = ("player__name", "roster__team__name")
    autocomplete_fields = ("player", "roster")
    list_display = ("player", "roster", "is_starter", "role")
    list_display_links = ("player", "roster")
    readonly_fields = ("player_rosters",)

    fieldsets = (
        (None, {
            'fields': ("player", "roster", "is_starter", "role", "player_rosters")
        }),
    )

    def player_rosters(self, obj):
        if not obj.player:
            return "-"
        rosters = RosterPlayer.objects.filter(player=obj.player).select_related("roster__team", "roster__tournament").order_by("-roster__year")
        if not rosters:
            return "No rosters found."

        # Optional: limit initial display and make it expandable with a bit of JS
        html = '<ul id="roster-list" style="max-height: 100px; overflow-y: auto; padding-left: 1em;">'
        for rp in rosters:
            url = reverse("admin:esport_roster_change", args=[rp.roster.id])
            label = f"{rp.roster.team.name} - {rp.roster.tournament.name} ({rp.roster.year})"
            html += f'<li><a href="{url}" target="_blank">{label}</a></li>'
        html += "</ul>"

        return format_html(html)

    player_rosters.short_description = "All rosters this player has been in"


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    search_fields = ("username", "email")
    list_display = ("username", "email")
    list_display_links = ("username",)

class RosterPlayerInline(admin.TabularInline):
    model = RosterPlayer
    extra = 2
    fields = ("player", "is_starter", "role")
    show_change_link = True
    autocomplete_fields = ("player",)

@admin.register(Roster)
class RosterAdmin(admin.ModelAdmin):
    list_display = ("team", "tournament", "year")
    inlines = [RosterPlayerInline]
    search_fields = ("team__name", "tournament__name", "year")
    autocomplete_fields = ("team", "tournament")
    list_select_related = True
    list_display_links = ("team", "tournament")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "team", "tournament"
        )
