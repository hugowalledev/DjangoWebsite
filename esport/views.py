from django.views import generic, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Match, MatchDay, Prediction, Player, Tournament, Team
from .forms import MatchPredictionForm
from django.forms import formset_factory
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator


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

class PredictionView(View):
    def get(self, request, slug):
        tournament = get_object_or_404(Tournament, slug=slug)
        today = timezone.now().date()

        matchdays = MatchDay.objects.filter(tournament=tournament, date__gte=today).order_by("date").prefetch_related("matches")

        # Charger les prédictions existantes de l'utilisateur
        predictions = Prediction.objects.filter(
            user=request.user,
            match__match_day__in=matchdays
        )

        # Clé : match.id, Valeur : prédiction
        predictions_by_match = {pred.match.id: pred for pred in predictions}

        # Clé : match_day.id, Valeur : fantasy pick (Player)
        fantasy_by_day = {
            pred.match.match_day.id: pred.fantasy_pick
            for pred in predictions if pred.fantasy_pick
        }

        context = {
            "tournament": tournament,
            "matchdays": matchdays,
            "predictions_by_match": predictions_by_match,
            "fantasy_by_day": fantasy_by_day,
        }
        return render(request, "esport/fantasy.html", context)

    def post(self, request, slug):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('account_login')}?next={request.path}")

        tournament = get_object_or_404(Tournament, slug=slug)
        today = timezone.now().date()
        matchdays = MatchDay.objects.filter(tournament=tournament, date__gte=today).order_by("date").prefetch_related("matches")

        for matchday in matchdays:
            for match in matchday.matches.all():
                match_id = str(match.id)
                winner_id = request.POST.get(f"winner_{match_id}")
                score_winner = request.POST.get(f"score_winner_{match_id}")
                score_loser = request.POST.get(f"score_loser_{match_id}")
                fantasy_pick_id = request.POST.get(f"fantasy_{matchday.id}")

                if winner_id and score_winner is not None and score_loser is not None:
                    prediction, created = Prediction.objects.get_or_create(
                        user=request.user,
                        match=match,
                        defaults={
                            "predicted_winner_id": winner_id,
                            "predicted_score_winner": score_winner,
                            "predicted_score_loser": score_loser,
                            "fantasy_pick_id": fantasy_pick_id if fantasy_pick_id else None
                        }
                    )

                    # Mise à jour si existait déjà
                    if not created:
                        prediction.predicted_winner_id = winner_id
                        prediction.predicted_score_winner = score_winner
                        prediction.predicted_score_loser = score_loser
                        if fantasy_pick_id:
                            prediction.fantasy_pick_id = fantasy_pick_id
                        prediction.save()

        return redirect("prediction", slug=tournament.slug)