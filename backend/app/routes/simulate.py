# backend/app/routes/simulate.py
import logging
import json
from pydantic import BaseModel
from fastapi import APIRouter

from app.tennis.engine import MatchState, build_win_prob_table
from app.tennis.simulator import simulate_max_prob_distribution, win_prob_at_state
from app.tennis.bayesian import bayesian_update_p

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


@router.post("/api/simulate")
async def simulate(req: SimulateRequest):
    state = score_to_match_state(req.score)
    table = build_win_prob_table(req.p_a, req.p_b)
    result = simulate_max_prob_distribution(
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

    # Step 2: Get p values from Tennis Abstract
    from app.scraper.tennis_abstract import scrape_player_p
    p_a = await scrape_player_p(player_a, gender)
    p_b = await scrape_player_p(player_b, gender)

    # Step 3: Search FlashScore for live match
    from app.scraper.flashscore import search_and_open_match, read_match_score, read_match_stats
    match_page = await search_and_open_match(player_a, player_b)

    match_found = match_page is not None
    current_score = {"sets": [0, 0], "games": [0, 0], "points": [0, 0], "serving": "a"}
    match_url = ""
    p_a_updated = p_a
    p_b_updated = p_b

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

        # Update p values from live match stats
        stats = await read_match_stats(match_page)
        if stats:
            a_won = stats.get("a_serve_won", 0)
            a_total = stats.get("a_serve_total", 0)
            b_won = stats.get("b_serve_won", 0)
            b_total = stats.get("b_serve_total", 0)
            if a_total > 0:
                p_a_updated = bayesian_update_p(p_a, a_won, a_total)
            if b_total > 0:
                p_b_updated = bayesian_update_p(p_b, b_won, b_total)

    return {
        "player_a": player_a,
        "player_b": player_b,
        "gender": gender,
        "p_a_prior": round(p_a, 4),
        "p_b_prior": round(p_b, 4),
        "match_found": match_found,
        "match_url": match_url,
        "current_score": current_score,
        "p_a_updated": round(p_a_updated, 4),
        "p_b_updated": round(p_b_updated, 4),
    }


@router.get("/api/match-update")
async def match_update(
    match_url: str,
    p_a_prior: float,
    p_b_prior: float,
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

    p_a_updated = p_a_prior
    p_b_updated = p_b_prior

    stats = await read_match_stats(match_page)
    if stats:
        a_won = stats.get("a_serve_won", 0)
        a_total = stats.get("a_serve_total", 0)
        b_won = stats.get("b_serve_won", 0)
        b_total = stats.get("b_serve_total", 0)
        if a_total > 0:
            p_a_updated = bayesian_update_p(p_a_prior, a_won, a_total)
        if b_total > 0:
            p_b_updated = bayesian_update_p(p_b_prior, b_won, b_total)

    state = score_to_match_state(ScoreInput(**score))
    table = build_win_prob_table(p_a_updated, p_b_updated)
    sim_result = simulate_max_prob_distribution(
        state, p_a_updated, p_b_updated, table, num_simulations
    )

    return {
        "current_score": score,
        "p_a_updated": round(p_a_updated, 4),
        "p_b_updated": round(p_b_updated, 4),
        **sim_result,
    }
