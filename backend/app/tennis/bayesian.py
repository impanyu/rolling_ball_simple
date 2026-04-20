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


P_SLOPE_WINDOW = 10


def compute_p_slope(
    prior_serve: dict,
    stats_history: list[dict],
    prefix: str,
) -> float | None:
    """Compute the slope of p over the last ~10 serve points.

    Uses stats_history snapshots to compute p at each snapshot,
    then linear regression of p vs serve_count over the window.
    Returns slope (change in p per serve point), or None if insufficient data.
    """
    if not stats_history or len(stats_history) < 2:
        return None

    far_fi = prior_serve.get("first_in", 0.60)
    far_fw = prior_serve.get("first_won", 0.70)
    far_sw = prior_serve.get("second_won", 0.50)

    # Compute p at each snapshot
    points = []
    for snap in stats_history:
        s1t = snap.get(f"{prefix}_1st_serve_total", 0)
        s1w = snap.get(f"{prefix}_1st_serve_won", 0)
        s2t = snap.get(f"{prefix}_2nd_serve_total", 0)
        s2w = snap.get(f"{prefix}_2nd_serve_won", 0)
        total = s1t + s2t
        if total == 0:
            continue

        m_fi = s1t / total
        m_fw = s1w / s1t if s1t > 0 else far_fw
        m_sw = s2w / s2t if s2t > 0 else far_sw

        w_prior = PRIOR_POINTS / (PRIOR_POINTS + total)
        w_match = total / (PRIOR_POINTS + total)

        fi = w_prior * far_fi + w_match * m_fi
        fw = w_prior * far_fw + w_match * m_fw
        sw = w_prior * far_sw + w_match * m_sw

        p = compute_p(fi, fw, sw)
        points.append((total, p))

    if len(points) < 2:
        return None

    # Take snapshots covering the last ~P_SLOPE_WINDOW serve points
    last_total = points[-1][0]
    cutoff = last_total - P_SLOPE_WINDOW
    window_points = [(t, p) for t, p in points if t >= cutoff]
    if len(window_points) < 2:
        window_points = points[-3:]  # at least last 3 snapshots

    if len(window_points) < 2:
        return None

    # Linear regression: p = slope * serve_count + intercept
    x = [t for t, _ in window_points]
    y = [p for _, p in window_points]
    n = len(x)
    sx = sum(x)
    sy = sum(y)
    sxx = sum(xi * xi for xi in x)
    sxy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-10:
        return 0.0

    slope = (n * sxy - sx * sy) / denom
    return round(slope, 6)


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
