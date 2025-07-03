from django.urls import path, include
from . import views

app_name = "esport"
urlpatterns = [
    path("", views.TournamentlistView.as_view(), name="tournamentlist"),
    path('<slug:slug>/', views.matchlist, name='matchlist'),
    path("<slug:slug>/vote/", views.VoteView.as_view(), name="vote"),
    path("<slug:slug>/fantasy/", views.PredictionView.as_view(), name="prediction"),
]