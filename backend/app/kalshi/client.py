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

    async def get_candlesticks(
        self,
        ticker: str,
        period_interval: int = 1,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"period_interval": period_interval}
        if start_ts:
            params["start_ts"] = start_ts
        if end_ts:
            params["end_ts"] = end_ts
        data = await self._request("GET", f"/markets/{ticker}/candlesticks", params)
        return data.get("candlesticks", [])
