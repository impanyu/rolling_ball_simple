import pytest
import pandas as pd
from datetime import datetime
from app.stats.player_stats import compute_ranking_at_date, compute_win_rate_3m


@pytest.fixture
def sample_rankings():
    return pd.DataFrame({
        "ranking_date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01"]),
        "ranking": [1, 2, 5],
        "player_name": ["novak djokovic", "novak djokovic", "carlos alcaraz"],
    })


@pytest.fixture
def sample_matches():
    return pd.DataFrame({
        "tourney_date": pd.to_datetime([
            "2024-01-10", "2024-01-12", "2024-01-15",
            "2024-02-01", "2024-02-05",
        ]),
        "winner_name": [
            "novak djokovic", "novak djokovic", "carlos alcaraz",
            "novak djokovic", "carlos alcaraz",
        ],
        "loser_name": [
            "carlos alcaraz", "daniil medvedev", "novak djokovic",
            "carlos alcaraz", "daniil medvedev",
        ],
        "tourney_name": ["AO"] * 5,
    })


def test_compute_ranking_at_date(sample_rankings):
    rank = compute_ranking_at_date(sample_rankings, "novak djokovic", datetime(2024, 1, 5))
    assert rank == 1

    rank = compute_ranking_at_date(sample_rankings, "novak djokovic", datetime(2024, 1, 10))
    assert rank == 2

    rank = compute_ranking_at_date(sample_rankings, "unknown player", datetime(2024, 1, 5))
    assert rank is None


def test_compute_win_rate_3m(sample_matches):
    rate = compute_win_rate_3m(sample_matches, "novak djokovic", datetime(2024, 2, 10))
    assert rate == pytest.approx(0.75)

    rate = compute_win_rate_3m(sample_matches, "carlos alcaraz", datetime(2024, 2, 10))
    assert rate == pytest.approx(0.5)

    rate = compute_win_rate_3m(sample_matches, "unknown", datetime(2024, 2, 10))
    assert rate is None
