from django import forms
from .models import Team, Match

class MatchPredictionForm(forms.Form):
    match_id = forms.IntegerField(widget=forms.HiddenInput)
    predicted_winner = forms.ModelChoiceField(queryset=Team.objects.none())
    predicted_score_winner = forms.IntegerField(min_value=0, max_value=5)
    predicted_score_loser = forms.IntegerField(min_value=0, max_value=5)

    def __init__(self, *args, match=None, **kwargs):
        super().__init__(*args, **kwargs)
        if match:
            self.fields["predicted_winner"].queryset = Team.objects.filter(id__in=[match.blue_roster.id, match.red_roster.id])
            self.fields["match_id"].initial = match.id
