import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from app.kalshi.client import KalshiClient


@pytest.fixture
def mock_auth():
    auth = MagicMock()
    auth.get_headers.return_value = {
        "KALSHI-ACCESS-KEY": "k",
        "KALSHI-ACCESS-SIGNATURE": "s",
        "KALSHI-ACCESS-TIMESTAMP": "t",
        "Content-Type": "application/json",
    }
    return auth


@pytest.mark.asyncio
async def test_get_events(mock_auth):
    client = KalshiClient("https://api.example.com", mock_auth)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "events": [{"ticker": "EVT1"}],
        "cursor": "",
    }
    mock_response.raise_for_status = MagicMock()

    client._http = AsyncMock()
    client._http.request = AsyncMock(return_value=mock_response)
    client._http.is_closed = False

    events = await client.get_events(series_ticker="KXATPMATCH")
    assert len(events) == 1
    assert events[0]["ticker"] == "EVT1"


@pytest.mark.asyncio
async def test_get_candlesticks(mock_auth):
    client = KalshiClient("https://api.example.com", mock_auth)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "candlesticks": [
            {"t": 1000, "open": 50, "high": 55, "low": 48, "close": 52},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    client._http = AsyncMock()
    client._http.request = AsyncMock(return_value=mock_response)
    client._http.is_closed = False

    candles = await client.get_candlesticks("TICKER-1")
    assert len(candles) == 1
    assert candles[0]["close"] == 52


@pytest.mark.asyncio
async def test_pagination(mock_auth):
    client = KalshiClient("https://api.example.com", mock_auth)

    page1 = MagicMock()
    page1.json.return_value = {"events": [{"ticker": "A"}], "cursor": "page2"}
    page1.raise_for_status = MagicMock()

    page2 = MagicMock()
    page2.json.return_value = {"events": [{"ticker": "B"}], "cursor": ""}
    page2.raise_for_status = MagicMock()

    client._http = AsyncMock()
    client._http.request = AsyncMock(side_effect=[page1, page2])
    client._http.is_closed = False

    events = await client.get_events()
    assert len(events) == 2
    assert events[0]["ticker"] == "A"
    assert events[1]["ticker"] == "B"
