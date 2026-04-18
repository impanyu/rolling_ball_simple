# backend/app/routes/simulate.py
import logging
import json
from pydantic import BaseModel
from fastapi import APIRouter

from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_time_slices, win_prob_at_state
from app.tennis.bayesian import update_serve_components, multi_scale_p

logger = logging.getLogger(__name__)
router = APIRouter()


class ScoreInput(BaseModel):
    sets: list[int]
    games: list[int]
    points: list[int]
    serving: str


class SimulateRequest(BaseModel):
    p_a: float
    p_b: float
    score: ScoreInput
    num_simulations: int = 100_000


class LookupRequest(BaseModel):
    player_input: str


def score_to_match_state(score: ScoreInput) -> MatchState:
    is_tiebreak = score.games[0] == 6 and score.games[1] == 6
    return MatchState(
        sets_a=score.sets[0],
        sets_b=score.sets[1],
        games_a=score.games[0],
        games_b=score.games[1],
        points_a=score.points[0],
        points_b=score.points[1],
        is_a_serving=(score.serving == "a"),
        is_tiebreak=is_tiebreak,
    )


def _update_p_from_stats(prior_serve: dict, stats: dict, prefix: str) -> dict:
    """Update serve components from FlashScore match stats."""
    obs_1st_in = stats.get(f"{prefix}_1st_serve_total", 0)  # 1st serves attempted
    obs_1st_total = obs_1st_in + stats.get(f"{prefix}_2nd_serve_total", 0)  # total serve points = 1st + 2nd
    obs_1st_won = stats.get(f"{prefix}_1st_serve_won", 0)
    obs_1st_serve_points = stats.get(f"{prefix}_1st_serve_total", 0)
    obs_2nd_won = stats.get(f"{prefix}_2nd_serve_won", 0)
    obs_2nd_serve_points = stats.get(f"{prefix}_2nd_serve_total", 0)

    # first_in = 1st serves in / total serve points
    # We approximate: obs_1st_in = obs_1st_serve_points (serves that were in play as 1st serve)
    return update_serve_components(
        prior_first_in=prior_serve["first_in"],
        prior_first_won=prior_serve["first_won"],
        prior_second_won=prior_serve["second_won"],
        obs_1st_in=obs_1st_serve_points,
        obs_1st_total=obs_1st_serve_points + obs_2nd_serve_points,
        obs_1st_won=obs_1st_won,
        obs_1st_serve_points=obs_1st_serve_points,
        obs_2nd_won=obs_2nd_won,
        obs_2nd_serve_points=obs_2nd_serve_points,
    )


@router.post("/api/simulate")
async def simulate(req: SimulateRequest):
    state = score_to_match_state(req.score)
    table = build_win_prob_table(req.p_a, req.p_b)

    # Debug: check if state is in table
    prob = win_prob_at_state(state, table, req.p_a, req.p_b)
    logger.info(f"SIMULATE: state={state.key()} p_a={req.p_a} p_b={req.p_b} in_table={state.key() in table} prob={prob:.4f}")
    if prob < 0.01 and not state.is_terminal():
        logger.error(f"SUSPICIOUS 0% prob for non-terminal state! score={req.score}")

    result = simulate_time_slices(
        state, req.p_a, req.p_b, table, req.num_simulations
    )
    return result


@router.post("/api/lookup-match")
async def lookup_match(req: LookupRequest):
    # Step 1: Use user input directly to search FlashScore + DDG (no LLM needed)
    # Split input into name parts for searching
    raw_input = req.player_input.strip()

    # Step 2: Search FlashScore for live match
    from app.scraper.flashscore import search_and_open_match, read_match_score, read_match_stats, read_match_surface, read_player_rankings, read_match_gender
    match_page, player_a, player_b = await search_and_open_match(raw_input, "")

    # If FlashScore search with empty second name found a match,
    # player names come from the URL. Otherwise use raw input as-is.
    if not match_page:
        # Try splitting input on common separators
        import re
        parts = re.split(r'\s+vs\.?\s+|\s+v\.?\s+|\s*-\s*|\s+against\s+', raw_input, flags=re.IGNORECASE)
        if len(parts) == 2:
            match_page, player_a, player_b = await search_and_open_match(parts[0].strip(), parts[1].strip())
        if not match_page:
            player_a = parts[0].strip() if len(parts) >= 1 else raw_input
            player_b = parts[1].strip() if len(parts) >= 2 else ""

    # Step 3: Get gender, surface, rankings from match page
    gender = "atp"
    surface = None
    rank_a, rank_b = None, None
    if match_page:
        gender = await read_match_gender(match_page)
        surface = await read_match_surface(match_page)
        rank_a, rank_b = await read_player_rankings(match_page)
        logger.info(f"Match found: {player_a} vs {player_b}, gender={gender}, surface={surface}, ranks={rank_a} vs {rank_b}")

    # Step 3: Get serve components from Tennis Abstract (adjusted for surface + opponent rank)
    from app.scraper.tennis_abstract import scrape_player_serve_stats
    serve_a = await scrape_player_serve_stats(player_a, gender, surface, opponent_rank=rank_b)
    serve_b = await scrape_player_serve_stats(player_b, gender, surface, opponent_rank=rank_a)

    p_a_prior = serve_a["p_serve"]
    p_b_prior = serve_b["p_serve"]

    match_found = match_page is not None
    current_score = {"sets": [0, 0], "games": [0, 0], "points": [0, 0], "serving": "a"}
    match_url = ""
    serve_a_updated = serve_a.copy()
    serve_b_updated = serve_b.copy()

    if match_page:
        match_url = match_page.url
        score_data = await read_match_score(match_page)
        if score_data:
            current_score = {
                "sets": score_data["sets"],
                "games": score_data["games"],
                "points": score_data["points"],
                "serving": score_data["serving"],
            }

        # Update p values using multi-scale weighting (far/mid/near)
        stats = await read_match_stats(match_page)
        if stats:
            serve_a_updated = multi_scale_p(serve_a, stats, [], "a")
            serve_b_updated = multi_scale_p(serve_b, stats, [], "b")

    total_points = 0
    if match_page and stats:
        total_points = stats.get("a_serve_total", 0) + stats.get("b_serve_total", 0)

    return {
        "player_a": player_a,
        "player_b": player_b,
        "gender": gender,
        "surface": surface,
        "p_a_prior": p_a_prior,
        "p_b_prior": p_b_prior,
        "serve_a_prior": serve_a,
        "serve_a_updated": serve_a_updated,
        "serve_b_prior": serve_b,
        "serve_b_updated": serve_b_updated,
        "match_found": match_found,
        "match_url": match_url,
        "current_score": current_score,
        "total_points": total_points,
        "match_stats": stats,
        "p_a_updated": serve_a_updated.get("p_serve", p_a_prior),
        "p_b_updated": serve_b_updated.get("p_serve", p_b_prior),
    }


@router.post("/api/match-update")
async def match_update(req: dict):
    """Re-read FlashScore DOM, update p values with near/mid/far weighting."""
    match_url = req.get("match_url", "")
    serve_a_prior = req.get("serve_a_prior", {})
    serve_b_prior = req.get("serve_b_prior", {})
    stats_history = req.get("stats_history", [])
    num_simulations = req.get("num_simulations", 100_000)

    from app.scraper.browser import get_browser
    from app.scraper.flashscore import read_match_score, read_match_stats

    browser = await get_browser()
    pages = browser.contexts[0].pages if browser.contexts else []
    match_page = None
    for page in pages:
        if match_url in page.url:
            match_page = page
            break

    if not match_page:
        return {"error": "Match page not found. Please look up the match again."}

    score_data = await read_match_score(match_page)
    if not score_data:
        return {"error": "Could not read match score"}

    score = {
        "sets": score_data["sets"],
        "games": score_data["games"],
        "points": score_data["points"],
        "serving": score_data["serving"],
    }

    stats = await read_match_stats(match_page)

    # Multi-scale p: far (prior) + mid (match total) + near (sliding window)
    serve_a_updated = multi_scale_p(serve_a_prior, stats, stats_history, "a")
    serve_b_updated = multi_scale_p(serve_b_prior, stats, stats_history, "b")

    p_a = serve_a_updated.get("p_serve", serve_a_prior.get("p_serve", 0.64))
    p_b = serve_b_updated.get("p_serve", serve_b_prior.get("p_serve", 0.64))

    logger.info(
        f"MATCH-UPDATE: p_a={p_a:.4f} (far={serve_a_updated.get('p_far')}, mid={serve_a_updated.get('p_mid')}, near={serve_a_updated.get('p_near')}) "
        f"p_b={p_b:.4f} (far={serve_b_updated.get('p_far')}, mid={serve_b_updated.get('p_mid')}, near={serve_b_updated.get('p_near')})"
    )

    state = score_to_match_state(ScoreInput(**score))
    table = build_win_prob_table(p_a, p_b)
    sim_result = simulate_time_slices(state, p_a, p_b, table, num_simulations)

    total_points = 0
    if stats:
        total_points = stats.get("a_serve_total", 0) + stats.get("b_serve_total", 0)

    return {
        "current_score": score,
        "total_points": total_points,
        "p_a_updated": round(p_a, 4),
        "p_b_updated": round(p_b, 4),
        "serve_a_updated": serve_a_updated,
        "serve_b_updated": serve_b_updated,
        "match_stats": stats,
        **sim_result,
    }


class RescrapeRequest(BaseModel):
    url: str
    player: str  # "a" or "b"
    surface: str | None = None
    opponent_rank: int | None = None


@router.post("/api/rescrape-player")
async def rescrape_player(req: RescrapeRequest):
    """Scrape serve stats from a user-provided Tennis Abstract URL."""
    from app.scraper.tennis_abstract import scrape_from_url
    result = await scrape_from_url(req.url, req.surface, req.opponent_rank)
    if not result:
        return {"error": f"Could not extract serve stats from {req.url}"}
    return {"player": req.player, "serve_stats": result}
