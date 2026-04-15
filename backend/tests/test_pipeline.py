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

    # Mock trades: 3 trades, each in a different minute
    mock_client.get_trades.return_value = [
        {"created_time": "2024-03-01T10:00:30Z", "yes_price_dollars": "0.62", "ticker": "MKT1"},
        {"created_time": "2024-03-01T10:01:30Z", "yes_price_dollars": "0.55", "ticker": "MKT1"},
        {"created_time": "2024-03-01T10:02:30Z", "yes_price_dollars": "0.75", "ticker": "MKT1"},
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
