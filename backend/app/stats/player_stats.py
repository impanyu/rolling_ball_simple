from datetime import datetime, timedelta

import pandas as pd


def compute_ranking_at_date(
    rankings: pd.DataFrame, player_name: str, match_date: datetime
) -> int | None:
    player_ranks = rankings[
        (rankings["player_name"] == player_name)
        & (rankings["ranking_date"] <= match_date)
    ]
    if player_ranks.empty:
        return None
    latest = player_ranks.loc[player_ranks["ranking_date"].idxmax()]
    return int(latest["ranking"])


def compute_win_rate_3m(
    matches: pd.DataFrame, player_name: str, match_date: datetime
) -> float | None:
    cutoff = match_date - timedelta(days=90)
    recent = matches[
        (matches["tourney_date"] >= cutoff) & (matches["tourney_date"] < match_date)
    ]
    wins = len(recent[recent["winner_name"] == player_name])
    losses = len(recent[recent["loser_name"] == player_name])
    total = wins + losses
    if total == 0:
        return None
    return wins / total
