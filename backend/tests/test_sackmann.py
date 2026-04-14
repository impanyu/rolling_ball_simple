# backend/tests/test_sackmann.py
import os
import pytest
import pandas as pd
from app.stats.sackmann import parse_rankings, parse_matches, normalize_name


def test_normalize_name():
    assert normalize_name("Roger", "Federer") == "roger federer"
    assert normalize_name("Rafael", "Nadal") == "rafael nadal"
    assert normalize_name("  Carlos ", " Alcaraz ") == "carlos alcaraz"


def test_parse_rankings(tmp_path):
    csv_content = "ranking_date,rank,player\n20240101,1,104925\n20240101,2,106421\n"
    (tmp_path / "atp_rankings_current.csv").write_text(csv_content)

    players_content = "player_id,name_first,name_last\n104925,Novak,Djokovic\n106421,Carlos,Alcaraz\n"
    (tmp_path / "atp_players.csv").write_text(players_content)

    rankings = parse_rankings(str(tmp_path), tour="atp")
    assert len(rankings) == 2
    assert rankings.iloc[0]["player_name"] == "novak djokovic"
    assert rankings.iloc[0]["ranking"] == 1


def test_parse_matches(tmp_path):
    csv_content = (
        "tourney_id,tourney_name,tourney_date,winner_name,loser_name,score\n"
        "2024-001,Australian Open,20240115,Novak Djokovic,Carlos Alcaraz,6-3 6-4\n"
        "2024-001,Australian Open,20240116,Carlos Alcaraz,Daniil Medvedev,7-5 6-3\n"
    )
    (tmp_path / "atp_matches_2024.csv").write_text(csv_content)

    matches = parse_matches(str(tmp_path), tour="atp")
    assert len(matches) == 2
    assert matches.iloc[0]["winner_name"] == "novak djokovic"
