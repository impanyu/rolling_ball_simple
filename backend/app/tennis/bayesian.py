def bayesian_update_p(
    prior_p: float,
    serve_wins: int,
    serve_total: int,
    prior_strength: int = 20,
) -> float:
    if serve_total == 0:
        return prior_p
    alpha_0 = prior_p * prior_strength
    beta_0 = (1 - prior_p) * prior_strength
    alpha_post = alpha_0 + serve_wins
    beta_post = beta_0 + (serve_total - serve_wins)
    return alpha_post / (alpha_post + beta_post)


def compute_p(first_in: float, first_won: float, second_won: float) -> float:
    return first_in * first_won + (1 - first_in) * second_won


def update_serve_components(
    prior_first_in: float,
    prior_first_won: float,
    prior_second_won: float,
    obs_1st_in: int,
    obs_1st_total: int,
    obs_1st_won: int,
    obs_1st_serve_points: int,
    obs_2nd_won: int,
    obs_2nd_serve_points: int,
    prior_strength: int = 20,
) -> dict:
    fi = bayesian_update_p(prior_first_in, obs_1st_in, obs_1st_total, prior_strength) if obs_1st_total > 0 else prior_first_in
    fw = bayesian_update_p(prior_first_won, obs_1st_won, obs_1st_serve_points, prior_strength) if obs_1st_serve_points > 0 else prior_first_won
    sw = bayesian_update_p(prior_second_won, obs_2nd_won, obs_2nd_serve_points, prior_strength) if obs_2nd_serve_points > 0 else prior_second_won

    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(compute_p(fi, fw, sw), 4),
    }


PRIOR_STRENGTH = 20
WINDOW_SIZE = 50


def _get_window_stats(
    current_stats: dict,
    stats_history: list[dict],
    prefix: str,
) -> dict:
    """Get serve stats for the last WINDOW_SIZE serves using sliding window.

    If match has fewer than WINDOW_SIZE serves, uses all available data.
    Finds the snapshot closest to (current_total - WINDOW_SIZE) and computes delta.
    Returns dict with 1st/2nd serve wins and totals for the window.
    """
    current_1st_total = current_stats.get(f"{prefix}_1st_serve_total", 0)
    current_1st_won = current_stats.get(f"{prefix}_1st_serve_won", 0)
    current_2nd_total = current_stats.get(f"{prefix}_2nd_serve_total", 0)
    current_2nd_won = current_stats.get(f"{prefix}_2nd_serve_won", 0)
    current_total = current_1st_total + current_2nd_total

    if current_total <= WINDOW_SIZE or not stats_history:
        # Use all available data (match shorter than window)
        return {
            "1st_total": current_1st_total,
            "1st_won": current_1st_won,
            "2nd_total": current_2nd_total,
            "2nd_won": current_2nd_won,
            "total": current_total,
        }

    # Find snapshot closest to WINDOW_SIZE serves ago
    target = current_total - WINDOW_SIZE
    best_snap = None
    best_diff = float("inf")
    for snap in stats_history:
        snap_total = snap.get(f"{prefix}_1st_serve_total", 0) + snap.get(f"{prefix}_2nd_serve_total", 0)
        diff = abs(snap_total - target)
        if diff < best_diff:
            best_diff = diff
            best_snap = snap

    if not best_snap:
        return {
            "1st_total": current_1st_total,
            "1st_won": current_1st_won,
            "2nd_total": current_2nd_total,
            "2nd_won": current_2nd_won,
            "total": current_total,
        }

    # Compute window = current - snapshot
    w_1st_total = max(0, current_1st_total - best_snap.get(f"{prefix}_1st_serve_total", 0))
    w_1st_won = max(0, current_1st_won - best_snap.get(f"{prefix}_1st_serve_won", 0))
    w_2nd_total = max(0, current_2nd_total - best_snap.get(f"{prefix}_2nd_serve_total", 0))
    w_2nd_won = max(0, current_2nd_won - best_snap.get(f"{prefix}_2nd_serve_won", 0))

    return {
        "1st_total": w_1st_total,
        "1st_won": w_1st_won,
        "2nd_total": w_2nd_total,
        "2nd_won": w_2nd_won,
        "total": w_1st_total + w_2nd_total,
    }


def multi_scale_p(
    prior_serve: dict,
    match_stats: dict | None,
    stats_history: list[dict] | None,
    prefix: str,
) -> dict:
    """Compute p using prior (20 pts) + moving window (up to 50 serves).

    Prior: Tennis Abstract season data as 20 virtual samples.
    Observations: last up to 50 serve points (sliding window of 1st/2nd serve data).
    Bayesian update each component separately, then combine.
    """
    p_far = prior_serve["p_serve"]
    far_fi = prior_serve.get("first_in", 0.60)
    far_fw = prior_serve.get("first_won", 0.70)
    far_sw = prior_serve.get("second_won", 0.50)

    if not match_stats:
        return {
            "first_in": far_fi,
            "first_won": far_fw,
            "second_won": far_sw,
            "p_serve": p_far,
            "p_far": p_far,
            "window_size": 0,
        }

    # Get sliding window stats (last up to 50 serves)
    window = _get_window_stats(match_stats, stats_history or [], prefix)

    # Bayesian update each component: prior (20 pts) + window observations
    total_serves = window["1st_total"] + window["2nd_total"]
    fi = bayesian_update_p(far_fi, window["1st_total"], total_serves, PRIOR_STRENGTH) if total_serves > 0 else far_fi
    fw = bayesian_update_p(far_fw, window["1st_won"], window["1st_total"], PRIOR_STRENGTH) if window["1st_total"] > 0 else far_fw
    sw = bayesian_update_p(far_sw, window["2nd_won"], window["2nd_total"], PRIOR_STRENGTH) if window["2nd_total"] > 0 else far_sw

    p_updated = compute_p(fi, fw, sw)

    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(p_updated, 4),
        "p_far": round(p_far, 4),
        "window_size": window["total"],
    }
