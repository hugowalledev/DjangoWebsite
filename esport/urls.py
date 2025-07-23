from django.urls import path, include
from . import views

app_name = "esport"
urlpatterns = [
    path("", views.TournamentListView.as_view(), name="tournamentlist"),
    path('<slug:slug>/', views.matchlist, name='matchlist'),
    path("<slug:slug>/fantasy/", views.PredictionView.as_view(), name="prediction"),
    path('match/<int:match_id>/', views.match_detail, name='match_detail'),
    path('<slug:slug>/scoreboard', views.tournament_scoreboard, name ='tournament_scoreboard'),
]