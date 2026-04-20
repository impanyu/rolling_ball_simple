import logging
import re
import datetime
import numpy as np
from app.scraper.browser import get_browser

logger = logging.getLogger(__name__)

DEFAULTS_ATP = {"first_in": 0.61, "first_won": 0.73, "second_won": 0.52}
DEFAULTS_WTA = {"first_in": 0.60, "first_won": 0.66, "second_won": 0.47}

MONTHS_BACK = 3
MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_date(date_str: str) -> datetime.date | None:
    """Parse Tennis Abstract date like '13‑Apr‑2026' or '5-Mar-2026'."""
    m = re.match(r'(\d{1,2})[‑-](\w{3})[‑-](\d{4})', date_str)
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTH_MAP.get(m.group(2)), int(m.group(3))
    if not mon:
        return None
    try:
        return datetime.date(year, mon, day)
    except ValueError:
        return None


def _parse_pct(s: str) -> float | None:
    """Parse '67.2%' to 0.672."""
    s = s.strip().rstrip('%')
    try:
        return float(s) / 100
    except ValueError:
        return None


async def _scrape_match_rows(page) -> list[dict]:
    """Extract per-match data from Tennis Abstract player page HTML table."""
    rows = await page.query_selector_all('tr')
    matches = []

    for row in rows:
        cells = await row.query_selector_all('td')
        if len(cells) != 17:
            continue

        texts = []
        for c in cells:
            texts.append((await c.text_content() or "").strip())

        date = _parse_date(texts[0])
        surface = texts[2] if texts[2] in ("Hard", "Clay", "Grass") else None
        if not date or not surface:
            continue

        try:
            opp_rank = int(texts[5])
        except (ValueError, IndexError):
            continue

        fi = _parse_pct(texts[12])
        fw = _parse_pct(texts[13])
        sw = _parse_pct(texts[14])

        if fi is None or fw is None or sw is None:
            continue

        matches.append({
            "date": date,
            "surface": surface.lower(),
            "opp_rank": opp_rank,
            "first_in": fi,
            "first_won": fw,
            "second_won": sw,
        })

    return matches


def _linear_regression_predict(x_vals: list[float], y_vals: list[float], x_target: float) -> float | None:
    """Simple linear regression: predict y at x_target."""
    if len(x_vals) < 3:
        return None
    x = np.array(x_vals, dtype=float)
    y = np.array(y_vals, dtype=float)
    # y = a*x + b
    n = len(x)
    sx = np.sum(x)
    sy = np.sum(y)
    sxx = np.sum(x * x)
    sxy = np.sum(x * y)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-10:
        return float(np.mean(y))
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    return float(a * x_target + b)


def compute_prior_from_matches(
    matches: list[dict],
    surface: str | None,
    opponent_rank: int | None,
    match_date: datetime.date | None = None,
) -> dict | None:
    """Compute prior serve components from per-match data using linear regression.

    1. Filter: same surface, last 3 months before match_date
    2. For each component, collect (opponent_rank, component_value) pairs
    3. Linear regression: component = f(opponent_rank)
    4. Predict at current opponent's rank
    """
    if match_date is None:
        match_date = datetime.date.today()

    # Try progressively wider windows until we have enough matches
    for months in [MONTHS_BACK, 6, 12]:
        cutoff = match_date - datetime.timedelta(days=months * 30)
        date_filtered = [m for m in matches if cutoff <= m["date"] < match_date]

        if surface:
            surface_filtered = [m for m in date_filtered if m["surface"] == surface.lower()]
            if len(surface_filtered) >= 3:
                filtered = surface_filtered
                logger.info(f"Using {len(filtered)} {surface} matches from last {months} months")
                break

        if len(date_filtered) >= 3:
            filtered = date_filtered
            if surface:
                logger.warning(f"Not enough {surface} matches, using all {len(filtered)} matches from last {months} months")
            else:
                logger.info(f"Using {len(filtered)} matches from last {months} months")
            break
    else:
        filtered = [m for m in matches if m["date"] < match_date]
        if not filtered:
            return None
        logger.warning(f"Using all {len(filtered)} career matches as fallback")

    opp_ranks = [m["opp_rank"] for m in filtered]
    if opponent_rank and opponent_rank > 0:
        target_rank = float(opponent_rank)
    else:
        target_rank = float(np.median(opp_ranks))
        logger.warning(f"No opponent rank provided, using median of data: {target_rank:.0f}")

    result = {}
    for component in ["first_in", "first_won", "second_won"]:
        values = [m[component] for m in filtered]

        if len(filtered) >= 3:
            predicted = _linear_regression_predict(
                [float(r) for r in opp_ranks], values, target_rank
            )
            if predicted is not None:
                predicted = max(0.1, min(0.95, predicted))
                result[component] = round(predicted, 4)
                continue

        # Not enough data for regression, use mean
        result[component] = round(float(np.mean(values)), 4)

    fi, fw, sw = result["first_in"], result["first_won"], result["second_won"]
    result["p_serve"] = round(fi * fw + (1 - fi) * sw, 4)
    result["matches_used"] = len(filtered)
    result["method"] = "regression" if len(filtered) >= 5 else "mean"

    logger.info(
        f"Prior from {len(filtered)} matches (target_rank={target_rank:.0f}): "
        f"fi={result['first_in']}, fw={result['first_won']}, sw={result['second_won']}, p={result['p_serve']} ({result['method']})"
    )

    return result


def _search_player_url_name(player_name: str, gender: str = "wta") -> str | None:
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
    """Scrape player's per-match data, compute prior via linear regression.

    1. Find player page on Tennis Abstract (via DDG)
    2. Parse all match rows (date, surface, opp_rank, 1stIn, 1stWon, 2ndWon)
    3. Filter: same surface + last 3 months
    4. Linear regression of each component vs opponent_rank
    5. Predict at current opponent's rank
    """
    prefix = "w" if gender == "wta" else ""
    defaults = DEFAULTS_WTA if gender == "wta" else DEFAULTS_ATP

    url_name = _search_player_url_name(player_name, gender)
    if not url_name:
        url_name = player_name.replace(" ", "")
        alt_name = _search_player_url_name(player_name, "atp" if gender == "wta" else "wta")
        if alt_name:
            url_name = alt_name
            prefix = "" if gender == "wta" else "w"

    # Load page with career data (to get enough match rows)
    url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={url_name}&f=ACareerqq"

    try:
        browser = await get_browser()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(3000)

        matches = await _scrape_match_rows(page)
        await page.close()

        logger.info(f"Scraped {len(matches)} match rows for {player_name}")

        if matches:
            result = compute_prior_from_matches(matches, surface, opponent_rank)
            if result:
                return result

    except Exception as e:
        logger.error(f"Failed to scrape {player_name}: {e}")

    logger.warning(f"Could not compute prior for {player_name}, using defaults")
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

        matches = await _scrape_match_rows(page)
        await page.close()

        if matches:
            result = compute_prior_from_matches(matches, surface, opponent_rank)
            if result:
                result["is_default"] = False
                return result

        # Fallback to summary parsing
        page2 = await browser.new_page()
        await page2.goto(url, timeout=15000)
        await page2.wait_for_timeout(3000)
        text = await page2.text_content("body") or ""
        await page2.close()

        from app.scraper.tennis_abstract import _parse_stat_block
        base = _parse_stat_block(text, "Last 52") or _parse_stat_block(text, "Career")
        if base:
            base["is_default"] = False
            return base

    except Exception as e:
        logger.error(f"Failed to scrape user URL {url}: {e}")
    return None


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
    return {
        "first_in": round(fi, 4),
        "first_won": round(fw, 4),
        "second_won": round(sw, 4),
        "p_serve": round(fi * fw + (1 - fi) * sw, 4),
    }


async def scrape_player_p(player_name: str, gender: str = "wta") -> float:
    stats = await scrape_player_serve_stats(player_name, gender)
    return stats["p_serve"]
