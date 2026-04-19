WINDOW_SIZE = 50


def compute_p(first_in: float, first_won: float, second_won: float) -> float:
    return first_in * first_won + (1 - first_in) * second_won


def _get_match_window_stats(
    current_stats: dict,
    stats_history: list[dict],
    prefix: str,
) -> dict:
    """Get serve stats for a sliding window from match data.

    If match has <= WINDOW_SIZE serves, return all match data.
    If match has > WINDOW_SIZE serves, find snapshot ~WINDOW_SIZE ago and return delta.
    """
    current_1st_total = current_stats.get(f"{prefix}_1st_serve_total", 0)
    current_1st_won = current_stats.get(f"{prefix}_1st_serve_won", 0)
    current_2nd_total = current_stats.get(f"{prefix}_2nd_serve_total", 0)
    current_2nd_won = current_stats.get(f"{prefix}_2nd_serve_won", 0)
    current_total = current_1st_total + current_2nd_total

    if current_total <= WINDOW_SIZE or not stats_history:
        return {
            "1st_total": current_1st_total,
            "1st_won": current_1st_won,
            "2nd_total": current_2nd_total,
            "2nd_won": current_2nd_won,
            "total": current_total,
        }

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

    return {
        "1st_total": max(0, current_1st_total - best_snap.get(f"{prefix}_1st_serve_total", 0)),
        "1st_won": max(0, current_1st_won - best_snap.get(f"{prefix}_1st_serve_won", 0)),
        "2nd_total": max(0, current_2nd_total - best_snap.get(f"{prefix}_2nd_serve_total", 0)),
        "2nd_won": max(0, current_2nd_won - best_snap.get(f"{prefix}_2nd_serve_won", 0)),
        "total": max(0, current_total - (best_snap.get(f"{prefix}_1st_serve_total", 0) + best_snap.get(f"{prefix}_2nd_serve_total", 0))),
    }


def multi_scale_p(
    prior_serve: dict,
    match_stats: dict | None,
    stats_history: list[dict] | None,
    prefix: str,
) -> dict:
    """Compute p using a fixed 50-point window that transitions from season to match data.

    - Match start: 50 points all from season prior
    - During match: (50 - match_serves) prior + match_serves match data
    - After 50 serves: pure sliding window of last 50 match serves
    Each component (first_in, first_won, second_won) weighted separately.
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
            "prior_pts": WINDOW_SIZE,
            "match_pts": 0,
        }

    window = _get_match_window_stats(match_stats, stats_history or [], prefix)
    match_serves = window["total"]

    # How many prior points to mix in
    prior_pts = max(0, WINDOW_SIZE - match_serves)

    # Compute match component rates from window
    match_total_serves = window["1st_total"] + window["2nd_total"]
    match_fi = window["1st_total"] / match_total_serves if match_total_serves > 0 else far_fi
    match_fw = window["1st_won"] / window["1st_total"] if window["1st_total"] > 0 else far_fw
    match_sw = window["2nd_won"] / window["2nd_total"] if window["2nd_total"] > 0 else far_sw

    # Weighted average: prior_pts from season + match_serves from match
    total_pts = prior_pts + match_serves
    if total_pts > 0:
        w_prior = prior_pts / total_pts
        w_match = match_serves / total_pts
    else:
        w_prior = 1.0
        w_match = 0.0

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
        "prior_pts": prior_pts,
        "match_pts": match_serves,
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
