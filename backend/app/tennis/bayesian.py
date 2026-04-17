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
