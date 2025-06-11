from django.urls import path
from . import views

app_name = "esport"
urlpatterns = [
    path("", views.TournamentlistView.as_view(), name="tournamentlist"),
    path("<slug:slug>/", views.MatchesView.as_view(), name="matches"),
    path("<slug:slug>/vote/", views.VoteView.as_view(), name="vote"),
]