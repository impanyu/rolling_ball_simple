"""
Monte Carlo simulator for tennis match win-probability distribution.

Simulates N random match paths from a given MatchState and records the
maximum P(A wins) observed along each path, building a histogram of those
peak probabilities.
"""
from __future__ import annotations

import random
import statistics
from typing import Dict, List, Tuple

from app.tennis.engine import (
    MatchState,
    _p_a_wins_tiebreak,
    _p_server_wins_game,
    _state_after_game,
    next_state,
)


def win_prob_at_state(
    state: MatchState,
    table: Dict[Tuple, float],
    p_a: float,
    p_b: float,
) -> float:
    """
    Compute P(A wins the match) at *any* state, including mid-game states that
    are not stored directly in the pre-built ``table``.

    The table produced by ``build_win_prob_table`` only contains start-of-game
    states (points_a == points_b == 0).  For mid-game states the function
    combines:

    * The closed-form probability that the current game is won by A, and
    * The table entries for the two possible post-game states.

    For tiebreak mid-points the same idea applies using ``_p_a_wins_tiebreak``.

    Terminal states (sets_a == 2 or sets_b == 2) return 1.0 / 0.0 directly.
    """
    if state.sets_a == 2:
        return 1.0
    if state.sets_b == 2:
        return 0.0

    key = state.key()

    # If the state is already in the table (start-of-game / start-of-tiebreak),
    # use it directly.
    if key in table:
        return table[key]

    if state.is_tiebreak:
        # p used by the closed-form function: P(A wins a tiebreak point).
        # In the tiebreak the serving player changes frequently, so we use the
        # same constant approximation that build_win_prob_table uses.
        p_point_a = p_a if state.is_a_serving else (1.0 - p_b)

        p_a_wins_tb = _p_a_wins_tiebreak(state.points_a, state.points_b, p_point_a)

        # Post-tiebreak states
        state_a_wins = MatchState(
            sets_a=state.sets_a + 1,
            sets_b=state.sets_b,
            games_a=0,
            games_b=0,
            points_a=0,
            points_b=0,
            is_a_serving=not state.is_a_serving,
            is_tiebreak=False,
        )
        state_b_wins = MatchState(
            sets_a=state.sets_a,
            sets_b=state.sets_b + 1,
            games_a=0,
            games_b=0,
            points_a=0,
            points_b=0,
            is_a_serving=not state.is_a_serving,
            is_tiebreak=False,
        )

        p_after_a = table.get(state_a_wins.key(), 1.0 if state_a_wins.sets_a == 2 else 0.0)
        p_after_b = table.get(state_b_wins.key(), 1.0 if state_b_wins.sets_a == 2 else 0.0)

        return p_a_wins_tb * p_after_a + (1.0 - p_a_wins_tb) * p_after_b

    else:
        # Regular game: points_a = server pts, points_b = receiver pts.
        p_server = p_a if state.is_a_serving else p_b
        p_sv_wins_game = _p_server_wins_game(state.points_a, state.points_b, p_server)
        p_a_wins_game = p_sv_wins_game if state.is_a_serving else (1.0 - p_sv_wins_game)

        state_after_a = _state_after_game(state, a_wins=True)
        state_after_b = _state_after_game(state, a_wins=False)

        p_after_a = table.get(
            state_after_a.key(),
            1.0 if state_after_a.sets_a == 2 else 0.0,
        )
        p_after_b = table.get(
            state_after_b.key(),
            1.0 if state_after_b.sets_a == 2 else 0.0,
        )

        return p_a_wins_game * p_after_a + (1.0 - p_a_wins_game) * p_after_b


def _simulate_one_path(
    start_state: MatchState,
    p_a: float,
    p_b: float,
    table: Dict[Tuple, float],
    rng: random.Random,
) -> float:
    """
    Simulate one complete match from ``start_state`` and return the maximum
    P(A wins) encountered at any state along the path (including the start).
    """
    state = start_state
    max_prob = win_prob_at_state(state, table, p_a, p_b)

    while not state.is_terminal():
        # Determine P(A wins the current point)
        if state.is_tiebreak:
            # Use current server to determine point probability
            p_a_point = p_a if state.is_a_serving else (1.0 - p_b)
        else:
            # A wins the point if A is serving and server wins, or B is serving
            # and receiver (A) wins.
            p_a_point = p_a if state.is_a_serving else (1.0 - p_b)

        a_wins_point = rng.random() < p_a_point
        state = next_state(state, a_wins_point)

        if not state.is_terminal():
            prob = win_prob_at_state(state, table, p_a, p_b)
            if prob > max_prob:
                max_prob = prob
        else:
            # Terminal: A wins → 1.0, B wins → 0.0
            terminal_prob = 1.0 if state.sets_a == 2 else 0.0
            if terminal_prob > max_prob:
                max_prob = terminal_prob

    return max_prob


def simulate_max_prob_distribution(
    start_state: MatchState,
    p_a: float,
    p_b: float,
    table: Dict[Tuple, float],
    n_simulations: int = 100_000,
) -> dict:
    """
    Simulate ``n_simulations`` match paths from ``start_state`` and build a
    distribution of the maximum P(A wins) observed per path.

    Returns a dict with:
    - ``current_win_prob``: P(A wins) at the start state (0–100 %)
    - ``total_count``: number of simulations run
    - ``histogram``: list of 20 dicts, each with
        ``bin_start``, ``bin_end``, ``count``, ``percentage``
        (bins cover [0 %, 5 %), [5 %, 10 %), ..., [95 %, 100 %])
    - ``stats``: dict with ``mean``, ``median``, ``p10``, ``p90`` (all in %)
    """
    rng = random.Random()

    max_probs: List[float] = []
    for _ in range(n_simulations):
        mp = _simulate_one_path(start_state, p_a, p_b, table, rng)
        max_probs.append(mp)

    # Convert to percentage
    max_probs_pct = [v * 100.0 for v in max_probs]

    # Build 20-bin histogram with 5 % wide bins [0,5), [5,10), ..., [95,100]
    n_bins = 20
    bin_width = 5.0
    bins = [0] * n_bins

    for v in max_probs_pct:
        idx = int(v // bin_width)
        if idx >= n_bins:
            idx = n_bins - 1  # clamp 100 % into last bin
        bins[idx] += 1

    histogram = []
    for i in range(n_bins):
        histogram.append(
            {
                "bin_start": i * bin_width,
                "bin_end": (i + 1) * bin_width,
                "count": bins[i],
                "percentage": (bins[i] / n_simulations) * 100.0,
            }
        )

    # Descriptive statistics (all in %)
    sorted_probs = sorted(max_probs_pct)
    mean_val = statistics.mean(max_probs_pct)
    median_val = statistics.median(max_probs_pct)
    p10_val = sorted_probs[int(0.10 * n_simulations)]
    p90_val = sorted_probs[min(int(0.90 * n_simulations), n_simulations - 1)]

    current_win_prob = win_prob_at_state(start_state, table, p_a, p_b) * 100.0

    return {
        "current_win_prob": current_win_prob,
        "total_count": n_simulations,
        "histogram": histogram,
        "stats": {
            "mean": mean_val,
            "median": median_val,
            "p10": p10_val,
            "p90": p90_val,
        },
    }
