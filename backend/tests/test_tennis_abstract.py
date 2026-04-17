import pytest
from app.scraper.tennis_abstract import parse_serve_stats_from_text


def test_parse_serve_stats():
    text = "Last 52 64-17 (79%)12-11 (52%)10.4%57.8%74.5%52.3%42.6%1.22"
    result = parse_serve_stats_from_text(text)
    assert result is not None
    assert result["first_in"] == pytest.approx(0.578, abs=0.01)
    assert result["first_won"] == pytest.approx(0.745, abs=0.01)
    assert result["second_won"] == pytest.approx(0.523, abs=0.01)
    assert 0.60 < result["p_serve"] < 0.70


def test_parse_serve_stats_no_match():
    result = parse_serve_stats_from_text("No data here")
    assert result is None


def test_parse_serve_stats_career_only():
    text = "Career 393-162 (71%)93-73 (56%)0.0%0.0%71.7%0.0%43.2%0.43"
    result = parse_serve_stats_from_text(text)
    assert result is None
