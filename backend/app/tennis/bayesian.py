def bayesian_update_p(
    prior_p: float,
    serve_wins: int,
    serve_total: int,
    prior_strength: int = 100,
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
    prior_strength: int = 50,
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


W_NEAR = 0.35
W_MID = 0.40
W_FAR = 0.25

NEAR_WINDOW = 10


def weighted_p(p_far: float, p_mid: float, p_near: float | None) -> float:
    if p_near is None:
        total = W_FAR + W_MID
        return (W_FAR / total) * p_far + (W_MID / total) * p_mid
    return W_FAR * p_far + W_MID * p_mid + W_NEAR * p_near


def compute_near_p_from_history(
    current_won: int,
    current_total: int,
    stats_history: list[dict],
    prefix: str,
    window: int = NEAR_WINDOW,
) -> float | None:
    """Find a snapshot ~window serve points ago and compute p from the delta.

    stats_history: list of cumulative stat snapshots (oldest first).
    Finds the snapshot where total was closest to (current_total - window).
    """
    if not stats_history or current_total < window:
        return None

    target_total = current_total - window

    # Find the snapshot closest to target_total
    best_snap = None
    best_diff = float("inf")
    for snap in stats_history:
        snap_total = snap.get(f"{prefix}_serve_total", 0)
        diff = abs(snap_total - target_total)
        if diff < best_diff:
            best_diff = diff
            best_snap = snap

    if best_snap is None:
        return None

    snap_won = best_snap.get(f"{prefix}_serve_won", 0)
    snap_total = best_snap.get(f"{prefix}_serve_total", 0)

    recent_total = current_total - snap_total
    recent_won = current_won - snap_won

    if recent_total < 5:
        return None

    return max(0.0, min(1.0, recent_won / recent_total))


def multi_scale_p(
    prior_serve: dict,
    match_stats: dict | None,
    stats_history: list[dict] | None,
    prefix: str,
) -> dict:
    """Compute p value using three time scales: far (prior), mid (match), near (sliding window).

    prior_serve: dict with first_in, first_won, second_won, p_serve
    match_stats: current cumulative FlashScore stats (or None)
    stats_history: list of previous cumulative stat snapshots for sliding window (or None)
    prefix: "a" or "b"
    """
    p_far = prior_serve["p_serve"]

    if not match_stats:
        return {**prior_serve, "p_weighted": p_far, "p_far": p_far, "p_mid": None, "p_near": None}

    match_won = match_stats.get(f"{prefix}_serve_won", 0)
    match_total = match_stats.get(f"{prefix}_serve_total", 0)
    p_mid = match_won / match_total if match_total > 0 else p_far

    p_near = None
    if stats_history:
        p_near = compute_near_p_from_history(match_won, match_total, stats_history, prefix)

    p_weighted = weighted_p(p_far, p_mid, p_near)

    return {
        **prior_serve,
        "p_serve": round(p_weighted, 4),
        "p_weighted": round(p_weighted, 4),
        "p_far": round(p_far, 4),
        "p_mid": round(p_mid, 4) if match_total > 0 else None,
        "p_near": round(p_near, 4) if p_near is not None else None,
    }
