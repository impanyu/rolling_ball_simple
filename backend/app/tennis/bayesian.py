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
    """Update each serve component separately using Bayesian updating.

    Returns dict with updated first_in, first_won, second_won, and combined p.
    """
    fi = bayesian_update_p(prior_first_in, obs_1st_in, obs_1st_total, prior_strength) if obs_1st_total > 0 else prior_first_in
    fw = bayesian_update_p(prior_first_won, obs_1st_won, obs_1st_serve_points, prior_strength) if obs_1st_serve_points > 0 else prior_first_won
    sw = bayesian_update_p(prior_second_won, obs_2nd_won, obs_2nd_serve_points, prior_strength) if obs_2nd_serve_points > 0 else prior_second_won

    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(compute_p(fi, fw, sw), 4),
    }
