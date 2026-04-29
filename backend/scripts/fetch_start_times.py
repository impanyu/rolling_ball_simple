#!/usr/bin/env python3
"""Fetch occurrence_datetime for all existing matches and rebuild extracted_data.

Usage: cd backend && source .venv/bin/activate && python3 -m scripts.fetch_start_times
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import init_db, get_db
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient
from app.kalshi.fetcher import extract_match_data, get_player_stats_for_match, _get_sackmann_data
from app.stats.sackmann import ensure_repos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not settings.kalshi_api_key_id:
        logger.error("KALSHI_API_KEY_ID not set")
        sys.exit(1)

    await init_db(settings.db_path)
    ensure_repos(settings.sackmann_data_dir)
    _get_sackmann_data(settings.sackmann_data_dir)

    auth = KalshiAuth(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
    client = KalshiClient("https://api.elections.kalshi.com/trade-api/v2", auth)

    # Get all match_ids
    async with get_db(settings.db_path) as db:
        cursor = await db.execute("SELECT DISTINCT match_id FROM raw_prices")
        match_ids = [row[0] for row in await cursor.fetchall()]

        cursor2 = await db.execute("SELECT match_id FROM match_start_times")
        existing = {row[0] for row in await cursor2.fetchall()}

    need_fetch = [m for m in match_ids if m not in existing]
    logger.info(f"Total matches: {len(match_ids)}, need start times: {len(need_fetch)}")

    # Fetch start times from Kalshi API
    fetched = 0
    for i, match_id in enumerate(need_fetch):
        try:
            markets = await client.get_markets(event_ticker=match_id)
            if markets:
                start_time = markets[0].get("close_time") or ""
                if start_time:
                    async with get_db(settings.db_path) as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO match_start_times (match_id, start_time) VALUES (?, ?)",
                            (match_id, start_time),
                        )
                        await db.commit()
                    fetched += 1
        except Exception as e:
            logger.debug(f"Failed {match_id}: {e}")

        if (i + 1) % 50 == 0:
            logger.info(f"  {i + 1}/{len(need_fetch)} checked, {fetched} start times found")
            await asyncio.sleep(1)

    logger.info(f"Fetched {fetched} start times")
    await client.close()

    # Rebuild extracted_data
    logger.info("Rebuilding extracted_data...")
    async with get_db(settings.db_path) as db:
        await db.execute("DELETE FROM extracted_data")
        await db.commit()

    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            "SELECT match_id, player, opponent, match_date FROM raw_prices GROUP BY match_id"
        )
        matches = await cursor.fetchall()

    for i, row in enumerate(matches):
        match_id, player, opponent, match_date = row
        player_stats = get_player_stats_for_match(settings.sackmann_data_dir, player, opponent, match_date)
        await extract_match_data(settings.db_path, match_id, player_stats)
        if (i + 1) % 100 == 0:
            logger.info(f"  {i + 1}/{len(matches)} rebuilt")

    # Update rankings from flashscore_rankings table
    async with get_db(settings.db_path) as db:
        await db.execute("""
            UPDATE extracted_data
            SET player_ranking = (
                SELECT r.ranking FROM flashscore_rankings r WHERE LOWER(extracted_data.player) = r.player_name
            )
            WHERE player_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.player) = r.player_name)
        """)
        await db.execute("""
            UPDATE extracted_data
            SET opponent_ranking = (
                SELECT r.ranking FROM flashscore_rankings r WHERE LOWER(extracted_data.opponent) = r.player_name
            )
            WHERE opponent_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.opponent) = r.player_name)
        """)
        await db.commit()

    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
