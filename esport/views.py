from django.views import generic, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Match, MatchDay, MVPDayVote, MVPResetState, Prediction, Player, PlayerStats, Tournament, Team, UserProfile
from .forms import MatchPredictionForm
from django.forms import formset_factory
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator


    
def get_possible_scores(match):
    if match.best_of == 1:
        return [(1, 0)]  # Score unique pour BO1
    elif match.best_of == 3:
        return [(2, 0), (2, 1)]
    elif match.best_of == 5:
        return [(3, 0), (3, 1), (3, 2)]
    return []

def get_leaderboard(tournament):
    users = UserProfile.objects.all()
    leaderboard = []

    for user in users:
        # Points sur les matchs du tournoi
        predictions = Prediction.objects.filter(
            user=user,
            match__match_day__tournament=tournament
        ).select_related('match', 'predicted_winner')
        
        user_points = 0
        for pred in predictions:
            user_points += pred.calculate_points()

        # Points Fantasy MVP par journée (somme des KDAs)
        mvp_votes = MVPDayVote.objects.filter(
            user=user,
            match_day__tournament=tournament
        ).select_related('fantasy_pick', 'match_day')

        mvp_points = 0
        for vote in mvp_votes:
            mvp_points += vote.calculate_points()

        total_points = user_points + mvp_points

        leaderboard.append({
            'user': user,
            'points': total_points,
            'match_points': user_points,
            'mvp_points': mvp_points,
        })
    # Classement décroissant
    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    return leaderboard

class TournamentlistView(generic.ListView):
    template_name = "esport/events.html"
    context_object_name = "tournaments_going"

    def get_queryset(self):
        """
        return the outgoing tournament.
        """
        return Tournament.objects.order_by("-date_started")


def matchlist(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    now = timezone.now()
    upcoming_matches = Match.objects.filter(
        match_day__tournament=tournament,
        scheduled_time__gte=now
    ).order_by('scheduled_time')

    leaderboard = get_leaderboard(tournament)

    return render(request, 'esport/matchlist.html', {
        'tournament': tournament,
        'upcoming_matches': upcoming_matches,
        'leaderboard' : leaderboard,
    })

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
        reset_state, _ = MVPResetState.objects.get_or_create(tournament=tournament)
        current_reset = reset_state.reset_id



        matchdays = MatchDay.objects.filter(tournament=tournament, date__gte=today).order_by("date").prefetch_related("matches")

        for matchday in matchdays:
            for match in matchday.matches.all():
                match.possible_scores = get_possible_scores(match)

        # Load Existing predictions
        predictions = Prediction.objects.filter(
            user=request.user,
            match__match_day__in=matchdays
        )
        predictions_by_match = {pred.match.id: pred for pred in predictions}
        
        
        # Load Existing Fantasy
        user_picks = set(
            MVPDayVote.objects.filter(
                user=request.user,
                match_day__tournament=tournament,
                reset_id=current_reset,
            ).values_list('fantasy_pick_id', flat=True)
        )

        user_mvp_votes = MVPDayVote.objects.filter(
            user=request.user,
            match_day__in=matchdays,
            reset_id=current_reset
        )

        fantasy_by_day = {vote.match_day.id: vote.fantasy_pick_id for vote in user_mvp_votes}

        context = {
            "tournament": tournament,
            "matchdays": matchdays,
            "predictions_by_match": predictions_by_match,
            "already_picked_players": user_picks,
            "fantasy_by_day": fantasy_by_day,
        }
        return render(request, "esport/fantasy.html", context)

    def post(self, request, slug):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('account_login')}?next={request.path}")

        tournament = get_object_or_404(Tournament, slug=slug)
        reset_state, created = MVPResetState.objects.get_or_create(tournament=tournament)
        current_reset = reset_state.reset_id
        today = timezone.now().date()
        matchdays = MatchDay.objects.filter(
            tournament=tournament, date__gte=today
        ).order_by("date").prefetch_related("matches")

        picks = []

        for matchday in matchdays:
            fantasy_pick_id = request.POST.get(f"fantasy_{matchday.id}")
            if fantasy_pick_id:
                picks.append(fantasy_pick_id)

        if len(picks) != len(set(picks)):
            messages.error(request, "Vous ne pouvez pas choisir deux fois le même joueur comme MVP pour ce tournoi pendant cette période.")
            return redirect(request.path)

        already_picked = MVPDayVote.objects.filter(
            user=request.user,
            match_day__tournament=tournament,
            fantasy_pick_id__in=picks,
            reset_id=current_reset,
        )
        if already_picked.exists():
            messages.error(request, "Vous avez déjà choisi au moins un de ces joueurs comme MVP sur ce tournoi pendant cette période.")
            return redirect(request.path)

        for matchday in matchdays:
            fantasy_pick_id = request.POST.get(f"fantasy_{matchday.id}")

            if fantasy_pick_id:
                MVPDayVote.objects.update_or_create(
                    user=request.user,
                    match_day=matchday,
                    reset_id=current_reset,
                    defaults={'fantasy_pick_id': fantasy_pick_id,},
                )

            for match in matchday.matches.all():
                match_id = str(match.id)
                winner_id = request.POST.get(f"winner_{match_id}")
                predicted_score = request.POST.get(f"score_{match_id}")

                if winner_id and predicted_score:
                    prediction, created = Prediction.objects.get_or_create(
                        user=request.user,
                        match=match,
                        defaults={
                            "predicted_winner_id": winner_id,
                            "predicted_score": predicted_score,
                        }
                    )
                    if not created:
                        prediction.predicted_winner_id = winner_id
                        prediction.predicted_score = predicted_score
                        prediction.save()

        messages.success(request,"Your pronostics have been saved !")
        return redirect("esport:matchlist", slug=tournament.slug)