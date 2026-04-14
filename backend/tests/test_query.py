# backend/tests/test_query.py
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_query.db"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        for i in range(20):
            await db.execute(
                "INSERT INTO extracted_data "
                "(match_id, player, opponent, tournament, match_date, minute, "
                "initial_price, current_price, max_price_after, "
                "player_ranking, opponent_ranking, player_win_rate_3m, opponent_win_rate_3m) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"MATCH{i // 5}",
                    "Player A",
                    "Player B",
                    "Tourney",
                    "2024-03-01",
                    i,
                    50.0,
                    30.0 + i,
                    40.0 + i * 3,
                    5,
                    10,
                    0.7,
                    0.5,
                ),
            )
        await db.commit()
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.fixture
def app():
    os.environ["DB_PATH"] = DB_TEST_PATH
    # Force reload settings with new DB_PATH
    import importlib
    import app.config
    importlib.reload(app.config)
    from app.routes.query import router
    from fastapi import FastAPI
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_query_no_filters(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 20
    assert len(data["histogram"]) == 20
    assert "mean" in data["stats"]


@pytest.mark.asyncio
async def test_query_with_price_filter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query?initial_price_min=45&initial_price_max=55")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 20


@pytest.mark.asyncio
async def test_query_with_ranking_filter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query?player_ranking_min=1&player_ranking_max=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 0


@pytest.mark.asyncio
async def test_histogram_bins_are_5_cents(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query")
    data = resp.json()
    bins = data["histogram"]
    for b in bins:
        assert b["bin_end"] - b["bin_start"] == 5
    assert bins[0]["bin_start"] == 0
    assert bins[-1]["bin_end"] == 100
