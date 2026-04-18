import logging
import re
import datetime
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)

DEFAULTS_ATP = {"first_in": 0.61, "first_won": 0.73, "second_won": 0.52}
DEFAULTS_WTA = {"first_in": 0.60, "first_won": 0.66, "second_won": 0.47}

SURFACE_LABELS = {"hard": "Hard", "clay": "Clay", "grass": "Grass"}


def _parse_stat_block(text: str, label: str) -> dict | None:
    pattern = (
        re.escape(label)
        + r'\s+\d+-\d+\s*\(\d+%\).*?'
        + r'(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%'
    )
    match = re.search(pattern, text)
    if not match:
        return None

    ace_pct, first_in, first_won, second_won = (float(x) for x in match.groups())
    fi = first_in / 100
    fw = first_won / 100
    sw = second_won / 100
    p_serve = fi * fw + (1 - fi) * sw

    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(p_serve, 4),
    }


def parse_serve_stats_from_text(
    text: str, surface: str | None = None, opponent_rank: int | None = None
) -> dict | None:
    current_year = str(datetime.date.today().year)

    base = _parse_stat_block(text, current_year)
    if base:
        logger.info(f"Using {current_year} season stats")
    else:
        if surface and surface.lower() in SURFACE_LABELS:
            label = SURFACE_LABELS[surface.lower()]
            base = _parse_stat_block(text, label)
            if base:
                logger.info(f"Using {label} surface stats")
            else:
                logger.warning(f"Could not find {label} surface stats")

        if not base:
            base = _parse_stat_block(text, "Last 52")

    if not base:
        return None

    if opponent_rank and opponent_rank <= 50:
        top10_stats = _parse_stat_block(text, "vs Top 10")
        if top10_stats:
            if opponent_rank <= 10:
                weight = 1.0
            else:
                weight = (50 - opponent_rank) / 40.0

            for key in ["first_in", "first_won", "second_won"]:
                base[key] = round(base[key] * (1 - weight) + top10_stats[key] * weight, 4)
            base["p_serve"] = round(
                base["first_in"] * base["first_won"] + (1 - base["first_in"]) * base["second_won"], 4
            )
            logger.info(f"Adjusted for opponent rank {opponent_rank} (top10 weight={weight:.2f})")

    return base


def _search_player_url_name(player_name: str, gender: str = "wta") -> str | None:
    """Use DuckDuckGo to find the correct Tennis Abstract URL name for a player."""
    try:
        from ddgs import DDGS
        prefix = "w" if gender == "wta" else ""

        for query in [
            f"site:tennisabstract.com/cgi-bin/{prefix}player {player_name}",
            f"tennisabstract.com {player_name} serve stats",
        ]:
            results = list(DDGS().text(query, max_results=5))
            for r in results:
                href = r.get("href", "")
                m = re.search(r'tennisabstract\.com/cgi-bin/\w*player[^?]*\?p=(\w+)', href)
                if m:
                    url_name = m.group(1)
                    logger.info(f"DDG found Tennis Abstract name for '{player_name}': {url_name}")
                    return url_name
    except Exception as e:
        logger.warning(f"DDG search failed for {player_name}: {e}")
    return None


async def scrape_player_serve_stats(
    player_name: str, gender: str = "wta", surface: str | None = None,
    opponent_rank: int | None = None,
) -> dict:
    """Scrape player's serve components from Tennis Abstract.
    Uses DuckDuckGo to find the correct player page, then scrapes it.
    """
    prefix = "w" if gender == "wta" else ""
    defaults = DEFAULTS_WTA if gender == "wta" else DEFAULTS_ATP
    current_year = str(datetime.date.today().year)

    # Step 1: Find the correct URL name via DuckDuckGo
    url_name = _search_player_url_name(player_name, gender)

    # Fallback: try simple concatenation
    if not url_name:
        url_name = player_name.replace(" ", "")
        # Also try with alt gender
        alt_name = _search_player_url_name(player_name, "atp" if gender == "wta" else "wta")
        if alt_name:
            url_name = alt_name
            prefix = "" if gender == "wta" else "w"

    # Step 2: Scrape the page
    url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={url_name}&f=A{current_year}qq"

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)
        text = await page.text_content("body") or ""
        await page.close()

        result = parse_serve_stats_from_text(text, surface, opponent_rank)
        if result:
            surface_label = surface or "overall"
            logger.info(f"Got serve stats for {player_name} as '{url_name}' ({surface_label}, vs rank {opponent_rank}): p={result['p_serve']}")
            return result

    except Exception as e:
        logger.error(f"Failed to scrape {player_name}: {e}")

    logger.warning(f"Could not parse stats for {player_name} (url_name={url_name}), using defaults")
    p = defaults["first_in"] * defaults["first_won"] + (1 - defaults["first_in"]) * defaults["second_won"]
    return {**defaults, "p_serve": round(p, 4), "is_default": True}


async def scrape_from_url(
    url: str, surface: str | None = None, opponent_rank: int | None = None
) -> dict | None:
    """Scrape serve stats from a user-provided Tennis Abstract URL."""
    if "player.cgi" in url and "player-classic.cgi" not in url:
        url = url.replace("player.cgi", "player-classic.cgi")
    if "f=" not in url:
        url += "&f=ACareerqq" if "?" in url else "?f=ACareerqq"

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)
        text = await page.text_content("body") or ""
        await page.close()

        result = parse_serve_stats_from_text(text, surface, opponent_rank)
        if result:
            result["is_default"] = False
            logger.info(f"Got serve stats from user URL {url}: p={result['p_serve']}")
            return result
    except Exception as e:
        logger.error(f"Failed to scrape user URL {url}: {e}")
    return None


async def scrape_player_p(player_name: str, gender: str = "wta") -> float:
    stats = await scrape_player_serve_stats(player_name, gender)
    return stats["p_serve"]
