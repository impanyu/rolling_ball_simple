# backend/tests/test_e2e.py
"""End-to-end test: insert data, query API, verify histogram."""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.database import init_db, get_db
from app.kalshi.fetcher import extract_match_data

DB_TEST_PATH = "/tmp/test_e2e.db"


@pytest_asyncio.fixture(autouse=True)
async def setup():
    os.environ["DB_PATH"] = DB_TEST_PATH
    import importlib
    import app.config
    importlib.reload(app.config)

    await init_db(DB_TEST_PATH)
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_full_flow():
    # 1. Insert raw prices simulating a match
    async with get_db(DB_TEST_PATH) as db:
        prices = [55, 60, 45, 70, 30, 80, 50, 65, 75, 40]
        for i, p in enumerate(prices):
            await db.execute(
                "INSERT INTO raw_prices (match_id, player, opponent, tournament, match_date, minute, price, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("E2E_MATCH", "Alice", "Bob", "Test Open", "2024-06-01", i, p, f"2024-06-01T10:{i:02d}:00Z"),
            )
        await db.commit()

    # 2. Run extraction
    stats = {
        "alice": {"ranking": 3, "win_rate_3m": 0.8},
        "bob": {"ranking": 15, "win_rate_3m": 0.55},
    }
    await extract_match_data(DB_TEST_PATH, "E2E_MATCH", stats)

    # 3. Query via API
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # All data
        resp = await client.get("/api/query")
        data = resp.json()
        assert data["total_count"] == 20  # 10 minutes x 2 sides

        # Filter by player ranking
        resp = await client.get("/api/query?player_ranking_min=1&player_ranking_max=5")
        data = resp.json()
        assert data["total_count"] == 10  # only Alice side (ranking=3)

        # Filter by initial price range
        resp = await client.get("/api/query?initial_price_min=50&initial_price_max=60")
        data = resp.json()
        # Alice initial=55 (in range), Bob initial=100-55=45 (out of range)
        assert data["total_count"] == 10

        # Verify histogram structure
        assert len(data["histogram"]) == 20
        total_pct = sum(b["percentage"] for b in data["histogram"])
        assert abs(total_pct - 100.0) < 0.1
