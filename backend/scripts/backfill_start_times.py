#!/usr/bin/env python3
"""Backfill start_time in match_results by re-scraping FlashScore player pages.

Only updates existing rows, doesn't insert new ones.
Usage: cd backend && source .venv/bin/activate && python3 -m scripts.backfill_start_times
"""
import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, get_db
from app.config import settings
from app.scraper.browser import get_browser
from app.scraper.flashscore_results import scrape_player_list

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


async def main():
    await init_db(settings.db_path)

    players = await scrape_player_list(max_per_tour=600)
    logger.info(f"Got {len(players)} players")

    browser = await get_browser()
    page = await browser.new_page()
    updated = 0
    today = datetime.now()
    year = today.year

    try:
        for i, player in enumerate(players):
            try:
                if page.is_closed():
                    page = await browser.new_page()

                url = f"https://www.flashscoreusa.com{player['href']}results/"
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
                            if (!homeEl || !awayEl || !timeEl) return;
                            results.push({
                                home: homeEl.textContent.trim(),
                                away: awayEl.textContent.trim(),
                                time_text: timeEl.textContent.trim(),
                            });
                        } catch(e) {}
                    });
                    return results;
                }""")

                batch = 0
                async with get_db(settings.db_path) as db:
                    for m in raw:
                        t = m["time_text"]
                        match_date = None
                        start_time = None

                        # "Nov 16, 2025" (with year, no time)
                        dm3 = re.match(r'([A-Za-z]{3})\s*(\d{1,2}),\s*(\d{4})', t)
                        if dm3:
                            mon = MONTH_MAP.get(dm3.group(1).lower())
                            if mon:
                                match_date = f"{int(dm3.group(3))}-{mon:02d}-{int(dm3.group(2)):02d}"
                        else:
                            # "Apr 1208:10 AM"
                            dm2 = re.match(r'([A-Za-z]{3})\s*(\d{1,2})\s*(\d{1,2}):(\d{2})\s*(AM|PM)?', t)
                            if dm2:
                                mon = MONTH_MAP.get(dm2.group(1).lower())
                                if mon:
                                    match_date = f"{year}-{mon:02d}-{int(dm2.group(2)):02d}"
                                    hour = int(dm2.group(3))
                                    minute = int(dm2.group(4))
                                    ampm = dm2.group(5)
                                    if ampm == "PM" and hour != 12:
                                        hour += 12
                                    elif ampm == "AM" and hour == 12:
                                        hour = 0
                                    start_time = f"{hour:02d}:{minute:02d}"

                        if not match_date or not start_time:
                            continue

                        # Update matching rows
                        cursor = await db.execute(
                            """UPDATE match_results SET start_time = ?
                               WHERE match_date = ? AND start_time IS NULL
                                 AND ((winner = ? AND loser = ?) OR (winner = ? AND loser = ?))""",
                            (start_time, match_date, m["home"], m["away"], m["away"], m["home"]),
                        )
                        batch += cursor.rowcount

                    await db.commit()
                updated += batch

                if (i + 1) % 50 == 0:
                    logger.info(f"  {i + 1}/{len(players)}, {updated} start_times updated")

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error(f"Failed {player['name']}: {e}")
                page = None
                page = await browser.new_page()
    finally:
        if page and not page.is_closed():
            await page.close()

    logger.info(f"Done: {updated} start_times backfilled")


if __name__ == "__main__":
    asyncio.run(main())
