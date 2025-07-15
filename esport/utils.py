

def get_possible_scores(match):
    bo = getattr(match, 'best_of', None)
    if bo == 1:
        return [(1, 0)]
    elif bo == 3:
        return [(2, 0), (2, 1)]
    elif bo == 5:
        return [(3, 0), (3, 1), (3, 2)]
    return []