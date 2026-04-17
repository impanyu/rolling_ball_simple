import pytest
from app.tennis.engine import MatchState, next_state, build_win_prob_table


def test_initial_state():
    s = MatchState()
    assert s.sets_a == 0 and s.sets_b == 0
    assert s.games_a == 0 and s.games_b == 0
    assert s.points_a == 0 and s.points_b == 0
    assert s.is_a_serving is True
    assert s.is_tiebreak is False
    assert s.is_terminal() is False


def test_point_advance_in_regular_game():
    s = MatchState()
    s1 = next_state(s, a_wins_point=True)
    assert s1.points_a == 1 and s1.points_b == 0

    s2 = next_state(s1, a_wins_point=True)
    assert s2.points_a == 2

    s3 = next_state(s2, a_wins_point=True)
    assert s3.points_a == 3

    s4 = next_state(s3, a_wins_point=True)
    assert s4.games_a == 1 and s4.games_b == 0
    assert s4.points_a == 0 and s4.points_b == 0
    assert s4.is_a_serving is False


def test_deuce_and_advantage():
    s = MatchState(points_a=3, points_b=3)
    s1 = next_state(s, a_wins_point=True)  # AD-40
    assert s1.points_a == 4

    s2 = next_state(s1, a_wins_point=False)  # back to deuce
    assert s2.points_a == 3 and s2.points_b == 3

    s3 = next_state(s1, a_wins_point=True)  # A wins game
    assert s3.games_a == 1
    assert s3.points_a == 0


def test_set_win():
    s = MatchState(games_a=5, games_b=0, points_a=3, is_a_serving=True)
    s1 = next_state(s, a_wins_point=True)
    assert s1.sets_a == 1
    assert s1.games_a == 0 and s1.games_b == 0


def test_tiebreak_at_6_6():
    s = MatchState(games_a=6, games_b=5, points_a=3, is_a_serving=False)
    s1 = next_state(s, a_wins_point=False)
    assert s1.games_a == 6 and s1.games_b == 6
    assert s1.is_tiebreak is True


def test_tiebreak_scoring():
    s = MatchState(games_a=6, games_b=6, is_tiebreak=True,
                   points_a=6, points_b=5, is_a_serving=True)
    s1 = next_state(s, a_wins_point=True)
    assert s1.sets_a == 1
    assert s1.is_tiebreak is False
    assert s1.games_a == 0 and s1.games_b == 0


def test_tiebreak_must_win_by_two():
    s = MatchState(games_a=6, games_b=6, is_tiebreak=True,
                   points_a=6, points_b=6, is_a_serving=True)
    s1 = next_state(s, a_wins_point=True)  # 7-6
    assert s1.is_tiebreak is True

    s2 = next_state(s1, a_wins_point=True)  # 8-6
    assert s2.sets_a == 1
    assert s2.is_tiebreak is False


def test_match_terminal():
    assert MatchState(sets_a=2).is_terminal() is True
    assert MatchState(sets_b=2).is_terminal() is True


def test_build_win_prob_table_extreme():
    table = build_win_prob_table(p_a=1.0, p_b=0.0)
    initial = MatchState()
    assert table[initial.key()] == pytest.approx(1.0)


def test_build_win_prob_table_symmetric():
    table = build_win_prob_table(p_a=0.6, p_b=0.6)
    initial = MatchState()
    prob = table[initial.key()]
    assert 0.45 < prob < 0.55


def test_build_win_prob_table_terminal_states():
    table = build_win_prob_table(p_a=0.65, p_b=0.60)
    assert table[MatchState(sets_a=2).key()] == 1.0
    assert table[MatchState(sets_b=2).key()] == 0.0
