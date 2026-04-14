#!/usr/bin/env python3
"""Manually trigger a full data fetch from Kalshi + Sackmann.

Usage: cd backend && source .venv/bin/activate && python3 -m scripts.fetch_now
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import init_db
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient
from app.kalshi.fetcher import run_full_pipeline
from app.stats.sackmann import ensure_repos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not settings.kalshi_api_key_id:
        logger.error("KALSHI_API_KEY_ID not set in .env - cannot fetch data")
        sys.exit(1)

    await init_db(settings.db_path)
    ensure_repos(settings.sackmann_data_dir)

    auth = KalshiAuth(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
    client = KalshiClient("https://trading-api.kalshi.com/trade-api/v2", auth)

    try:
        await run_full_pipeline(client, settings.db_path, settings.sackmann_data_dir)
        logger.info("Done!")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
