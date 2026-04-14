import os
import pytest
from app.kalshi.fetcher import extract_match_data
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_fetcher.db"


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_extract_match_data_basic():
    await init_db(DB_TEST_PATH)

    async with get_db(DB_TEST_PATH) as db:
        for minute, price in enumerate([60, 55, 70, 45, 80]):
            await db.execute(
                "INSERT INTO raw_prices (match_id, player, opponent, tournament, match_date, minute, price, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("MATCH1", "Player A", "Player B", "Tourney", "2024-03-01", minute, price, f"2024-03-01T00:{minute:02d}:00Z"),
            )
        await db.commit()

    player_stats = {
        "player a": {"ranking": 5, "win_rate_3m": 0.75},
        "player b": {"ranking": 10, "win_rate_3m": 0.60},
    }

    await extract_match_data(DB_TEST_PATH, "MATCH1", player_stats)

    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM extracted_data WHERE player = 'Player A' ORDER BY minute"
        )
        rows = await cursor.fetchall()

    assert len(rows) == 5

    # Minute 0: initial=60, current=60, max_after=max(60,55,70,45,80)=80
    assert rows[0]["initial_price"] == 60
    assert rows[0]["current_price"] == 60
    assert rows[0]["max_price_after"] == 80

    # Minute 3: initial=60, current=45, max_after=max(45,80)=80
    assert rows[3]["initial_price"] == 60
    assert rows[3]["current_price"] == 45
    assert rows[3]["max_price_after"] == 80

    # Minute 4 (last): initial=60, current=80, max_after=80
    assert rows[4]["current_price"] == 80
    assert rows[4]["max_price_after"] == 80

    # Check player stats
    assert rows[0]["player_ranking"] == 5
    assert rows[0]["opponent_ranking"] == 10
    assert rows[0]["player_win_rate_3m"] == pytest.approx(0.75)
    assert rows[0]["opponent_win_rate_3m"] == pytest.approx(0.60)


@pytest.mark.asyncio
async def test_extract_match_data_generates_no_side():
    """Player B data should be 100 - YES price."""
    await init_db(DB_TEST_PATH)

    async with get_db(DB_TEST_PATH) as db:
        for minute, price in enumerate([60, 55, 70]):
            await db.execute(
                "INSERT INTO raw_prices (match_id, player, opponent, tournament, match_date, minute, price, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("MATCH2", "Player A", "Player B", "Tourney", "2024-03-01", minute, price, f"2024-03-01T00:{minute:02d}:00Z"),
            )
        await db.commit()

    player_stats = {}
    await extract_match_data(DB_TEST_PATH, "MATCH2", player_stats)

    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM extracted_data WHERE player = 'Player B' ORDER BY minute"
        )
        rows = await cursor.fetchall()

    assert len(rows) == 3
    # Player B prices: 100-60=40, 100-55=45, 100-70=30
    # Minute 0: initial=40, current=40, max_after=max(40,45,30)=45
    assert rows[0]["initial_price"] == 40
    assert rows[0]["current_price"] == 40
    assert rows[0]["max_price_after"] == 45
