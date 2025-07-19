import datetime
from datetime import date, timedelta
from django.views import generic, View
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Match, MatchDay, MVPDayVote, MVPResetState, Prediction, Player, PlayerStats, Tournament, Team, UserProfile
from .forms import MatchPredictionForm
from django.forms import formset_factory
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .utils import get_possible_scores 

def get_leaderboard(tournament):
    # Only users who have at least one Prediction or MVPDayVote for this tournament
    prediction_users = set(
        Prediction.objects.filter(
            match__match_day__tournament=tournament
        ).values_list('user_id', flat=True)
    )
    mvp_users = set(
        MVPDayVote.objects.filter(
            match_day__tournament=tournament
        ).values_list('user_id', flat=True)
    )
    participating_user_ids = prediction_users | mvp_users  # union

    users = UserProfile.objects.filter(id__in=participating_user_ids)

    leaderboard = []

    for user in users:
        # Points from match predictions
        predictions = Prediction.objects.filter(
            user=user,
            match__match_day__tournament=tournament
        ).select_related('match', 'predicted_winner')
        
        user_points = sum(pred.calculate_points() for pred in predictions)

        # Points from fantasy MVPs
        mvp_votes = MVPDayVote.objects.filter(
            user=user,
            match_day__tournament=tournament
        ).select_related('fantasy_pick', 'match_day')

        mvp_points = sum(vote.calculate_points() for vote in mvp_votes)

        total_points = user_points + mvp_points

        leaderboard.append({
            'user': user,
            'points': total_points,
            'match_points': user_points,
            'mvp_points': mvp_points,
        })

    # Sort descending by points
    leaderboard.sort(key=lambda x: x['points'], reverse=True)
    return leaderboard


class TournamentListView(generic.TemplateView):
    template_name = "esport/events.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.now().date()
        # Tournaments that are ongoing or start in the next 7 days
        context['tournaments_going'] = Tournament.objects.filter(
            date_ended__gte=now, date_started__lte=now + timedelta(days=5)
        ).order_by('date_started')

        # Past tournaments, ended before today
        context['tournaments_past'] = Tournament.objects.filter(
            date_ended__lt=now
        ).order_by('-date_started')
        return context
        
def matchlist(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    now = timezone.now()
    upcoming_matches = Match.objects.filter(
        match_day__tournament=tournament,
        scheduled_time__gte=now
    ).order_by('scheduled_time')

    leaderboard = get_leaderboard(tournament)

    user_predictions = {}
    has_voted_all = False
    if request.user.is_authenticated:
        user_predictions_qs = Prediction.objects.filter(
            user=request.user,
            match__in=upcoming_matches
        )
        user_predictions = {p.match_id: p for p in user_predictions_qs}
        has_voted_all = upcoming_matches.count() > 0 and user_predictions_qs.count() == upcoming_matches.count()
    # -------------------------------------

    return render(request, 'esport/matchlist.html', {
        'tournament': tournament,
        'upcoming_matches': upcoming_matches,
        'leaderboard' : leaderboard,
        'user_predictions': user_predictions,
        'has_voted_all': has_voted_all,
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
        # Redirect if not authenticated
        if not request.user.is_authenticated:
            return redirect(f"{reverse('account_login')}?next={request.path}")

        tournament = get_object_or_404(Tournament, slug=slug)
        reset_state, created = MVPResetState.objects.get_or_create(tournament=tournament)
        current_reset = reset_state.reset_id
        today = timezone.now().date()

        # Get all upcoming matchdays (future or today)
        matchdays = MatchDay.objects.filter(
            tournament=tournament, date__gte=today
        ).order_by("date").prefetch_related("matches")

        # Collect submitted fantasy picks by matchday
        picks_by_day = {}
        for matchday in matchdays:
            fantasy_pick_id = request.POST.get(f"fantasy_{matchday.id}")
            if fantasy_pick_id:
                picks_by_day[matchday.id] = int(fantasy_pick_id)

        # Load all existing MVPDayVotes for this tournament & reset
        existing_votes = MVPDayVote.objects.filter(
            user=request.user,
            match_day__tournament=tournament,
            reset_id=current_reset,
        )

        # Set of already picked players for other matchdays
        already_picked = set(existing_votes.values_list('fantasy_pick_id', flat=True))

        # For each matchday, if the fantasy_pick hasn't changed, ignore that player in the duplicate check
        for vote in existing_votes:
            if picks_by_day.get(vote.match_day.id) == vote.fantasy_pick_id:
                already_picked.discard(vote.fantasy_pick_id)

        # Check for duplicate fantasy_pick in the whole submission (can't pick the same player twice, except for its own day)
        submitted_picks = set(picks_by_day.values())
        if already_picked & submitted_picks:
            messages.error(request, "You already picked at least one of these players as MVP for this tournament in this period.")
            return redirect(request.path)

        # Now process the votes
        for matchday in matchdays:
            fantasy_pick_id = request.POST.get(f"fantasy_{matchday.id}")
            if fantasy_pick_id:
                # Create or update the MVPDayVote for this matchday
                MVPDayVote.objects.update_or_create(
                    user=request.user,
                    match_day=matchday,
                    reset_id=current_reset,
                    defaults={'fantasy_pick_id': fantasy_pick_id},
                )

            for match in matchday.matches.all():
                match_id = str(match.id)
                winner_id = request.POST.get(f"winner_{match_id}")
                predicted_score = request.POST.get(f"score_{match_id}")

                if winner_id and predicted_score:
                    # Create or update the Prediction
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

        messages.success(request, "Your pronostics have been saved!")
        return redirect("esport:matchlist", slug=tournament.slug)
