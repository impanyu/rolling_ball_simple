import logging
import re
from playwright.async_api import Page
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)


def parse_pbp_elements(raw_elements: list[dict]) -> dict | None:
    if not raw_elements:
        return None

    score_elements = [e for e in raw_elements if "scoreBox" in e.get("parent_class", "")]
    lost_serve = [e for e in raw_elements if "lostServe" in e.get("parent_class", "")]

    if not score_elements:
        return None

    scores = []
    for e in score_elements:
        text = e["text"].strip()
        if text.isdigit():
            scores.append(int(text))

    if len(scores) < 2:
        return None

    games_a = scores[-2] if len(scores) >= 2 else 0
    games_b = scores[-1] if len(scores) >= 2 else 0

    home_breaks = sum(1 for e in lost_serve if "home" in e.get("parent_class", ""))
    away_breaks = sum(1 for e in lost_serve if "away" in e.get("parent_class", ""))

    sets_a = 0
    sets_b = 0
    prev_a, prev_b = 0, 0
    for i in range(0, len(scores) - 1, 2):
        a, b = scores[i], scores[i + 1]
        if a < prev_a or b < prev_b:
            if prev_a > prev_b:
                sets_a += 1
            else:
                sets_b += 1
        prev_a, prev_b = a, b

    return {
        "sets": [sets_a, sets_b],
        "games": [games_a, games_b],
        "points": [0, 0],
        "serving": "a",
        "home_breaks": home_breaks,
        "away_breaks": away_breaks,
    }


async def read_flashscore_pbp(page: Page) -> list[dict]:
    elements = await page.query_selector_all('[class*="pointByPoint"], [class*="matchHistoryRow__lostServe"]')
    raw = []
    for el in elements:
        parent_info = await el.evaluate("el => el.parentElement ? el.parentElement.className : ''")
        text = (await el.text_content() or "").strip()
        winning = await el.get_attribute("data-winning")
        raw.append({
            "parent_class": parent_info,
            "text": text,
            "winning": winning == "true",
        })
    return raw


async def search_and_open_match(player_a: str, player_b: str) -> Page | None:
    """Search FlashScore tennis page for a match between two players.
    Matches by checking player last names in the match URL hrefs.
    """
    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto("https://www.flashscoreusa.com/tennis/", timeout=15000)
        await page.wait_for_timeout(4000)

        a_last = player_a.split()[-1].lower()
        b_last = player_b.split()[-1].lower()

        links = await page.query_selector_all('a[href*="/game/tennis/"]')
        for link in links:
            href = (await link.get_attribute("href") or "").lower()
            if a_last in href and b_last in href:
                match_url = await link.get_attribute("href") or ""
                if not match_url.startswith("http"):
                    match_url = f"https://www.flashscoreusa.com{match_url}"
                pbp_url = match_url.rstrip("/") + "/summary/point-by-point/set-1/"
                await page.goto(pbp_url, timeout=15000)
                await page.wait_for_timeout(5000)
                logger.info(f"Found match: {match_url}")
                return page

        logger.warning(f"No match found for {player_a} vs {player_b}")
        await page.close()
        return None
    except Exception as e:
        logger.error(f"FlashScore search failed: {e}")
        await page.close()
        return None
