# backend/tests/test_main.py
import os
import importlib
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

DB_TEST_PATH = "/tmp/test_main.db"


@pytest_asyncio.fixture(autouse=True)
async def setup_and_cleanup():
    os.environ["KALSHI_API_KEY_ID"] = ""
    os.environ["KALSHI_PRIVATE_KEY_PATH"] = "./secrets/test.pem"
    os.environ["DB_PATH"] = DB_TEST_PATH
    import app.config
    importlib.reload(app.config)
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.fixture
def test_app():
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_app_starts_and_serves_query(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 0
    assert len(data["histogram"]) == 20


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
