import logging
import re
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
    """Parse serve stats, adjusting for surface and opponent strength.
    If opponent_rank <= 10, blend with 'vs Top 10' stats.
    If opponent_rank 11-50, interpolate between 'vs Top 10' and overall.
    """
    # Get surface-specific or overall stats
    base = None
    if surface and surface.lower() in SURFACE_LABELS:
        label = SURFACE_LABELS[surface.lower()]
        base = _parse_stat_block(text, label)
        if not base:
            logger.warning(f"Could not find {label} surface stats, falling back to Last 52")

    if not base:
        base = _parse_stat_block(text, "Last 52")

    if not base:
        return None

    # Adjust for opponent strength if ranking is available
    if opponent_rank and opponent_rank <= 50:
        top10_stats = _parse_stat_block(text, "vs Top 10")
        if top10_stats:
            if opponent_rank <= 10:
                weight = 1.0
            else:
                weight = (50 - opponent_rank) / 40.0  # linear: rank 10→1.0, rank 50→0.0

            for key in ["first_in", "first_won", "second_won"]:
                base[key] = round(base[key] * (1 - weight) + top10_stats[key] * weight, 4)
            base["p_serve"] = round(
                base["first_in"] * base["first_won"] + (1 - base["first_in"]) * base["second_won"], 4
            )
            logger.info(f"Adjusted for opponent rank {opponent_rank} (top10 weight={weight:.2f})")

    return base


def _generate_name_variants(player_name: str) -> list[str]:
    """Generate multiple URL name variants to try on Tennis Abstract.
    E.g. 'Carlos Juan Angelo Prado' -> [
        'CarlosJuanAngeloPrado',  # full name
        'CarlosPrado',            # first + last
        'AngeloPrado',            # last-first-name + last
        'CJAPrado',               # initials + last
    ]
    """
    parts = player_name.strip().split()
    if len(parts) <= 1:
        return [player_name.replace(" ", "")]

    variants = []
    # Full name (no spaces)
    variants.append("".join(parts))

    if len(parts) > 2:
        # First + Last
        variants.append(parts[0] + parts[-1])
        # Second-to-last + Last (some players go by middle name)
        variants.append(parts[-2] + parts[-1])

    return variants


async def scrape_player_serve_stats(
    player_name: str, gender: str = "wta", surface: str | None = None,
    opponent_rank: int | None = None,
) -> dict:
    """Scrape player's serve components from Tennis Abstract.
    Adjusts for surface and opponent ranking. Tries multiple name variants.
    """
    prefix = "w" if gender == "wta" else ""
    defaults = DEFAULTS_WTA if gender == "wta" else DEFAULTS_ATP

    variants = _generate_name_variants(player_name)

    browser = await get_browser()

    for variant in variants:
        url = f"https://www.tennisabstract.com/cgi-bin/{prefix}player-classic.cgi?p={variant}&f=ACareerqq"
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=15000)
            await page.wait_for_timeout(3000)
            text = await page.text_content("body") or ""
            await page.close()

            result = parse_serve_stats_from_text(text, surface, opponent_rank)
            if result:
                surface_label = surface or "overall"
                logger.info(f"Got serve stats for {player_name} as '{variant}' ({surface_label}, vs rank {opponent_rank}): fi={result['first_in']}, fw={result['first_won']}, sw={result['second_won']}, p={result['p_serve']}")
                return result

        except Exception as e:
            logger.debug(f"Failed variant '{variant}' for {player_name}: {e}")
            continue

    # Also try without gender prefix
    alt_prefix = "" if prefix == "w" else "w"
    for variant in variants[:1]:
        url = f"https://www.tennisabstract.com/cgi-bin/{alt_prefix}player-classic.cgi?p={variant}&f=ACareerqq"
        try:
            page = await browser.new_page()
            await page.goto(url, timeout=15000)
            await page.wait_for_timeout(3000)
            text = await page.text_content("body") or ""
            await page.close()

            result = parse_serve_stats_from_text(text, surface, opponent_rank)
            if result:
                logger.info(f"Got serve stats for {player_name} using alt gender prefix")
                return result
        except Exception:
            pass

    logger.warning(f"Could not parse stats for {player_name} (tried {variants}), using defaults")
    p = defaults["first_in"] * defaults["first_won"] + (1 - defaults["first_in"]) * defaults["second_won"]
    return {**defaults, "p_serve": round(p, 4), "is_default": True}


async def scrape_from_url(
    url: str, surface: str | None = None, opponent_rank: int | None = None
) -> dict | None:
    """Scrape serve stats from a user-provided Tennis Abstract URL."""
    # Convert non-classic URLs to classic format (our parser needs it)
    if "player.cgi" in url and "player-classic.cgi" not in url:
        url = url.replace("player.cgi", "player-classic.cgi")
    # Ensure the career stats filter is applied
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
