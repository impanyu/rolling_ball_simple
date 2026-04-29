import logging
import re
from datetime import datetime, timedelta
from app.scraper.browser import get_browser
from app.database import get_db

logger = logging.getLogger(__name__)

RANKINGS_URLS = {
    "ATP": "https://www.flashscoreusa.com/tennis/rankings/atp/",
    "WTA": "https://www.flashscoreusa.com/tennis/rankings/wta/",
}


def _fs_name_matches(fs_name: str, kalshi_name: str) -> bool:
    """Check if FlashScore name (e.g. 'Singh K.') matches Kalshi name (e.g. 'Karan Singh')."""
    fs_lower = fs_name.lower().replace('.', '').strip()
    parts = kalshi_name.strip().split()
    if not parts:
        return False
    last = parts[-1].lower()
    first_initial = parts[0][0].lower() if parts[0] else ""
    # FlashScore format: "LastName FirstInitial" e.g. "Singh K"
    return last in fs_lower and first_initial in fs_lower


async def scrape_all_match_starts() -> list[dict]:
    """Scrape FlashScore tennis page once, return all matches with start times."""
    browser = await get_browser()
    page = await browser.new_page()
    results = []

    try:
        await page.goto("https://www.flashscoreusa.com/tennis/", timeout=15000)
        await page.wait_for_timeout(4000)

        # Get all match rows with links
        match_rows = await page.evaluate("""() => {
            const rows = document.querySelectorAll('[class*="event__match"]');
            const results = [];
            for (const row of rows) {
                const text = row.textContent.trim().toLowerCase();
                const a = row.querySelector('a[href]');
                const href = a ? a.getAttribute('href') : null;
                // Extract participant names
                const parts = text.split(/\\d/)[0].trim();
                results.push({text: text.substring(0, 200), href: href});
            }
            return results;
        }""")

        # For each match with a link, visit detail page to get start time
        seen_hrefs = set()
        for row in match_rows:
            href = row.get("href")
            if not href or href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            if not href.startswith("http"):
                href = "https://www.flashscoreusa.com" + href

            try:
                await page.goto(href, timeout=10000)
                await page.wait_for_timeout(1500)

                data = await page.evaluate("""() => {
                    const startEl = document.querySelector('[class*="startTime"]');
                    const homeEl = document.querySelectorAll('[class*="participant__participantName"]');
                    const names = [];
                    homeEl.forEach(el => names.push(el.textContent.trim()));
                    return {
                        start_text: startEl ? startEl.textContent.trim() : null,
                        players: names,
                    };
                }""")

                if data.get("start_text") and len(data.get("players", [])) >= 2:
                    import time as _time
                    start_text = data["start_text"]
                    month_map = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                                 "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}

                    parsed = None
                    m = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM),?\s*(\w+)\s+(\d{1,2}),?\s*(\d{4})', start_text)
                    if m:
                        hour = int(m.group(1))
                        minute = int(m.group(2))
                        ampm = m.group(3)
                        if ampm == "PM" and hour != 12: hour += 12
                        elif ampm == "AM" and hour == 12: hour = 0
                        mon = month_map.get(m.group(4).lower(), 1)
                        day = int(m.group(5))
                        year = int(m.group(6))
                        utc_offset = _time.timezone if _time.daylight == 0 else _time.altzone
                        local_dt = datetime(year, mon, day, hour, minute)
                        utc_dt = local_dt + timedelta(seconds=utc_offset)
                        parsed = utc_dt.isoformat() + "Z"

                    if not parsed:
                        m2 = re.match(r'(\d{1,2}):(\d{2}),?\s*(\d{1,2})\s+(\w+)\s+(\d{4})', start_text)
                        if m2:
                            hour = int(m2.group(1))
                            minute = int(m2.group(2))
                            day = int(m2.group(3))
                            mon = month_map.get(m2.group(4).lower(), 1)
                            year = int(m2.group(5))
                            utc_offset = _time.timezone if _time.daylight == 0 else _time.altzone
                            local_dt = datetime(year, mon, day, hour, minute)
                            utc_dt = local_dt + timedelta(seconds=utc_offset)
                            parsed = utc_dt.isoformat() + "Z"

                    if parsed:
                        results.append({
                            "player_a": data["players"][0],
                            "player_b": data["players"][1] if len(data["players"]) > 1 else "",
                            "start_time": parsed,
                        })

            except Exception:
                continue

    except Exception as e:
        logger.warning(f"Failed to scrape FlashScore batch: {e}")
    finally:
        await page.close()

    logger.info(f"FlashScore batch: found {len(results)} match start times")
    return results


async def scrape_live_match_start(player_a: str, player_b: str) -> str | None:
    """Scrape FlashScore to find start time of a live/today match.

    1. Search FlashScore tennis page for the match
    2. Click into match detail page
    3. Read duelParticipant__startTime for precise start time

    Returns ISO timestamp string (UTC) or None if not found.
    """
    browser = await get_browser()
    page = await browser.new_page()

    try:
        await page.goto("https://www.flashscoreusa.com/tennis/", timeout=15000)
        await page.wait_for_timeout(4000)

        last_a = player_a.split()[-1].lower() if player_a else ""
        last_b = player_b.split()[-1].lower() if player_b else ""

        # Find match detail URL from the listing page
        match_url = await page.evaluate("""(args) => {
            const [lastA, lastB] = args;
            const rows = document.querySelectorAll('[class*="event__match"]');
            for (const row of rows) {
                const text = row.textContent.toLowerCase();
                if (text.includes(lastA) && text.includes(lastB)) {
                    const a = row.querySelector('a[href]');
                    if (a) return a.getAttribute('href');
                }
            }
            return null;
        }""", [last_a, last_b])

        if not match_url:
            logger.debug(f"FlashScore: no match found for {player_a} vs {player_b}")
            return None

        if not match_url.startswith("http"):
            match_url = "https://www.flashscoreusa.com" + match_url

        # Navigate to match detail page for precise start time
        await page.goto(match_url, timeout=15000)
        await page.wait_for_timeout(2000)

        start_text = await page.evaluate("""() => {
            const el = document.querySelector('[class*="startTime"]');
            return el ? el.textContent.trim() : null;
        }""")

        if not start_text:
            logger.debug(f"FlashScore: no startTime element on {match_url}")
            return None

        # Parse "05:30 PM, April 27, 2026" or "17:30, 27 April 2026" etc.
        import time as _time
        month_map = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
                     "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}

        # US format: "05:30 PM, April 27, 2026"
        m = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM),?\s*(\w+)\s+(\d{1,2}),?\s*(\d{4})', start_text)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2))
            ampm = m.group(3)
            if ampm == "PM" and hour != 12: hour += 12
            elif ampm == "AM" and hour == 12: hour = 0
            mon = month_map.get(m.group(4).lower(), 1)
            day = int(m.group(5))
            year = int(m.group(6))

            utc_offset = _time.timezone if _time.daylight == 0 else _time.altzone
            local_dt = datetime(year, mon, day, hour, minute)
            utc_dt = local_dt + timedelta(seconds=utc_offset)
            logger.info(f"FlashScore: {player_a} vs {player_b} start={utc_dt.isoformat()}Z (from '{start_text}')")
            return utc_dt.isoformat() + "Z"

        # European format: "17:30, 27 April 2026"
        m2 = re.match(r'(\d{1,2}):(\d{2}),?\s*(\d{1,2})\s+(\w+)\s+(\d{4})', start_text)
        if m2:
            hour = int(m2.group(1))
            minute = int(m2.group(2))
            day = int(m2.group(3))
            mon = month_map.get(m2.group(4).lower(), 1)
            year = int(m2.group(5))

            utc_offset = _time.timezone if _time.daylight == 0 else _time.altzone
            local_dt = datetime(year, mon, day, hour, minute)
            utc_dt = local_dt + timedelta(seconds=utc_offset)
            logger.info(f"FlashScore: {player_a} vs {player_b} start={utc_dt.isoformat()}Z (from '{start_text}')")
            return utc_dt.isoformat() + "Z"

        logger.warning(f"FlashScore: could not parse startTime '{start_text}'")

    except Exception as e:
        logger.warning(f"Failed to scrape FlashScore: {e}")
    finally:
        await page.close()

    return None


async def scrape_player_list(max_per_tour: int = 2000) -> list[dict]:
    """Scrape top N ATP + top N WTA from FlashScore USA rankings."""
    browser = await get_browser()
    page = await browser.new_page()
    all_players = []

    try:
        for tour, url in RANKINGS_URLS.items():
            await page.goto(url, timeout=15000)
            await page.wait_for_timeout(4000)

            # Click "Show more" to load all players
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(500)
            await page.evaluate("""() => {
                const btn = document.querySelector('button.wclButtonLink');
                if (btn) btn.click();
            }""")
            await page.wait_for_timeout(3000)

            players = await page.evaluate("""() => {
                const links = document.querySelectorAll('a[href*="/player/"]');
                return Array.from(links).map((a, i) => ({
                    name: a.textContent.trim(),
                    href: a.getAttribute('href'),
                    rank: i + 1,
                }));
            }""")

            players = players[:max_per_tour]
            for p in players:
                p["tour"] = tour
            all_players.extend(players)
            logger.info(f"Found {len(players)} {tour} players from rankings")
    finally:
        await page.close()

    return all_players


async def scrape_player_results(player_href: str, player_name: str, page=None) -> list[dict]:
    """Scrape recent match results for a single player from their FlashScore page."""
    browser = await get_browser()
    url = f"https://www.flashscoreusa.com{player_href}results/"
    own_page = page is None
    if own_page:
        page = await browser.new_page()
    matches = []

    try:
        await page.goto(url, timeout=15000)
        await page.wait_for_timeout(2000)

        raw = await page.evaluate("""() => {
            const rows = document.querySelectorAll('[class*="event__match"]');
            const results = [];

            rows.forEach(row => {
                try {
                    const homeEl = row.querySelector('[class*="homeParticipant"]');
                    const awayEl = row.querySelector('[class*="awayParticipant"]');
                    const timeEl = row.querySelector('[class*="event__time"]');
                    if (!homeEl || !awayEl) return;

                    const home = homeEl.textContent.trim();
                    const away = awayEl.textContent.trim();
                    const timeText = timeEl ? timeEl.textContent.trim() : '';

                    const parts = row.querySelectorAll('[class*="event__part"]');
                    const scores = Array.from(parts).map(p => p.textContent.trim());
                    let homeS = 0, awayS = 0;
                    for (let i = 0; i < scores.length - 1; i += 2) {
                        const a = parseInt(scores[i]) || 0;
                        const b = parseInt(scores[i+1]) || 0;
                        if (a > b) homeS++;
                        else if (b > a) awayS++;
                    }

                    if (homeS === 0 && awayS === 0) return;

                    results.push({
                        home, away, time_text: timeText,
                        winner: homeS > awayS ? home : away,
                        loser: homeS > awayS ? away : home,
                    });
                } catch(e) {}
            });
            return results;
        }""")

        today = datetime.now()
        year = today.year
        month_map = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        for m in raw:
            t = m["time_text"]
            m["match_date"] = None
            m["start_time"] = None

            # Format: "Nov 16, 2025" (US with year, no time)
            dm3 = re.match(r'([A-Za-z]{3})\s*(\d{1,2}),\s*(\d{4})', t)
            if dm3:
                mon = month_map.get(dm3.group(1).lower())
                if mon:
                    m["match_date"] = f"{int(dm3.group(3))}-{mon:02d}-{int(dm3.group(2)):02d}"
            else:
                # Format: "22.04. 04:10" (European)
                dm = re.match(r'(\d{2})\.(\d{2})\.\s*(\d{2}):(\d{2})', t)
                if dm:
                    m["match_date"] = f"{year}-{int(dm.group(2)):02d}-{int(dm.group(1)):02d}"
                    m["start_time"] = f"{int(dm.group(3)):02d}:{int(dm.group(4)):02d}"
                else:
                    # Format: "Apr 1208:10 AM" or "Apr 12 08:10 AM" (US)
                    dm2 = re.match(r'([A-Za-z]{3})\s*(\d{1,2})\s*(\d{1,2}):(\d{2})\s*(AM|PM)?', t)
                    if dm2:
                        mon = month_map.get(dm2.group(1).lower())
                        if mon:
                            m["match_date"] = f"{year}-{mon:02d}-{int(dm2.group(2)):02d}"
                            hour = int(dm2.group(3))
                            minute = int(dm2.group(4))
                            ampm = dm2.group(5)
                            if ampm == "PM" and hour != 12:
                                hour += 12
                            elif ampm == "AM" and hour == 12:
                                hour = 0
                            m["start_time"] = f"{hour:02d}:{minute:02d}"

            matches.append(m)

    except Exception as e:
        logger.error(f"Failed to scrape results for {player_name}: {e}")
    finally:
        if own_page:
            await page.close()

    return matches


async def store_rankings(db_path: str, players: list[dict]) -> None:
    """Store FlashScore rankings into DB and update extracted_data."""
    now = datetime.now().strftime("%Y-%m-%d")

    async with get_db(db_path) as db:
        await db.execute("DELETE FROM flashscore_rankings")
        for p in players:
            name_fs = p["name"]
            parts = name_fs.split()
            if len(parts) >= 2:
                normalized = f"{' '.join(parts[1:])} {parts[0]}"
            else:
                normalized = name_fs
            await db.execute(
                "INSERT OR REPLACE INTO flashscore_rankings (player_name, tour, ranking, href, updated_at) VALUES (?, ?, ?, ?, ?)",
                (normalized.lower(), p["tour"], p["rank"], p.get("href", ""), now),
            )
        await db.commit()
        logger.info(f"Stored {len(players)} FlashScore rankings")

        updated = await db.execute("""
            UPDATE extracted_data
            SET player_ranking = (
                SELECT r.ranking FROM flashscore_rankings r
                WHERE LOWER(extracted_data.player) = r.player_name
            )
            WHERE player_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.player) = r.player_name)
        """)
        cnt_p = updated.rowcount

        updated2 = await db.execute("""
            UPDATE extracted_data
            SET opponent_ranking = (
                SELECT r.ranking FROM flashscore_rankings r
                WHERE LOWER(extracted_data.opponent) = r.player_name
            )
            WHERE opponent_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.opponent) = r.player_name)
        """)
        cnt_o = updated2.rowcount
        await db.commit()
        logger.info(f"Updated rankings in extracted_data: {cnt_p} player, {cnt_o} opponent")


async def scrape_and_store_results(db_path: str, max_per_tour: int = 600) -> int:
    """Full pipeline: get player list, scrape each player's results, store in DB."""
    players = await scrape_player_list(max_per_tour=max_per_tour)
    await store_rankings(db_path, players)
    logger.info(f"Scraping results for {len(players)} players...")

    inserted = 0
    batch_inserted = 0
    page = None

    try:
        for i, player in enumerate(players):
            try:
                if page is None or page.is_closed():
                    browser = await get_browser()
                    page = await browser.new_page()

                matches = await scrape_player_results(player["href"], player["name"], page=page)

                async with get_db(db_path) as db:
                    for m in matches:
                        if not m.get("match_date"):
                            continue
                        md = m["match_date"]
                        mmdd = md[5:]
                        existing = await db.execute(
                            "SELECT 1 FROM match_results WHERE winner = ? AND loser = ? AND SUBSTR(match_date, 6) = ? AND tour = ? LIMIT 1",
                            (m["winner"], m["loser"], mmdd, player["tour"]),
                        )
                        if await existing.fetchone():
                            continue
                        try:
                            await db.execute(
                                "INSERT OR IGNORE INTO match_results (winner, loser, match_date, tour, tournament, start_time) VALUES (?, ?, ?, ?, ?, ?)",
                                (m["winner"], m["loser"], md, player["tour"], None, m.get("start_time")),
                            )
                            batch_inserted += 1
                        except Exception:
                            pass
                    await db.commit()

                inserted += batch_inserted
                if (i + 1) % 20 == 0:
                    logger.info(f"  Progress: {i + 1}/{len(players)} players, {inserted} results inserted")
                    batch_inserted = 0

                import asyncio
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Failed player {player['name']}: {e}")
                page = None
    finally:
        if page and not page.is_closed():
            await page.close()

    logger.info(f"Done: {inserted} results from {len(players)} players")
    return inserted


async def get_winrates_from_db(db_path: str, min_win_rate: float = 80, min_matches: int = 5, days: int = 30) -> dict:
    """Query stored results for player win rates."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    async with get_db(db_path) as db:
        cursor = await db.execute("""
            WITH player_stats AS (
                SELECT player, tour, SUM(wins) as wins, SUM(losses) as losses
                FROM (
                    SELECT winner as player, tour, 1 as wins, 0 as losses
                    FROM match_results WHERE match_date >= ?
                    UNION ALL
                    SELECT loser as player, tour, 0 as wins, 1 as losses
                    FROM match_results WHERE match_date >= ?
                )
                GROUP BY player, tour
            )
            SELECT ps.player, ps.tour, ps.wins, ps.losses, ps.wins + ps.losses as total,
                   ROUND(ps.wins * 100.0 / (ps.wins + ps.losses), 1) as win_rate,
                   (SELECT fr.href FROM flashscore_rankings fr
                    WHERE fr.tour = ps.tour
                      AND fr.player_name LIKE '%' || LOWER(SUBSTR(ps.player, 1, INSTR(ps.player, ' ') - 1))
                      AND fr.player_name LIKE REPLACE(LOWER(SUBSTR(ps.player, INSTR(ps.player, ' ') + 1, 3)), '.', '') || '%'
                    LIMIT 1) as href,
                   (SELECT fr.ranking FROM flashscore_rankings fr
                    WHERE fr.tour = ps.tour
                      AND fr.player_name LIKE '%' || LOWER(SUBSTR(ps.player, 1, INSTR(ps.player, ' ') - 1))
                      AND fr.player_name LIKE REPLACE(LOWER(SUBSTR(ps.player, INSTR(ps.player, ' ') + 1, 3)), '.', '') || '%'
                    LIMIT 1) as ranking
            FROM player_stats ps
            WHERE ps.wins + ps.losses >= ?
              AND ps.wins * 100.0 / (ps.wins + ps.losses) >= ?
            ORDER BY win_rate DESC, total DESC
        """, (cutoff, cutoff, min_matches, min_win_rate))
        rows = await cursor.fetchall()

        total_cursor = await db.execute(
            "SELECT COUNT(*) FROM match_results WHERE match_date >= ?", (cutoff,)
        )
        total = (await total_cursor.fetchone())[0]

    players = [
        {
            "player": r[0], "tour": r[1], "wins": r[2],
            "losses": r[3], "total": r[4], "win_rate": r[5],
            "href": r[6] or "", "ranking": r[7],
        }
        for r in rows
    ]
    return {"players": players, "total_matches": total}
