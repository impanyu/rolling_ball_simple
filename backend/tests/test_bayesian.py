import pytest
from app.tennis.bayesian import bayesian_update_p


def test_no_observations_returns_prior():
    p = bayesian_update_p(prior_p=0.65, serve_wins=0, serve_total=0)
    assert p == pytest.approx(0.65)


def test_observations_shift_posterior():
    p = bayesian_update_p(prior_p=0.65, serve_wins=40, serve_total=50)
    assert p > 0.65
    assert p < 0.80


def test_weak_performance_lowers_p():
    p = bayesian_update_p(prior_p=0.65, serve_wins=20, serve_total=50)
    assert p < 0.65


def test_large_sample_dominates_prior():
    p = bayesian_update_p(prior_p=0.65, serve_wins=400, serve_total=500, prior_strength=100)
    assert abs(p - 0.8) < 0.03


def test_prior_strength():
    p = bayesian_update_p(prior_p=0.65, serve_wins=8, serve_total=10, prior_strength=200)
    assert abs(p - 0.65) < 0.03
