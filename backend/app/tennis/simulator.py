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

        p_after_a = table.get(state_a_wins.key(), 1.0 if state_a_wins.sets_a == 2 else (0.0 if state_a_wins.sets_b == 2 else 0.5))
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
            1.0 if state_after_a.sets_a == 2 else (0.0 if state_after_a.sets_b == 2 else 0.5),
        )
        p_after_b = table.get(
            state_after_b.key(),
            1.0 if state_after_b.sets_a == 2 else (0.0 if state_after_b.sets_b == 2 else 0.5),
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


MAX_PATH_POINTS = 30
HORIZON_POINTS = [10, 20, 30]
HORIZON_WEIGHTS = {n: 1.0 / n for n in HORIZON_POINTS}


def _build_histogram(values_pct: List[float], n_bins: int = 20, bin_width: float = 5.0) -> list:
    bins = [0] * n_bins
    for v in values_pct:
        idx = int(v // bin_width)
        if idx >= n_bins:
            idx = n_bins - 1
        bins[idx] += 1
    total = len(values_pct)
    return [
        {
            "bin_start": i * bin_width,
            "bin_end": (i + 1) * bin_width,
            "count": bins[i],
            "percentage": round((bins[i] / total) * 100.0, 2) if total > 0 else 0,
        }
        for i in range(n_bins)
    ]


def _compute_stats(values_pct: List[float]) -> dict:
    if not values_pct:
        return {"mean": 0, "median": 0, "std": 0}
    return {
        "mean": round(statistics.mean(values_pct), 2),
        "median": round(statistics.median(values_pct), 2),
        "std": round(statistics.stdev(values_pct), 2) if len(values_pct) > 1 else 0,
    }


def simulate_combined(
    start_state: MatchState,
    p_a: float,
    p_b: float,
    table: Dict[Tuple, float],
    n_simulations: int = 100_000,
    max_points: int = MAX_PATH_POINTS,
    horizons: List[int] | None = None,
    slope_a: float = 0.0,
    slope_b: float = 0.0,
) -> dict:
    """Unified simulation with p trend (slope) per serve point.

    Each path simulates up to max_points. p values drift by slope per point:
    p_a(t) = clamp(p_a + slope_a * t, 0.2, 0.9)
    p_b(t) = clamp(p_b + slope_b * t, 0.2, 0.9)
    """
    if horizons is None:
        horizons = HORIZON_POINTS

    rng = random.Random()
    current_win_prob = win_prob_at_state(start_state, table, p_a, p_b) * 100.0

    horizon_values: Dict[int, List[float]] = {h: [] for h in horizons}
    max_probs_a: List[float] = []
    min_probs_a: List[float] = []
    all_probs: List[float] = []
    horizon_set = set(horizons)

    for sim_idx in range(n_simulations):
        state = start_state
        init_prob = win_prob_at_state(state, table, p_a, p_b)
        path_max = init_prob
        path_min = init_prob
        recorded_horizons: set[int] = set()

        for point_idx in range(1, max_points + 1):
            if state.is_terminal():
                terminal_prob = 1.0 if state.sets_a == 2 else 0.0
                if terminal_prob > path_max:
                    path_max = terminal_prob
                if terminal_prob < path_min:
                    path_min = terminal_prob
                all_probs.append(terminal_prob * 100.0)
                for h in horizons:
                    if h not in recorded_horizons:
                        horizon_values[h].append(terminal_prob * 100.0)
                        recorded_horizons.add(h)
                break

            pa_t = max(0.2, min(0.9, p_a + slope_a * point_idx))
            pb_t = max(0.2, min(0.9, p_b + slope_b * point_idx))
            p_a_point = pa_t if state.is_a_serving else (1.0 - pb_t)
            a_wins_point = rng.random() < p_a_point
            state = next_state(state, a_wins_point)

            if state.is_terminal():
                prob = 1.0 if state.sets_a == 2 else 0.0
            else:
                prob = win_prob_at_state(state, table, p_a, p_b)

            if prob > path_max:
                path_max = prob
            if prob < path_min:
                path_min = prob

            all_probs.append(prob * 100.0)

            if point_idx in horizon_set and point_idx not in recorded_horizons:
                horizon_values[point_idx].append(prob * 100.0)
                recorded_horizons.add(point_idx)

        for h in horizons:
            if h not in recorded_horizons:
                final_prob = (1.0 if state.sets_a == 2 else 0.0) if state.is_terminal() else win_prob_at_state(state, table, p_a, p_b)
                horizon_values[h].append(final_prob * 100.0)

        max_probs_a.append(path_max * 100.0)
        min_probs_a.append(path_min * 100.0)

    # Build time-slice results
    slices = []
    for h in horizons:
        vals = horizon_values[h]
        slices.append({
            "horizon": h,
            "total_count": len(vals),
            "histogram": _build_histogram(vals),
            "stats": _compute_stats(vals),
        })

    # Build combined histogram from ALL probabilities across all paths

    return {
        "current_win_prob": round(current_win_prob, 2),
        "slices": slices,
        "combined": {
            "total_count": len(all_probs),
            "histogram": _build_histogram(all_probs),
            "stats": _compute_stats(all_probs) if all_probs else {"mean": 0, "median": 0, "std": 0},
        },
        "max_prob_a": {
            "total_count": n_simulations,
            "histogram": _build_histogram(max_probs_a),
            "stats": _compute_stats(max_probs_a),
        },
        "min_prob_a": {
            "total_count": n_simulations,
            "histogram": _build_histogram(min_probs_a),
            "stats": _compute_stats(min_probs_a),
        },
    }


# Keep backward compatibility
def simulate_time_slices(*args, **kwargs):
    return simulate_combined(*args, **kwargs)


def simulate_max_prob(*args, **kwargs):
    return simulate_combined(*args, **kwargs)


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
    mean_val = statistics.mean(max_probs_pct)
    median_val = statistics.median(max_probs_pct)
    std_val = statistics.stdev(max_probs_pct) if n_simulations > 1 else 0.0

    current_win_prob = win_prob_at_state(start_state, table, p_a, p_b) * 100.0

    return {
        "current_win_prob": round(current_win_prob, 2),
        "total_count": n_simulations,
        "histogram": histogram,
        "stats": {
            "mean": round(mean_val, 2),
            "median": round(median_val, 2),
            "std": round(std_val, 2),
        },
    }
