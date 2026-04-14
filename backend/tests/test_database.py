import os
import pytest
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_tennis_odds.db"


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert "raw_prices" in tables
    assert "extracted_data" in tables
    assert "player_stats" in tables


@pytest.mark.asyncio
async def test_raw_prices_columns():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(raw_prices)")
        columns = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "match_id", "player", "opponent", "tournament",
                "match_date", "minute", "price", "timestamp"}
    assert columns == expected


@pytest.mark.asyncio
async def test_extracted_data_columns():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(extracted_data)")
        columns = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "match_id", "player", "opponent", "tournament",
                "match_date", "minute", "initial_price", "current_price",
                "max_price_after", "player_ranking", "opponent_ranking",
                "player_win_rate_3m", "opponent_win_rate_3m"}
    assert columns == expected
