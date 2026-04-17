import logging
import re
from playwright.async_api import Page
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)

DEFAULT_P_ATP = 0.64
DEFAULT_P_WTA = 0.56


def parse_serve_stats_from_text(text: str) -> dict | None:
    match = re.search(
        r'Last 52.*?(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%.*?(\d+\.\d+)%',
        text,
    )
    if not match:
        return None

    ace_pct, first_in, first_won, second_won = (float(x) for x in match.groups())
    fi = first_in / 100
    fw = first_won / 100
    sw = second_won / 100
    p_serve = fi * fw + (1 - fi) * sw

    return {
        "first_in": first_in,
        "first_won": first_won,
        "second_won": second_won,
        "p_serve": round(p_serve, 4),
    }


async def scrape_player_p(player_name: str, gender: str = "wta") -> float:
    prefix = "w" if gender == "wta" else ""
    url_name = player_name.replace(" ", "")
    url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={url_name}&f=ACareerqq"
    default_p = DEFAULT_P_WTA if gender == "wta" else DEFAULT_P_ATP

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)
        text = await page.text_content("body") or ""
        await page.close()

        result = parse_serve_stats_from_text(text)
        if result:
            logger.info(f"Got p_serve for {player_name}: {result['p_serve']}")
            return result["p_serve"]

        logger.warning(f"Could not parse stats for {player_name}, using default {default_p}")
        return default_p
    except Exception as e:
        logger.error(f"Failed to scrape {player_name}: {e}")
        return default_p
