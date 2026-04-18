# backend/app/routes/simulate.py
import logging
import json
from pydantic import BaseModel
from fastapi import APIRouter

from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_time_slices, simulate_max_prob, win_prob_at_state
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
    first_server: str = "a"
    num_simulations: int = 100_000


class LookupRequest(BaseModel):
    player_input: str


def compute_current_server(
    sets_a: int, sets_b: int,
    games_a: int, games_b: int,
    first_server: str = "a",
    completed_set_games: list[tuple[int, int]] | None = None,
) -> bool:
    """Compute who is serving based on total games played and who served first.
    Returns True if A is serving.
    """
    # Count total games across all sets
    total_games = games_a + games_b
    if completed_set_games:
        for ga, gb in completed_set_games:
            total_games += ga + gb

    # In regular play: first server serves games 0, 2, 4, ... (even total)
    # In tiebreak: the player who was receiving serves first in tiebreak
    is_tiebreak = games_a == 6 and games_b == 6

    if is_tiebreak:
        # Tiebreak first server = the player who would have served next
        a_serves_regular = (total_games % 2 == 0) == (first_server == "a")
        return a_serves_regular
    else:
        a_serves = (total_games % 2 == 0) == (first_server == "a")
        return a_serves


def score_to_match_state(score: ScoreInput, first_server: str = "a") -> MatchState:
    is_tiebreak = score.games[0] == 6 and score.games[1] == 6
    is_a_serving = compute_current_server(
        score.sets[0], score.sets[1],
        score.games[0], score.games[1],
        first_server,
    )
    return MatchState(
        sets_a=score.sets[0],
        sets_b=score.sets[1],
        games_a=score.games[0],
        games_b=score.games[1],
        points_a=score.points[0],
        points_b=score.points[1],
        is_a_serving=is_a_serving,
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
    state = score_to_match_state(req.score, req.first_server)
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


@router.post("/api/simulate-max")
async def simulate_max(req: SimulateRequest):
    """Simulate paths up to 100 points, return max P(win) histogram."""
    state = score_to_match_state(req.score, req.first_server)
    table = build_win_prob_table(req.p_a, req.p_b)
    result = simulate_max_prob(state, req.p_a, req.p_b, table, req.num_simulations)
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
        logger.info(f"LOOKUP stats result: {stats}")
        if stats:
            serve_a_updated = multi_scale_p(serve_a, stats, [], "a")
            serve_b_updated = multi_scale_p(serve_b, stats, [], "b")
            logger.info(f"LOOKUP prior A:   fi={serve_a.get('first_in')}, fw={serve_a.get('first_won')}, sw={serve_a.get('second_won')}, p={serve_a.get('p_serve')}")
            logger.info(f"LOOKUP updated A: fi={serve_a_updated.get('first_in')}, fw={serve_a_updated.get('first_won')}, sw={serve_a_updated.get('second_won')}, p={serve_a_updated.get('p_serve')}")
        else:
            logger.warning("LOOKUP: no match stats available, using priors as-is")

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
    """Re-read FlashScore DOM. Only re-compute if score changed."""
    try:
        return await _do_match_update(req)
    except Exception as e:
        logger.error(f"match-update error: {e}")
        return {"error": str(e), "changed": False}


async def _do_match_update(req: dict):
    logger.info(">>> MATCH-UPDATE called")
    match_url = req.get("match_url", "")
    serve_a_prior = req.get("serve_a_prior", {})
    serve_b_prior = req.get("serve_b_prior", {})
    stats_history = req.get("stats_history", [])
    first_server = req.get("first_server", "a")
    prev_score = req.get("prev_score")
    num_simulations = req.get("num_simulations", 100_000)

    from app.scraper.browser import get_browser
    from app.scraper.flashscore import read_match_score, read_match_stats

    browser = await get_browser()
    # Open a fresh tab, read data, close tab (no reload/goto on existing page)
    match_page = None
    try:
        match_page = await browser.new_page()
        await match_page.goto(match_url, timeout=10000, wait_until="domcontentloaded")
        await match_page.wait_for_timeout(1500)
    except Exception as e:
        logger.warning(f"Navigation failed: {e}")
        if match_page:
            try: await match_page.close()
            except: pass
        return {"error": "Could not load match page.", "changed": False}

    try:
        score_data = await read_match_score(match_page)
        stats = await read_match_stats(match_page)
    finally:
        try: await match_page.close()
        except: pass

    if not score_data:
        return {"error": "Could not read match score"}

    score = {
        "sets": score_data["sets"],
        "games": score_data["games"],
        "points": score_data["points"],
        "serving": score_data["serving"],
    }

    logger.info(f">>> Score read: {score}, prev: {prev_score}")
    if prev_score and score == prev_score:
        return {"changed": False, "current_score": score}

    # Multi-scale p: far (prior) + mid (match total) + near (sliding window)
    serve_a_updated = multi_scale_p(serve_a_prior, stats, stats_history, "a")
    serve_b_updated = multi_scale_p(serve_b_prior, stats, stats_history, "b")

    p_a = serve_a_updated.get("p_serve", serve_a_prior.get("p_serve", 0.64))
    p_b = serve_b_updated.get("p_serve", serve_b_prior.get("p_serve", 0.64))

    logger.info(
        f"MATCH-UPDATE: p_a={p_a:.4f} (far={serve_a_updated.get('p_far')}, window={serve_a_updated.get('window_size')}) "
        f"p_b={p_b:.4f} (far={serve_b_updated.get('p_far')}, window={serve_b_updated.get('window_size')})"
    )

    # Run simulation based on requested mode
    sim_mode = req.get("sim_mode", "timeslice")
    state = score_to_match_state(ScoreInput(**score), first_server)
    table = build_win_prob_table(p_a, p_b)

    if sim_mode == "maxprob":
        sim_result = simulate_max_prob(state, p_a, p_b, table, num_simulations)
    else:
        sim_result = simulate_time_slices(state, p_a, p_b, table, num_simulations)

    total_points = 0
    if stats:
        total_points = stats.get("a_serve_total", 0) + stats.get("b_serve_total", 0)

    return {
        "changed": True,
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
