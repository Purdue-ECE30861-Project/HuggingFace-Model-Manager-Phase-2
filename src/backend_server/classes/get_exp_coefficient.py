import math


def get_exp_coefficient(half_magnitude_point: float):
    return math.log2(0.5) / half_magnitude_point


def score_large_good(exp_coefficient: float, score: float):
    # should return a value between 0 and 1 that approaches 1 as score -> infinity
    if score < 0:
        return 0
    return 1 - (2 ** (
        score * exp_coefficient
    ))

def score_large_bad(exp_coefficient: float, score: float):
    # should return a value between 0 and 1 that approaches 0 as score -> infinity
    if score < 0:
        return 0
    return 2 ** (score * exp_coefficient)