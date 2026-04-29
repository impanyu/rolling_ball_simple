import logging
from typing import Any

import httpx

from app.kalshi.auth import KalshiAuth

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiClient:
    def __init__(self, base_url: str, auth: KalshiAuth) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self._http: httpx.AsyncClient | None = None

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    async def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = self.auth.get_headers(method, f"/trade-api/v2{path}")
        http = await self._get_http()
        response = await http.request(method, url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def _paginate(
        self,
        method: str,
        path: str,
        collection_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        params = dict(params or {})
        while True:
            data = await self._request(method, path, params)
            items = data.get(collection_key, [])
            all_items.extend(items)
            cursor = data.get("cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        return all_items

    async def get_events(
        self,
        series_ticker: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 200}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        return await self._paginate("GET", "/events", "events", params)

    async def get_markets(
        self,
        event_ticker: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": 200}
        if event_ticker:
            params["event_ticker"] = event_ticker
        if status:
            params["status"] = status
        return await self._paginate("GET", "/markets", "markets", params)

    async def get_trades(
        self,
        ticker: str,
    ) -> list[dict[str, Any]]:
        """Fetch all trades for a market (paginated)."""
        return await self._paginate(
            "GET", "/markets/trades", "trades", {"ticker": ticker, "limit": 1000}
        )

    async def get_market(self, ticker: str) -> dict[str, Any]:
        """Fetch a single market by ticker."""
        return await self._request("GET", f"/markets/{ticker}")

    async def get_balance(self) -> dict[str, Any]:
        return await self._request("GET", "/portfolio/balance")

    async def get_positions(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/portfolio/positions")
        return data.get("market_positions", [])

    async def place_order(
        self,
        ticker: str,
        side: str,
        action: str,
        count: int,
        type: str = "market",
        yes_price: int | None = None,
        no_price: int | None = None,
    ) -> dict[str, Any]:
        """Place an order on Kalshi.
        side: 'yes' or 'no'
        action: 'buy' or 'sell'
        type: 'market' or 'limit'
        yes_price/no_price: in cents (1-99) for limit orders
        """
        body: dict[str, Any] = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "count": count,
            "type": type,
        }
        if yes_price is not None:
            body["yes_price"] = yes_price
        if no_price is not None:
            body["no_price"] = no_price

        url = f"{self.base_url}/portfolio/orders"
        headers = self.auth.get_headers("POST", "/trade-api/v2/portfolio/orders")
        http = await self._get_http()
        response = await http.post(url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()
