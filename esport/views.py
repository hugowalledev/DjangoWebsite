from django.shortcuts import render
from django.views import generic

from .models import Tournament,Team,Player,Match

class TournamentlistView(generic.ListView):
    template_name = "esport/events.html"
    context_object_name = "tournaments_going"

    def get_queryset(self):
        """
        return the outgoing tournament.
        """
        return Tournament.objects.order_by("-date_started")


class MatchesView(generic.DetailView):
    model = Tournament
    template_name = "esport/matchlist.html"

    def get_queryset(self):
        """
        Show incoming matches.
        """
        return Tournament.objects

class VoteView(generic.DetailView):
    model = Tournament
    template_name = "esport/vote.html"
    def get_queryset(self):
        """
        Show incoming matches.
        """
        return Tournament.objects