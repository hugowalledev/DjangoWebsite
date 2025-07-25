from django.test import SimpleTestCase
from types import SimpleNamespace
from esport.utils import get_possible_scores

class GetPossibleScoresTest(SimpleTestCase):
    """
    Unit tests for the get_possible_scores utility function.
    This function determines the possible score outcomes for a match,
    depending on its 'best_of' value.
    """

    def test_bo1_returns_single_score(self):
        """
        For best_of = 1, the function should return only the single possible result.
        """
        match = SimpleNamespace(best_of=1)
        self.assertEqual(get_possible_scores(match), [(1, 0)])

    def test_bo3_returns_all_valid_scores(self):
        """
        For best_of = 3, the function should return both possible outcomes for a BO3 series.
        """
        match = SimpleNamespace(best_of=3)
        self.assertEqual(get_possible_scores(match), [(2, 0), (2, 1)])

    def test_bo5_returns_all_valid_scores(self):
        """
        For best_of = 5, the function should return all valid BO5 series results.
        """
        match = SimpleNamespace(best_of=5)
        self.assertEqual(get_possible_scores(match), [(3, 0), (3, 1), (3, 2)])

    def test_unexpected_best_of_returns_empty(self):
        """
        If 'best_of' is not 1, 3, or 5, the function should return an empty list.
        """
        match = SimpleNamespace(best_of=2)
        self.assertEqual(get_possible_scores(match), [])

    def test_missing_best_of_returns_empty(self):
        """
        If the match object does not have a 'best_of' attribute, return an empty list.
        """
        match = SimpleNamespace()
        self.assertEqual(get_possible_scores(match), [])

    def test_none_match_returns_empty(self):
        """
        If None is passed as match, the function should return an empty list.
        """
        self.assertEqual(get_possible_scores(None), [])

    def test_invalid_type_for_best_of(self):
        """
        If 'best_of' is not an integer, function should safely return an empty list.
        """
        match = SimpleNamespace(best_of="three")
        self.assertEqual(get_possible_scores(match), [])

