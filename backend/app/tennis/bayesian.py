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
    """Compute serve point win rate from 3 components (all as fractions 0-1)."""
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


# Weights for near/mid/far time scales
W_NEAR = 0.35
W_MID = 0.40
W_FAR = 0.25


def weighted_p(
    p_far: float,
    p_mid: float,
    p_near: float | None,
) -> float:
    """Weighted combination of far (season prior), mid (match total), near (recent points).
    If near is not available, redistribute its weight to mid.
    """
    if p_near is None:
        # No recent data — just far + mid
        total = W_FAR + W_MID
        return (W_FAR / total) * p_far + (W_MID / total) * p_mid

    return W_FAR * p_far + W_MID * p_mid + W_NEAR * p_near


def compute_recent_p(
    current_won: int,
    current_total: int,
    prev_won: int,
    prev_total: int,
) -> float | None:
    """Compute p from the delta between two cumulative stat snapshots.
    Returns None if not enough recent data (< 5 points).
    """
    recent_total = current_total - prev_total
    recent_won = current_won - prev_won
    if recent_total < 5:
        return None
    return recent_won / recent_total


def multi_scale_p(
    prior_serve: dict,
    match_stats: dict | None,
    prev_stats: dict | None,
    prefix: str,
) -> dict:
    """Compute p value using three time scales: far (prior), mid (match), near (recent).

    prior_serve: dict with first_in, first_won, second_won, p_serve from Tennis Abstract
    match_stats: current cumulative FlashScore stats (or None)
    prev_stats: previous cumulative FlashScore stats for computing recent delta (or None)
    prefix: "a" or "b"
    """
    p_far = prior_serve["p_serve"]

    if not match_stats:
        return {**prior_serve, "p_weighted": p_far, "p_far": p_far, "p_mid": None, "p_near": None}

    # Mid: overall match p
    match_won = match_stats.get(f"{prefix}_serve_won", 0)
    match_total = match_stats.get(f"{prefix}_serve_total", 0)
    p_mid = match_won / match_total if match_total > 0 else p_far

    # Near: recent delta since last update
    p_near = None
    if prev_stats:
        prev_won = prev_stats.get(f"{prefix}_serve_won", 0)
        prev_total = prev_stats.get(f"{prefix}_serve_total", 0)
        p_near = compute_recent_p(match_won, match_total, prev_won, prev_total)

    p_weighted = weighted_p(p_far, p_mid, p_near)

    return {
        **prior_serve,
        "p_serve": round(p_weighted, 4),
        "p_weighted": round(p_weighted, 4),
        "p_far": round(p_far, 4),
        "p_mid": round(p_mid, 4) if match_total > 0 else None,
        "p_near": round(p_near, 4) if p_near is not None else None,
    }
