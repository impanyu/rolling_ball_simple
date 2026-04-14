# backend/tests/test_main.py
import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("KALSHI_API_KEY_ID", "")
os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
os.environ.setdefault("DB_PATH", "/tmp/test_main.db")

from app.main import app


@pytest.fixture(autouse=True)
def cleanup():
    yield
    if os.path.exists("/tmp/test_main.db"):
        os.remove("/tmp/test_main.db")


@pytest.mark.asyncio
async def test_app_starts_and_serves_query():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] == 0
    assert len(data["histogram"]) == 20


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
