# backend/app/stats/sackmann.py
import logging
import subprocess
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ATP_REPO = "https://github.com/JeffSackmann/tennis_atp.git"
WTA_REPO = "https://github.com/JeffSackmann/tennis_wta.git"


def normalize_name(first: str, last: str) -> str:
    return f"{first.strip()} {last.strip()}".lower()


def clone_or_update(repo_url: str, dest: str) -> None:
    dest_path = Path(dest)
    if dest_path.exists() and (dest_path / ".git").exists():
        logger.info(f"Updating {dest}")
        subprocess.run(["git", "pull"], cwd=dest, capture_output=True, check=True)
    else:
        logger.info(f"Cloning {repo_url} to {dest}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, dest],
            capture_output=True,
            check=True,
        )


def ensure_repos(sackmann_dir: str) -> None:
    clone_or_update(ATP_REPO, f"{sackmann_dir}/tennis_atp")
    clone_or_update(WTA_REPO, f"{sackmann_dir}/tennis_wta")


def parse_rankings(repo_dir: str, tour: str = "atp") -> pd.DataFrame:
    repo_path = Path(repo_dir)

    players_file = repo_path / f"{tour}_players.csv"
    players = pd.read_csv(players_file, dtype=str, low_memory=False)
    name_map = {
        row["player_id"]: normalize_name(
            str(row.get("name_first", "")), str(row.get("name_last", ""))
        )
        for _, row in players.iterrows()
    }

    ranking_files = sorted(repo_path.glob(f"{tour}_rankings_*.csv"))
    frames = []
    for f in ranking_files:
        df = pd.read_csv(f, dtype={"player": str})
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["ranking_date", "ranking", "player_name"])

    rankings = pd.concat(frames, ignore_index=True).copy()
    rankings.loc[:, "player_name"] = rankings["player"].map(name_map)
    rankings = rankings.dropna(subset=["player_name"])
    rankings.loc[:, "ranking_date"] = pd.to_datetime(rankings["ranking_date"], format="%Y%m%d")
    rankings = rankings.rename(columns={"rank": "ranking"})
    return rankings[["ranking_date", "ranking", "player_name"]]


def parse_matches(repo_dir: str, tour: str = "atp") -> pd.DataFrame:
    repo_path = Path(repo_dir)
    match_files = sorted(repo_path.glob(f"{tour}_matches_*.csv"))
    frames = []
    for f in match_files:
        df = pd.read_csv(f, low_memory=False)
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["tourney_date", "winner_name", "loser_name", "tourney_name"])

    matches = pd.concat(frames, ignore_index=True).copy()
    matches.loc[:, "winner_name"] = matches["winner_name"].str.lower().str.strip()
    matches.loc[:, "loser_name"] = matches["loser_name"].str.lower().str.strip()
    matches.loc[:, "tourney_date"] = pd.to_datetime(matches["tourney_date"], format="%Y%m%d")
    return matches[["tourney_date", "winner_name", "loser_name", "tourney_name"]]
