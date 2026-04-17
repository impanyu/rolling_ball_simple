import logging
import re
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)

DEFAULTS_ATP = {"first_in": 0.61, "first_won": 0.73, "second_won": 0.52}
DEFAULTS_WTA = {"first_in": 0.60, "first_won": 0.66, "second_won": 0.47}

SURFACE_LABELS = {"hard": "Hard", "clay": "Clay", "grass": "Grass"}


def _parse_stat_block(text: str, label: str) -> dict | None:
    """Parse a stat block starting with `label` followed by percentage fields.
    Pattern: 'Label W-L (pct%)...Ace%...1stIn%...1stWon%...2ndWon%...'
    """
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


def parse_serve_stats_from_text(text: str, surface: str | None = None) -> dict | None:
    """Parse serve stats from Tennis Abstract page text.
    If surface is provided ('hard'/'clay'/'grass'), extract surface-specific stats.
    Otherwise extract 'Last 52' overall stats.
    """
    if surface and surface.lower() in SURFACE_LABELS:
        label = SURFACE_LABELS[surface.lower()]
        result = _parse_stat_block(text, label)
        if result:
            return result
        logger.warning(f"Could not find {label} surface stats, falling back to Last 52")

    return _parse_stat_block(text, "Last 52")


async def scrape_player_serve_stats(
    player_name: str, gender: str = "wta", surface: str | None = None
) -> dict:
    """Scrape player's serve components from Tennis Abstract.
    If surface is provided, returns surface-specific stats.
    Returns dict with first_in, first_won, second_won, p_serve (all as fractions 0-1).
    """
    prefix = "w" if gender == "wta" else ""
    url_name = player_name.replace(" ", "")
    url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={url_name}&f=ACareerqq"
    defaults = DEFAULTS_WTA if gender == "wta" else DEFAULTS_ATP

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)
        text = await page.text_content("body") or ""
        await page.close()

        result = parse_serve_stats_from_text(text, surface)
        if result:
            surface_label = surface or "overall"
            logger.info(f"Got serve stats for {player_name} ({surface_label}): fi={result['first_in']}, fw={result['first_won']}, sw={result['second_won']}, p={result['p_serve']}")
            return result

        logger.warning(f"Could not parse stats for {player_name}, using defaults")
    except Exception as e:
        logger.error(f"Failed to scrape {player_name}: {e}")

    p = defaults["first_in"] * defaults["first_won"] + (1 - defaults["first_in"]) * defaults["second_won"]
    return {**defaults, "p_serve": round(p, 4)}


async def scrape_player_p(player_name: str, gender: str = "wta") -> float:
    stats = await scrape_player_serve_stats(player_name, gender)
    return stats["p_serve"]
