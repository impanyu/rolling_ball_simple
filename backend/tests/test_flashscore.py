import pytest
from app.scraper.flashscore import parse_pbp_elements


def test_parse_pbp_elements_basic():
    raw_elements = [
        {"parent_class": "matchHistoryRow__scoreBox", "text": "0", "winning": False},
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": True},
        {"parent_class": "matchHistoryRow__lostServe matchHistoryRow__away", "text": "LOST SERVE", "winning": False},
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": False},
        {"parent_class": "matchHistoryRow__scoreBox", "text": "1", "winning": True},
    ]
    result = parse_pbp_elements(raw_elements)
    assert result is not None
    assert "sets" in result
    assert "games" in result


def test_parse_pbp_elements_empty():
    result = parse_pbp_elements([])
    assert result is None
