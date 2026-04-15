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
async def test_get_trades(mock_auth):
    client = KalshiClient("https://api.example.com", mock_auth)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "trades": [
            {"yes_price_dollars": "0.52", "created_time": "2024-01-01T00:00:00Z"},
        ],
        "cursor": "",
    }
    mock_response.raise_for_status = MagicMock()

    client._http = AsyncMock()
    client._http.request = AsyncMock(return_value=mock_response)
    client._http.is_closed = False

    trades = await client.get_trades("TICKER-1")
    assert len(trades) == 1
    assert trades[0]["yes_price_dollars"] == "0.52"


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
