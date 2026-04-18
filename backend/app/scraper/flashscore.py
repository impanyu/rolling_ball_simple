import logging
import re
from playwright.async_api import Page
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)


async def read_player_rankings(page: Page) -> tuple[int | None, int | None]:
    """Extract player rankings from FlashScore match page.
    Returns (rank_a, rank_b) or None for each if not found.
    """
    try:
        rank_els = await page.query_selector_all('[class*="participantRank"]')
        ranks = []
        for el in rank_els:
            text = (await el.text_content() or "").strip()
            match = re.search(r'(\d+)', text)
            if match:
                ranks.append(int(match.group(1)))
        rank_a = ranks[0] if len(ranks) >= 1 else None
        rank_b = ranks[1] if len(ranks) >= 2 else None
        return rank_a, rank_b
    except Exception:
        return None, None


async def read_match_surface(page: Page) -> str | None:
    """Extract surface type from FlashScore match page (e.g. 'clay', 'hard', 'grass')."""
    try:
        body = await page.text_content("body") or ""
        match = re.search(r'(?:clay|hard|grass)', body.lower())
        if match:
            return match.group(0)
    except Exception:
        pass
    return None


async def read_match_score(page: Page) -> dict | None:
    """Extract current match score from the FlashScore match page header.
    Works on the main match page (not PBP subpage).
    """
    try:
        # detailScore__matchInfo contains: "1-1Set 3 - Tiebreak6 : 6 ( 1 : 0 )"
        # detailScore__wrapper contains: "1-1" (sets)
        # detailScore__status contains: "Set 3 - Tiebreak6 : 6 ( 1 : 0 )"
        # detailScore__detailScoreServe contains: "6 : 6" (games in current set)

        match_info_el = await page.query_selector('[class*="detailScore__matchInfo"]')
        if not match_info_el:
            return None

        info_text = (await match_info_el.text_content() or "").strip()
        logger.info(f"Match info text: {info_text}")

        # Extract sets score: "1-1" at the start
        sets_match = re.match(r'(\d+)\s*[-–]\s*(\d+)', info_text)
        if not sets_match:
            return None
        sets_a, sets_b = int(sets_match.group(1)), int(sets_match.group(2))

        # Extract current set games: "6 : 6" or "3 : 2"
        games_a, games_b = 0, 0
        games_el = await page.query_selector('[class*="detailScore__detailScoreServe"]')
        if games_el:
            games_text = (await games_el.text_content() or "").strip()
            games_match = re.match(r'(\d+)\s*:\s*(\d+)', games_text)
            if games_match:
                games_a, games_b = int(games_match.group(1)), int(games_match.group(2))

        # Check for tiebreak
        is_tiebreak = "tiebreak" in info_text.lower()

        # Extract point score from "( X : Y )" — works for both regular games and tiebreaks
        points_a, points_b = 0, 0
        pts_match = re.search(r'\(\s*(\d+)\s*:\s*(\d+)\s*\)', info_text)
        if pts_match:
            raw_a, raw_b = int(pts_match.group(1)), int(pts_match.group(2))
            if is_tiebreak:
                points_a, points_b = raw_a, raw_b
            else:
                # Map tennis game scores (0,15,30,40) to engine encoding (0,1,2,3)
                score_map = {0: 0, 15: 1, 30: 2, 40: 3}
                points_a = score_map.get(raw_a, 3)
                points_b = score_map.get(raw_b, 3)
                # Handle advantage: if one has 40 and other has AD (shown as 40:A or similar)
                # In FlashScore both show as numbers, deuce is 40:40 → 3:3

        # Determine who is serving
        serving = "a"

        return {
            "sets": [sets_a, sets_b],
            "games": [games_a, games_b],
            "points": [points_a, points_b],
            "serving": serving,
            "is_tiebreak": is_tiebreak,
        }

    except Exception as e:
        logger.error(f"Failed to read match score: {e}")
        return None


async def read_match_stats(page: Page) -> dict | None:
    """Extract serve statistics from the match page for Bayesian p-value update."""
    try:
        body = await page.text_content("body") or ""

        # Look for "1st serve points won" stats
        # Pattern: "73% (56/77)" or similar
        stats = {}

        # Find serve points won for home (player A) and away (player B)
        # FlashScore shows stats like: "73% (56/77)  1st serve points won  65% (42/65)"
        srv_match = re.search(
            r'(\d+)%\s*\((\d+)/(\d+)\)\s*1st serve points won\s*(\d+)%\s*\((\d+)/(\d+)\)',
            body
        )
        if srv_match:
            a_1st_pct, a_1st_won, a_1st_total = srv_match.group(1), int(srv_match.group(2)), int(srv_match.group(3))
            b_1st_pct, b_1st_won, b_1st_total = srv_match.group(4), int(srv_match.group(5)), int(srv_match.group(6))
            stats["a_1st_serve_won"] = a_1st_won
            stats["a_1st_serve_total"] = a_1st_total
            stats["b_1st_serve_won"] = b_1st_won
            stats["b_1st_serve_total"] = b_1st_total

        srv2_match = re.search(
            r'(\d+)%\s*\((\d+)/(\d+)\)\s*2nd serve points won\s*(\d+)%\s*\((\d+)/(\d+)\)',
            body
        )
        if srv2_match:
            stats["a_2nd_serve_won"] = int(srv2_match.group(2))
            stats["a_2nd_serve_total"] = int(srv2_match.group(3))
            stats["b_2nd_serve_won"] = int(srv2_match.group(5))
            stats["b_2nd_serve_total"] = int(srv2_match.group(6))

        if stats:
            # Compute total serve points won
            a_won = stats.get("a_1st_serve_won", 0) + stats.get("a_2nd_serve_won", 0)
            a_total = stats.get("a_1st_serve_total", 0) + stats.get("a_2nd_serve_total", 0)
            b_won = stats.get("b_1st_serve_won", 0) + stats.get("b_2nd_serve_won", 0)
            b_total = stats.get("b_1st_serve_total", 0) + stats.get("b_2nd_serve_total", 0)
            stats["a_serve_won"] = a_won
            stats["a_serve_total"] = a_total
            stats["b_serve_won"] = b_won
            stats["b_serve_total"] = b_total
            return stats

        return None

    except Exception as e:
        logger.error(f"Failed to read match stats: {e}")
        return None


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


def extract_player_names_from_url(url: str) -> tuple[str, str] | None:
    """Extract player full names from FlashScore match URL.
    URL pattern: /game/tennis/lastname-firstname-ID/lastname-firstname-ID/
    Returns (player_a_name, player_b_name) or None.
    """
    match = re.search(
        r'/game/tennis/([\w-]+?)-(\w{8})/([\w-]+?)-(\w{8})/',
        url,
    )
    if not match:
        return None
    slug_a, _, slug_b, _ = match.groups()
    # URL format: lastname-firstname or lastname-first-middle-etc
    # First word is last name, rest are first/middle names
    # Convert 'prado-carlos-juan-angelo' to 'Carlos Juan Angelo Prado'
    name_a = _slug_to_name(slug_a)
    name_b = _slug_to_name(slug_b)
    return name_a, name_b


def _slug_to_name(slug: str) -> str:
    parts = slug.split('-')
    if len(parts) <= 1:
        return parts[0].capitalize() if parts else ""
    last_name = parts[0].capitalize()
    first_names = ' '.join(w.capitalize() for w in parts[1:])
    return f"{first_names} {last_name}"


async def _read_page_player_names(page: Page, url: str) -> tuple[str, str]:
    """Read actual HOME/AWAY player names from the FlashScore match page.
    HOME (top) = player_a, AWAY (bottom) = player_b.
    Falls back to URL-based extraction if page elements not found.
    """
    name_els = await page.query_selector_all('[class*="participant__participantName"]')
    page_names = []
    for el in name_els:
        text = (await el.text_content() or "").strip()
        if text and text not in page_names:
            page_names.append(text)

    # URL names as fallback
    url_names = extract_player_names_from_url(url)

    if len(page_names) >= 2:
        # Page shows abbreviated names like "Soto M." — use URL for full names
        # but determine which URL player is HOME and which is AWAY
        if url_names:
            url_a_last = url_names[0].split()[-1].lower()
            # Check if URL's first player matches page's HOME (first) player
            home_last = page_names[0].split()[0].lower().rstrip(".")
            if url_a_last == home_last:
                return url_names[0], url_names[1]
            else:
                # URL order is reversed from page order — swap
                return url_names[1], url_names[0]

    # Fallback to URL order
    if url_names:
        return url_names[0], url_names[1]
    return "Player A", "Player B"


def _ddg_find_player_slugs(player_a: str, player_b: str) -> list[str]:
    """Use DuckDuckGo to find FlashScore player slugs (e.g. 'bai-zhuoxuan').
    Returns a list of slugs found for either player.
    """
    try:
        from ddgs import DDGS
        query = f"site:flashscoreusa.com {player_a} {player_b} tennis"
        results = list(DDGS().text(query, max_results=5))
        slugs = []
        for r in results:
            href = r.get("href", "")
            # Extract player slugs from various FlashScore URL patterns
            for pattern in [
                r'/game/tennis/([\w-]+?)-\w{8}/',
                r'/player/([\w-]+?)/\w{8}/',
                r'/h2h/tennis/([\w-]+?)-\w{8}/',
            ]:
                for m in re.finditer(pattern, href):
                    slug = m.group(1)
                    if slug not in slugs:
                        slugs.append(slug)
        logger.info(f"DDG found FlashScore slugs: {slugs}")
        return slugs
    except Exception as e:
        logger.warning(f"DDG FlashScore search failed: {e}")
        return []


def _best_match_parts(name: str) -> list[str]:
    """Extract usable name parts (>= 3 chars) for URL matching."""
    parts = [p.lower().rstrip(".") for p in name.split() if len(p.rstrip(".")) >= 3]
    if not parts:
        parts = [p.lower().rstrip(".") for p in name.split() if len(p.rstrip(".")) >= 2]
    return parts


async def search_and_open_match(player_a: str, player_b: str) -> tuple[Page | None, str, str]:
    """Search FlashScore tennis page for a match between two players.
    Uses DDG to find player slugs, then matches on the live tennis page.
    Returns (page, home_player, away_player). HOME matches score's left number.
    """
    # Step 1: Get player slugs via DuckDuckGo for better matching
    ddg_slugs = _ddg_find_player_slugs(player_a, player_b)

    # Build match parts from LLM names + DDG slugs
    a_parts = _best_match_parts(player_a)
    b_parts = _best_match_parts(player_b)

    # Add DDG slug parts (split on '-' to get name components)
    for slug in ddg_slugs:
        for part in slug.split("-"):
            if len(part) >= 3 and part not in a_parts and part not in b_parts:
                # Assign to whichever player it matches best
                if any(p in slug for p in a_parts):
                    if part not in a_parts:
                        a_parts.append(part)
                elif any(p in slug for p in b_parts):
                    if part not in b_parts:
                        b_parts.append(part)

    logger.info(f"Matching parts: A={a_parts}, B={b_parts}")

    browser = await get_browser()
    page = await browser.new_page()
    try:
        await page.goto("https://www.flashscoreusa.com/tennis/", timeout=15000)
        await page.wait_for_timeout(4000)

        all_parts = a_parts + b_parts
        links = await page.query_selector_all('a[href*="/game/tennis/"]')

        # First pass: try matching both players
        best_link = None
        best_score = 0
        for link in links:
            href = (await link.get_attribute("href") or "").lower()
            a_match = sum(1 for p in a_parts if p in href)
            b_match = sum(1 for p in b_parts if p in href)
            score = a_match + b_match
            if a_match > 0 and b_match > 0 and score > best_score:
                best_score = score
                best_link = link

        # Fallback: if no dual match, try matching any single part with >= 4 chars
        if not best_link:
            long_parts = [p for p in all_parts if len(p) >= 4]
            for link in links:
                href = (await link.get_attribute("href") or "").lower()
                matches = sum(1 for p in long_parts if p in href)
                if matches > 0 and matches > best_score:
                    best_score = matches
                    best_link = link

        if best_link:
            match_url = await best_link.get_attribute("href") or ""
            if not match_url.startswith("http"):
                match_url = f"https://www.flashscoreusa.com{match_url}"

            await page.goto(match_url, timeout=15000)
            await page.wait_for_timeout(5000)

            real_a, real_b = await _read_page_player_names(page, match_url)
            logger.info(f"Found match: {match_url} (HOME={real_a} vs AWAY={real_b})")
            return page, real_a, real_b

        logger.warning(f"No match found for {player_a} vs {player_b} (parts: A={a_parts}, B={b_parts})")
        await page.close()
        return None, player_a, player_b
    except Exception as e:
        logger.error(f"FlashScore search failed: {e}")
        await page.close()
        return None, player_a, player_b
