import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.kalshi.fetcher import run_full_pipeline
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_pipeline.db"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_run_full_pipeline():
    await init_db(DB_TEST_PATH)

    mock_client = AsyncMock()

    mock_client.get_events.return_value = [
        {
            "event_ticker": "EVT1",
            "title": "Match: Djokovic vs Alcaraz",
            "category": "tennis",
        }
    ]
    mock_client.get_markets.return_value = [
        {
            "ticker": "MKT1",
            "event_ticker": "EVT1",
            "title": "Djokovic to win",
            "subtitle": "Novak Djokovic vs Carlos Alcaraz",
            "status": "finalized",
            "open_time": "2024-03-01T10:00:00Z",
            "close_time": "2024-03-01T12:00:00Z",
            "yes_sub_title": "Novak Djokovic",
            "no_sub_title": "Carlos Alcaraz",
        }
    ]

    mock_client.get_candlesticks.return_value = [
        {"t": 1709290800, "open": 60, "high": 65, "low": 58, "close": 62, "volume": 100},
        {"t": 1709290860, "open": 62, "high": 70, "low": 60, "close": 55, "volume": 80},
        {"t": 1709290920, "open": 55, "high": 75, "low": 50, "close": 75, "volume": 120},
    ]

    with patch("app.kalshi.fetcher.get_player_stats_for_match", return_value={}):
        await run_full_pipeline(mock_client, DB_TEST_PATH, "/tmp/sackmann_test")

    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM raw_prices")
        raw_count = (await cursor.fetchone())[0]
        assert raw_count == 3

    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM extracted_data")
        ext_count = (await cursor.fetchone())[0]
        assert ext_count == 6  # 3 minutes x 2 sides
