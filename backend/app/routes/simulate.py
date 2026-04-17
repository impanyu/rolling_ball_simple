# backend/app/routes/simulate.py
import logging
import json
from pydantic import BaseModel
from fastapi import APIRouter

from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_time_slices, win_prob_at_state
from app.tennis.bayesian import update_serve_components

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
    result = simulate_time_slices(
        state, req.p_a, req.p_b, table, req.num_simulations
    )
    return result


@router.post("/api/lookup-match")
async def lookup_match(req: LookupRequest):
    import app.config as _config_module
    settings = _config_module.settings

    # Step 1: Parse player names with GPT-4o-mini
    from openai import AsyncOpenAI
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        completion = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "Extract two tennis player names from the input. "
                    "Return JSON with exactly these fields: "
                    '{"player_a": "First Last", "player_b": "First Last", "gender": "atp" or "wta"}. '
                    "Infer gender from the player names. Return only JSON, no other text."
                )},
                {"role": "user", "content": req.player_input},
            ],
            temperature=0,
        )
        parsed = json.loads(completion.choices[0].message.content)
        player_a = parsed["player_a"]
        player_b = parsed["player_b"]
        gender = parsed.get("gender", "atp")
    except Exception as e:
        logger.error(f"Failed to parse player names: {e}")
        return {"error": f"Could not parse player names: {e}"}

    # Step 2: Get serve components from Tennis Abstract
    from app.scraper.tennis_abstract import scrape_player_serve_stats
    serve_a = await scrape_player_serve_stats(player_a, gender)
    serve_b = await scrape_player_serve_stats(player_b, gender)

    p_a_prior = serve_a["p_serve"]
    p_b_prior = serve_b["p_serve"]

    # Step 3: Search FlashScore for live match
    from app.scraper.flashscore import search_and_open_match, read_match_score, read_match_stats
    match_page = await search_and_open_match(player_a, player_b)

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

        # Update serve components from live match stats (1st/2nd separately)
        stats = await read_match_stats(match_page)
        if stats:
            serve_a_updated = _update_p_from_stats(serve_a, stats, "a")
            serve_b_updated = _update_p_from_stats(serve_b, stats, "b")

    return {
        "player_a": player_a,
        "player_b": player_b,
        "gender": gender,
        "p_a_prior": p_a_prior,
        "p_b_prior": p_b_prior,
        "serve_a_prior": serve_a,
        "serve_a_updated": serve_a_updated,
        "serve_b_prior": serve_b,
        "serve_b_updated": serve_b_updated,
        "match_found": match_found,
        "match_url": match_url,
        "current_score": current_score,
        "p_a_updated": serve_a_updated["p_serve"],
        "p_b_updated": serve_b_updated["p_serve"],
    }


@router.get("/api/match-update")
async def match_update(
    match_url: str,
    a_first_in: float, a_first_won: float, a_second_won: float,
    b_first_in: float, b_first_won: float, b_second_won: float,
    num_simulations: int = 100_000,
):
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

    serve_a_prior = {"first_in": a_first_in, "first_won": a_first_won, "second_won": a_second_won}
    serve_b_prior = {"first_in": b_first_in, "first_won": b_first_won, "second_won": b_second_won}
    serve_a_updated = serve_a_prior.copy()
    serve_b_updated = serve_b_prior.copy()

    stats = await read_match_stats(match_page)
    if stats:
        serve_a_updated = _update_p_from_stats(serve_a_prior, stats, "a")
        serve_b_updated = _update_p_from_stats(serve_b_prior, stats, "b")

    p_a = serve_a_updated.get("p_serve", a_first_in * a_first_won + (1 - a_first_in) * a_second_won)
    p_b = serve_b_updated.get("p_serve", b_first_in * b_first_won + (1 - b_first_in) * b_second_won)

    state = score_to_match_state(ScoreInput(**score))
    table = build_win_prob_table(p_a, p_b)
    sim_result = simulate_time_slices(state, p_a, p_b, table, num_simulations)

    return {
        "current_score": score,
        "p_a_updated": round(p_a, 4),
        "p_b_updated": round(p_b, 4),
        "serve_a_updated": serve_a_updated,
        "serve_b_updated": serve_b_updated,
        **sim_result,
    }
