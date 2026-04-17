import pytest
from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_max_prob_distribution, win_prob_at_state


def test_win_prob_at_state_start_of_game():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    prob = win_prob_at_state(state, table, 0.65, 0.60)
    assert 0.5 < prob < 0.9


def test_win_prob_at_state_mid_game():
    """Mid-game states (e.g. 30-0) should return a valid probability."""
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    # A is serving, leading 30-0 (points_a=2, points_b=0 in server/receiver encoding)
    state = MatchState(points_a=2, points_b=0, is_a_serving=True)
    prob = win_prob_at_state(state, table, 0.65, 0.60)
    # Should be higher than start-of-game since server is ahead
    start_prob = win_prob_at_state(MatchState(), table, 0.65, 0.60)
    assert prob > start_prob


def test_simulate_returns_correct_shape():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    result = simulate_max_prob_distribution(state, 0.65, 0.60, table, 1000)
    assert result["total_count"] == 1000
    assert len(result["histogram"]) == 20
    assert "stats" in result
    assert "current_win_prob" in result


def test_simulate_histogram_sums_to_100():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    result = simulate_max_prob_distribution(MatchState(), 0.65, 0.60, table, 10000)
    total_pct = sum(b["percentage"] for b in result["histogram"])
    assert abs(total_pct - 100.0) < 0.5


def test_simulate_max_prob_always_gte_current():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState()
    current = win_prob_at_state(state, table, 0.65, 0.60)
    result = simulate_max_prob_distribution(state, 0.65, 0.60, table, 5000)
    assert result["stats"]["mean"] >= current * 100 - 1


def test_simulate_from_winning_position():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    state = MatchState(sets_a=1, games_a=5, games_b=0, is_a_serving=True)
    result = simulate_max_prob_distribution(state, 0.65, 0.60, table, 5000)
    assert result["stats"]["mean"] > 90


def test_simulate_deterministic_p1():
    table = build_win_prob_table(p_a=1.0, p_b=0.0)
    result = simulate_max_prob_distribution(MatchState(), 1.0, 0.0, table, 100)
    assert result["stats"]["mean"] == pytest.approx(100.0)
