#!/usr/bin/env python3
"""Fetch actual match results from Kalshi API and store in extracted_data.won column.

Usage: cd backend && source .venv/bin/activate && python3 -m scripts.fetch_results
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not settings.kalshi_api_key_id:
        logger.error("KALSHI_API_KEY_ID not set")
        sys.exit(1)

    await init_db(settings.db_path)

    auth = KalshiAuth(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
    client = KalshiClient("https://api.elections.kalshi.com/trade-api/v2", auth)

    async with get_db(settings.db_path) as db:
        cursor = await db.execute(
            "SELECT DISTINCT match_id FROM raw_prices"
        )
        match_ids = [row[0] for row in await cursor.fetchall()]

    logger.info(f"Fetching results for {len(match_ids)} matches")
    updated = 0

    for i, match_id in enumerate(match_ids):
        try:
            markets = await client.get_markets(event_ticker=match_id)
            if len(markets) != 2:
                continue

            markets.sort(key=lambda m: m["ticker"])
            # First market's yes_sub_title = player_a
            player_a = markets[0].get("yes_sub_title", "")
            result_a = markets[0].get("result", "")  # "yes" or "no"

            if not result_a or result_a not in ("yes", "no"):
                continue

            won_a = 1 if result_a == "yes" else 0
            won_b = 1 - won_a

            async with get_db(settings.db_path) as db:
                # Update player_a's rows
                await db.execute(
                    "UPDATE extracted_data SET won = ? WHERE match_id = ? AND player = ?",
                    (won_a, match_id, player_a),
                )
                # Update player_b's rows (opponent)
                cursor = await db.execute(
                    "SELECT DISTINCT player FROM extracted_data WHERE match_id = ? AND player != ?",
                    (match_id, player_a),
                )
                player_b_row = await cursor.fetchone()
                if player_b_row:
                    await db.execute(
                        "UPDATE extracted_data SET won = ? WHERE match_id = ? AND player = ?",
                        (won_b, match_id, player_b_row[0]),
                    )
                await db.commit()
                updated += 1

        except Exception as e:
            if "429" in str(e):
                await asyncio.sleep(5)
            continue

        if (i + 1) % 100 == 0:
            logger.info(f"  {i + 1}/{len(match_ids)}, {updated} updated")

    logger.info(f"Done: {updated} matches with results")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
