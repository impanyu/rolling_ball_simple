PRIOR_POINTS = 50


def compute_p(first_in: float, first_won: float, second_won: float) -> float:
    return first_in * first_won + (1 - first_in) * second_won


def multi_scale_p(
    prior_serve: dict,
    match_stats: dict | None,
    stats_history: list[dict] | None,
    prefix: str,
) -> dict:
    """Compute p using fixed 50-point prior + cumulative match data.

    Prior: 50 virtual points from Tennis Abstract (fixed, never removed).
    Match: all cumulative serve data from the current match (no window cap).
    Each component weighted by point count: prior 50 + match N.
    """
    far_fi = prior_serve.get("first_in", 0.60)
    far_fw = prior_serve.get("first_won", 0.70)
    far_sw = prior_serve.get("second_won", 0.50)
    p_far = prior_serve.get("p_serve", compute_p(far_fi, far_fw, far_sw))

    if not match_stats:
        return {
            "first_in": far_fi,
            "first_won": far_fw,
            "second_won": far_sw,
            "p_serve": p_far,
            "p_far": p_far,
            "window_size": 0,
        }

    # Get cumulative match stats
    match_1st_total = match_stats.get(f"{prefix}_1st_serve_total", 0)
    match_1st_won = match_stats.get(f"{prefix}_1st_serve_won", 0)
    match_2nd_total = match_stats.get(f"{prefix}_2nd_serve_total", 0)
    match_2nd_won = match_stats.get(f"{prefix}_2nd_serve_won", 0)
    match_serves = match_1st_total + match_2nd_total

    # Compute match component rates
    match_fi = match_1st_total / match_serves if match_serves > 0 else far_fi
    match_fw = match_1st_won / match_1st_total if match_1st_total > 0 else far_fw
    match_sw = match_2nd_won / match_2nd_total if match_2nd_total > 0 else far_sw

    # Weighted average: 50 prior points + match_serves match points
    total_pts = PRIOR_POINTS + match_serves
    w_prior = PRIOR_POINTS / total_pts
    w_match = match_serves / total_pts

    fi = w_prior * far_fi + w_match * match_fi
    fw = w_prior * far_fw + w_match * match_fw
    sw = w_prior * far_sw + w_match * match_sw

    p_updated = compute_p(fi, fw, sw)

    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(p_updated, 4),
        "p_far": round(p_far, 4),
        "window_size": match_serves,
    }


# Legacy compatibility
def bayesian_update_p(prior_p, serve_wins, serve_total, prior_strength=20):
    if serve_total == 0:
        return prior_p
    alpha_0 = prior_p * prior_strength
    beta_0 = (1 - prior_p) * prior_strength
    return (alpha_0 + serve_wins) / (alpha_0 + beta_0 + serve_total)


def update_serve_components(prior_first_in, prior_first_won, prior_second_won,
                            obs_1st_in, obs_1st_total, obs_1st_won, obs_1st_serve_points,
                            obs_2nd_won, obs_2nd_serve_points, prior_strength=20):
    fi = bayesian_update_p(prior_first_in, obs_1st_in, obs_1st_total, prior_strength) if obs_1st_total > 0 else prior_first_in
    fw = bayesian_update_p(prior_first_won, obs_1st_won, obs_1st_serve_points, prior_strength) if obs_1st_serve_points > 0 else prior_first_won
    sw = bayesian_update_p(prior_second_won, obs_2nd_won, obs_2nd_serve_points, prior_strength) if obs_2nd_serve_points > 0 else prior_second_won
    return {"first_in": round(fi, 4), "first_won": round(fw, 4), "second_won": round(sw, 4),
            "p_serve": round(compute_p(fi, fw, sw), 4)}
