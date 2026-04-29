#!/usr/bin/env python3
"""Regenerate extracted_data from existing raw_prices (no API calls needed).

Usage: cd backend && source .venv/bin/activate && python3 -m scripts.rebuild_extracted
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import init_db, get_db
from app.kalshi.fetcher import extract_match_data, get_player_stats_for_match, _get_sackmann_data
from app.stats.sackmann import ensure_repos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await init_db(settings.db_path)
    ensure_repos(settings.sackmann_data_dir)

    # Pre-warm Sackmann cache
    _get_sackmann_data(settings.sackmann_data_dir)

    async with get_db(settings.db_path) as db:
        await db.execute("DELETE FROM extracted_data")
        await db.commit()
        logger.info("Cleared extracted_data")

        cursor = await db.execute(
            "SELECT match_id, player, opponent, match_date "
            "FROM raw_prices GROUP BY match_id"
        )
        matches = await cursor.fetchall()

    logger.info(f"Regenerating extracted_data for {len(matches)} matches")

    for i, row in enumerate(matches):
        match_id, player, opponent, match_date = row
        player_stats = get_player_stats_for_match(
            settings.sackmann_data_dir, player, opponent, match_date
        )
        await extract_match_data(settings.db_path, match_id, player_stats)
        if (i + 1) % 100 == 0:
            logger.info(f"  {i + 1}/{len(matches)} done")

    logger.info("Done!")


if __name__ == "__main__":
    asyncio.run(main())
