from django.urls import path

from . import views

app_name = "esport"
urlpatterns = [
    path("", views.TournamentlistView.as_view(), name="tournaments"),
    path("matches/", views.MatchesView.as_view(), name="matches"),
    path("matches/vote/", views.VoteView
    .as_view(), name="vote"),
]