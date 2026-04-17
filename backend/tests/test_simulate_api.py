import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("KALSHI_API_KEY_ID", "")
os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
os.environ.setdefault("OPENAI_API_KEY", "test-key")


@pytest.fixture
def app():
    from app.routes.simulate import router
    from fastapi import FastAPI
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.mark.asyncio
async def test_simulate_endpoint(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/simulate", json={
            "p_a": 0.65,
            "p_b": 0.60,
            "score": {
                "sets": [0, 0],
                "games": [0, 0],
                "points": [0, 0],
                "serving": "a"
            },
            "num_simulations": 1000
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "current_win_prob" in data
    assert "slices" in data
    assert len(data["slices"]) == 5  # 5 horizons: 10, 20, 30, 50, 80
    assert len(data["slices"][0]["histogram"]) == 20
    assert "combined" in data
    assert len(data["combined"]["histogram"]) == 20


@pytest.mark.asyncio
async def test_simulate_mid_match(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/simulate", json={
            "p_a": 0.65,
            "p_b": 0.60,
            "score": {
                "sets": [1, 0],
                "games": [3, 2],
                "points": [0, 0],
                "serving": "a"
            },
            "num_simulations": 1000
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_win_prob"] > 50
