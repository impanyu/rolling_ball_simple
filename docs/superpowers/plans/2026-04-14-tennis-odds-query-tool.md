# Tennis Match Odds Query Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web tool to query and visualize historical tennis match odds from Kalshi, with histogram display and cumulative probability interaction.

**Architecture:** Python FastAPI backend with SQLite for storage, APScheduler for daily Kalshi data fetching, Sackmann repos for player stats. React + Vite + Recharts frontend with 6 dual-range query filters and interactive histogram.

**Tech Stack:** Python 3.14, FastAPI, SQLite (aiosqlite), APScheduler, httpx, React 18, Vite, TypeScript, Recharts

---

## File Map

### Backend (`backend/`)

| File | Responsibility |
|---|---|
| `app/__init__.py` | Package marker |
| `app/main.py` | FastAPI app creation, scheduler setup, lifespan |
| `app/config.py` | Pydantic settings from `.env` |
| `app/database.py` | SQLite connection pool, table creation |
| `app/models.py` | Pydantic schemas for API request/response |
| `app/kalshi/__init__.py` | Package marker |
| `app/kalshi/auth.py` | RSA signing for Kalshi API |
| `app/kalshi/client.py` | Async REST client (events, markets, candlesticks) |
| `app/kalshi/fetcher.py` | Market discovery, candlestick fetch, extraction pipeline |
| `app/stats/__init__.py` | Package marker |
| `app/stats/sackmann.py` | Clone/update Sackmann repos, parse CSV data |
| `app/stats/player_stats.py` | Compute ranking + 3-month win rate per player per date |
| `app/routes/__init__.py` | Package marker |
| `app/routes/query.py` | `GET /api/query` endpoint |
| `requirements.txt` | Python dependencies |
| `.env.example` | Credential template |

### Frontend (`frontend/`)

| File | Responsibility |
|---|---|
| `src/App.tsx` | Root layout, wires QueryForm to Histogram |
| `src/api.ts` | `fetchQueryResults()` — calls backend API |
| `src/components/QueryForm.tsx` | 6 dual-range filter inputs + Search button |
| `src/components/Histogram.tsx` | Recharts bar chart + click-for-cumulative interaction |
| `src/types.ts` | TypeScript interfaces for API response |

### Root

| File | Responsibility |
|---|---|
| `start.sh` | One-command startup for backend + frontend |
| `.gitignore` | Ignore data/, secrets/, .env, node_modules, __pycache__ |

---

## Task 1: Project Scaffolding + .gitignore

**Files:**
- Create: `.gitignore`
- Create: `backend/requirements.txt`
- Create: `backend/.env.example`
- Create: `backend/app/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```
# Python
__pycache__/
*.pyc
*.egg-info/
.venv/

# Node
node_modules/
dist/

# Data & secrets
data/
secrets/
backend/.env

# IDE
.vscode/
.idea/

# OS
.DS_Store
```

- [ ] **Step 2: Create `backend/requirements.txt`**

```
fastapi==0.115.12
uvicorn[standard]==0.34.2
aiosqlite==0.21.0
httpx==0.28.1
cryptography==44.0.3
apscheduler==3.11.0
pydantic-settings==2.9.1
pandas==2.2.3
```

- [ ] **Step 3: Create `backend/.env.example`**

```
# Kalshi API
KALSHI_API_KEY_ID=your_key_id_here
KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi_private.pem

# Database
DB_PATH=./data/tennis_odds.db

# Scheduler (daily fetch time, 24h format)
FETCH_CRON_HOUR=3
FETCH_CRON_MINUTE=0

# Sackmann data directory
SACKMANN_DATA_DIR=./data/sackmann
```

- [ ] **Step 4: Create `backend/app/__init__.py`**

Empty file.

- [ ] **Step 5: Install backend dependencies**

Run: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend/requirements.txt backend/.env.example backend/app/__init__.py
git commit -m "chore: scaffold backend project with dependencies and config template"
```

---

## Task 2: Configuration Module

**Files:**
- Create: `backend/app/config.py`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/__init__.py` (empty) and `backend/tests/test_config.py`:

```python
import os
import pytest
from app.config import Settings


def test_settings_loads_defaults():
    os.environ.setdefault("KALSHI_API_KEY_ID", "test_key")
    os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
    s = Settings()
    assert s.db_path == "./data/tennis_odds.db"
    assert s.fetch_cron_hour == 3
    assert s.fetch_cron_minute == 0
    assert s.sackmann_data_dir == "./data/sackmann"


def test_settings_loads_env_overrides():
    os.environ["DB_PATH"] = "/tmp/test.db"
    os.environ["FETCH_CRON_HOUR"] = "5"
    os.environ.setdefault("KALSHI_API_KEY_ID", "test_key")
    os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
    s = Settings()
    assert s.db_path == "/tmp/test.db"
    assert s.fetch_cron_hour == 5
    # Cleanup
    del os.environ["DB_PATH"]
    del os.environ["FETCH_CRON_HOUR"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write implementation**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kalshi API
    kalshi_api_key_id: str = ""
    kalshi_private_key_path: str = "./secrets/kalshi_private.pem"

    # Database
    db_path: str = "./data/tennis_odds.db"

    # Scheduler
    fetch_cron_hour: int = 3
    fetch_cron_minute: int = 0

    # Sackmann
    sackmann_data_dir: str = "./data/sackmann"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/__init__.py backend/tests/test_config.py
git commit -m "feat: add configuration module with pydantic-settings"
```

---

## Task 3: Database Layer

**Files:**
- Create: `backend/app/database.py`
- Test: `backend/tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_database.py
import asyncio
import os
import pytest
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_tennis_odds.db"


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_init_db_creates_tables():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
    assert "raw_prices" in tables
    assert "extracted_data" in tables
    assert "player_stats" in tables


@pytest.mark.asyncio
async def test_raw_prices_columns():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(raw_prices)")
        columns = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "match_id", "player", "opponent", "tournament",
                "match_date", "minute", "price", "timestamp"}
    assert columns == expected


@pytest.mark.asyncio
async def test_extracted_data_columns():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("PRAGMA table_info(extracted_data)")
        columns = {row[1] for row in await cursor.fetchall()}
    expected = {"id", "match_id", "player", "opponent", "tournament",
                "match_date", "minute", "initial_price", "current_price",
                "max_price_after", "player_ranking", "opponent_ranking",
                "player_win_rate_3m", "opponent_win_rate_3m"}
    assert columns == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pip install pytest-asyncio && python3 -m pytest tests/test_database.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.database'`

- [ ] **Step 3: Write implementation**

```python
# backend/app/database.py
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

SQL_CREATE_RAW_PRICES = """
CREATE TABLE IF NOT EXISTS raw_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    player TEXT NOT NULL,
    opponent TEXT NOT NULL,
    tournament TEXT NOT NULL,
    match_date TEXT NOT NULL,
    minute INTEGER NOT NULL,
    price REAL NOT NULL,
    timestamp TEXT NOT NULL
)
"""

SQL_CREATE_EXTRACTED_DATA = """
CREATE TABLE IF NOT EXISTS extracted_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    player TEXT NOT NULL,
    opponent TEXT NOT NULL,
    tournament TEXT NOT NULL,
    match_date TEXT NOT NULL,
    minute INTEGER NOT NULL,
    initial_price REAL NOT NULL,
    current_price REAL NOT NULL,
    max_price_after REAL NOT NULL,
    player_ranking INTEGER,
    opponent_ranking INTEGER,
    player_win_rate_3m REAL,
    opponent_win_rate_3m REAL
)
"""

SQL_CREATE_PLAYER_STATS = """
CREATE TABLE IF NOT EXISTS player_stats (
    player_name TEXT NOT NULL,
    match_date TEXT NOT NULL,
    ranking INTEGER,
    win_rate_3m REAL,
    PRIMARY KEY (player_name, match_date)
)
"""

SQL_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_raw_match ON raw_prices(match_id)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_initial ON extracted_data(initial_price)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_current ON extracted_data(current_price)",
    "CREATE INDEX IF NOT EXISTS idx_extracted_max ON extracted_data(max_price_after)",
]


async def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(SQL_CREATE_RAW_PRICES)
        await db.execute(SQL_CREATE_EXTRACTED_DATA)
        await db.execute(SQL_CREATE_PLAYER_STATS)
        for idx_sql in SQL_CREATE_INDEXES:
            await db.execute(idx_sql)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: str):
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_database.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/database.py backend/tests/test_database.py
git commit -m "feat: add SQLite database layer with table creation"
```

---

## Task 4: Kalshi Auth Module

**Files:**
- Create: `backend/app/kalshi/__init__.py`
- Create: `backend/app/kalshi/auth.py`
- Test: `backend/tests/test_kalshi_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_kalshi_auth.py
import time
from unittest.mock import patch
from app.kalshi.auth import KalshiAuth


def test_get_headers_contains_required_keys(tmp_path):
    # Generate a test RSA key
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    auth = KalshiAuth(key_id="test_key_id", private_key_path=str(key_path))
    headers = auth.get_headers("GET", "/trade-api/v2/events")

    assert "KALSHI-ACCESS-KEY" in headers
    assert headers["KALSHI-ACCESS-KEY"] == "test_key_id"
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "Content-Type" in headers


def test_different_requests_produce_different_signatures(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    auth = KalshiAuth(key_id="test_key_id", private_key_path=str(key_path))
    headers1 = auth.get_headers("GET", "/trade-api/v2/events")
    headers2 = auth.get_headers("POST", "/trade-api/v2/orders")

    # RSA-PSS is randomized, so even same input gives different sigs,
    # but different input definitely gives different sigs
    assert headers1["KALSHI-ACCESS-SIGNATURE"] != headers2["KALSHI-ACCESS-SIGNATURE"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_kalshi_auth.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/kalshi/__init__.py` (empty).

```python
# backend/app/kalshi/auth.py
import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KalshiAuth:
    def __init__(self, key_id: str, private_key_path: str) -> None:
        self.key_id = key_id
        pem_bytes = Path(private_key_path).read_bytes()
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError(f"Expected RSA private key, got {type(key)}")
        self.private_key = key

    def get_headers(self, method: str, path: str) -> dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        message = (timestamp_ms + method + path).encode("utf-8")
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "Content-Type": "application/json",
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_kalshi_auth.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/kalshi/__init__.py backend/app/kalshi/auth.py backend/tests/test_kalshi_auth.py
git commit -m "feat: add Kalshi RSA auth module"
```

---

## Task 5: Kalshi REST Client

**Files:**
- Create: `backend/app/kalshi/client.py`
- Test: `backend/tests/test_kalshi_client.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_kalshi_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_kalshi_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/kalshi/client.py
import logging
from typing import Any

import httpx

from app.kalshi.auth import KalshiAuth

logger = logging.getLogger(__name__)

BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_kalshi_client.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/kalshi/client.py backend/tests/test_kalshi_client.py
git commit -m "feat: add Kalshi REST client with pagination"
```

---

## Task 6: Sackmann Data Parser

**Files:**
- Create: `backend/app/stats/__init__.py`
- Create: `backend/app/stats/sackmann.py`
- Test: `backend/tests/test_sackmann.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sackmann.py
import os
import pytest
import pandas as pd
from app.stats.sackmann import parse_rankings, parse_matches, normalize_name


def test_normalize_name():
    assert normalize_name("Roger", "Federer") == "roger federer"
    assert normalize_name("Rafael", "Nadal") == "rafael nadal"
    assert normalize_name("  Carlos ", " Alcaraz ") == "carlos alcaraz"


def test_parse_rankings(tmp_path):
    # Create a minimal rankings CSV
    csv_content = "ranking_date,rank,player\n20240101,1,104925\n20240101,2,106421\n"
    (tmp_path / "atp_rankings_current.csv").write_text(csv_content)

    players_content = "player_id,name_first,name_last\n104925,Novak,Djokovic\n106421,Carlos,Alcaraz\n"
    (tmp_path / "atp_players.csv").write_text(players_content)

    rankings = parse_rankings(str(tmp_path), tour="atp")
    assert len(rankings) == 2
    assert rankings.iloc[0]["player_name"] == "novak djokovic"
    assert rankings.iloc[0]["ranking"] == 1


def test_parse_matches(tmp_path):
    csv_content = (
        "tourney_id,tourney_name,tourney_date,winner_name,loser_name,score\n"
        "2024-001,Australian Open,20240115,Novak Djokovic,Carlos Alcaraz,6-3 6-4\n"
        "2024-001,Australian Open,20240116,Carlos Alcaraz,Daniil Medvedev,7-5 6-3\n"
    )
    (tmp_path / "atp_matches_2024.csv").write_text(csv_content)

    matches = parse_matches(str(tmp_path), tour="atp")
    assert len(matches) == 2
    assert matches.iloc[0]["winner_name"] == "novak djokovic"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_sackmann.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/stats/__init__.py` (empty).

```python
# backend/app/stats/sackmann.py
import logging
import subprocess
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

ATP_REPO = "https://github.com/JeffSackmann/tennis_atp.git"
WTA_REPO = "https://github.com/JeffSackmann/tennis_wta.git"


def normalize_name(first: str, last: str) -> str:
    return f"{first.strip()} {last.strip()}".lower()


def clone_or_update(repo_url: str, dest: str) -> None:
    dest_path = Path(dest)
    if dest_path.exists() and (dest_path / ".git").exists():
        logger.info(f"Updating {dest}")
        subprocess.run(["git", "pull"], cwd=dest, capture_output=True, check=True)
    else:
        logger.info(f"Cloning {repo_url} to {dest}")
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, dest],
            capture_output=True,
            check=True,
        )


def ensure_repos(sackmann_dir: str) -> None:
    clone_or_update(ATP_REPO, f"{sackmann_dir}/tennis_atp")
    clone_or_update(WTA_REPO, f"{sackmann_dir}/tennis_wta")


def parse_rankings(repo_dir: str, tour: str = "atp") -> pd.DataFrame:
    repo_path = Path(repo_dir)

    # Load player names
    players_file = repo_path / f"{tour}_players.csv"
    players = pd.read_csv(players_file, dtype={"player_id": str})
    name_map = {
        row["player_id"]: normalize_name(
            str(row.get("name_first", "")), str(row.get("name_last", ""))
        )
        for _, row in players.iterrows()
    }

    # Load all rankings files
    ranking_files = sorted(repo_path.glob(f"{tour}_rankings_*.csv"))
    frames = []
    for f in ranking_files:
        df = pd.read_csv(f, dtype={"player": str})
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["ranking_date", "ranking", "player_name"])

    rankings = pd.concat(frames, ignore_index=True)
    rankings["player_name"] = rankings["player"].map(name_map)
    rankings = rankings.dropna(subset=["player_name"])
    rankings["ranking_date"] = pd.to_datetime(
        rankings["ranking_date"], format="%Y%m%d"
    )
    rankings = rankings.rename(columns={"rank": "ranking"})
    return rankings[["ranking_date", "ranking", "player_name"]]


def parse_matches(repo_dir: str, tour: str = "atp") -> pd.DataFrame:
    repo_path = Path(repo_dir)
    match_files = sorted(repo_path.glob(f"{tour}_matches_*.csv"))
    frames = []
    for f in match_files:
        df = pd.read_csv(f, low_memory=False)
        frames.append(df)

    if not frames:
        return pd.DataFrame(
            columns=["tourney_date", "winner_name", "loser_name", "tourney_name"]
        )

    matches = pd.concat(frames, ignore_index=True)
    matches["winner_name"] = matches["winner_name"].str.lower().str.strip()
    matches["loser_name"] = matches["loser_name"].str.lower().str.strip()
    matches["tourney_date"] = pd.to_datetime(
        matches["tourney_date"], format="%Y%m%d"
    )
    return matches[["tourney_date", "winner_name", "loser_name", "tourney_name"]]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_sackmann.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/stats/__init__.py backend/app/stats/sackmann.py backend/tests/test_sackmann.py
git commit -m "feat: add Sackmann data parser for rankings and matches"
```

---

## Task 7: Player Stats Computation

**Files:**
- Create: `backend/app/stats/player_stats.py`
- Test: `backend/tests/test_player_stats.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_player_stats.py
import pytest
import pandas as pd
from datetime import datetime
from app.stats.player_stats import compute_ranking_at_date, compute_win_rate_3m


@pytest.fixture
def sample_rankings():
    return pd.DataFrame({
        "ranking_date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01"]),
        "ranking": [1, 2, 5],
        "player_name": ["novak djokovic", "novak djokovic", "carlos alcaraz"],
    })


@pytest.fixture
def sample_matches():
    return pd.DataFrame({
        "tourney_date": pd.to_datetime([
            "2024-01-10", "2024-01-12", "2024-01-15",
            "2024-02-01", "2024-02-05",
        ]),
        "winner_name": [
            "novak djokovic", "novak djokovic", "carlos alcaraz",
            "novak djokovic", "carlos alcaraz",
        ],
        "loser_name": [
            "carlos alcaraz", "daniil medvedev", "novak djokovic",
            "carlos alcaraz", "daniil medvedev",
        ],
        "tourney_name": ["AO"] * 5,
    })


def test_compute_ranking_at_date(sample_rankings):
    # On Jan 5, Djokovic's most recent ranking is from Jan 1 = rank 1
    rank = compute_ranking_at_date(sample_rankings, "novak djokovic", datetime(2024, 1, 5))
    assert rank == 1

    # On Jan 10, Djokovic's most recent ranking is from Jan 8 = rank 2
    rank = compute_ranking_at_date(sample_rankings, "novak djokovic", datetime(2024, 1, 10))
    assert rank == 2

    # Unknown player returns None
    rank = compute_ranking_at_date(sample_rankings, "unknown player", datetime(2024, 1, 5))
    assert rank is None


def test_compute_win_rate_3m(sample_matches):
    # On Feb 10, look back 90 days: Djokovic has 3 wins, 1 loss = 0.75
    rate = compute_win_rate_3m(sample_matches, "novak djokovic", datetime(2024, 2, 10))
    assert rate == pytest.approx(0.75)

    # Alcaraz has 2 wins, 2 losses = 0.5
    rate = compute_win_rate_3m(sample_matches, "carlos alcaraz", datetime(2024, 2, 10))
    assert rate == pytest.approx(0.5)

    # Unknown player returns None
    rate = compute_win_rate_3m(sample_matches, "unknown", datetime(2024, 2, 10))
    assert rate is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_player_stats.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/stats/player_stats.py
from datetime import datetime, timedelta

import pandas as pd


def compute_ranking_at_date(
    rankings: pd.DataFrame, player_name: str, match_date: datetime
) -> int | None:
    player_ranks = rankings[
        (rankings["player_name"] == player_name)
        & (rankings["ranking_date"] <= match_date)
    ]
    if player_ranks.empty:
        return None
    latest = player_ranks.loc[player_ranks["ranking_date"].idxmax()]
    return int(latest["ranking"])


def compute_win_rate_3m(
    matches: pd.DataFrame, player_name: str, match_date: datetime
) -> float | None:
    cutoff = match_date - timedelta(days=90)
    recent = matches[
        (matches["tourney_date"] >= cutoff) & (matches["tourney_date"] < match_date)
    ]
    wins = len(recent[recent["winner_name"] == player_name])
    losses = len(recent[recent["loser_name"] == player_name])
    total = wins + losses
    if total == 0:
        return None
    return wins / total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_player_stats.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/stats/player_stats.py backend/tests/test_player_stats.py
git commit -m "feat: add player ranking and win rate computation"
```

---

## Task 8: Data Extraction Logic

**Files:**
- Create: `backend/app/kalshi/fetcher.py`
- Test: `backend/tests/test_fetcher.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_fetcher.py
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

    # Insert raw price data for a match: 5 minutes of data
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

    # Check extracted data for Player A (YES side)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/kalshi/fetcher.py
import logging
from app.database import get_db

logger = logging.getLogger(__name__)


async def extract_match_data(
    db_path: str,
    match_id: str,
    player_stats: dict[str, dict],
) -> None:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT player, opponent, tournament, match_date, minute, price "
            "FROM raw_prices WHERE match_id = ? ORDER BY minute",
            (match_id,),
        )
        rows = await cursor.fetchall()

    if not rows:
        logger.warning(f"No raw data for {match_id}")
        return

    player = rows[0]["player"]
    opponent = rows[0]["opponent"]
    tournament = rows[0]["tournament"]
    match_date = rows[0]["match_date"]
    yes_prices = [(r["minute"], r["price"]) for r in rows]

    # Build data for both sides
    sides = [
        {
            "player": player,
            "opponent": opponent,
            "prices": [(m, p) for m, p in yes_prices],
        },
        {
            "player": opponent,
            "opponent": player,
            "prices": [(m, 100 - p) for m, p in yes_prices],
        },
    ]

    async with get_db(db_path) as db:
        for side in sides:
            prices = side["prices"]
            initial_price = prices[0][1]
            p_name = side["player"].lower()
            o_name = side["opponent"].lower()

            p_stats = player_stats.get(p_name, {})
            o_stats = player_stats.get(o_name, {})

            for i, (minute, current_price) in enumerate(prices):
                max_price_after = max(p for _, p in prices[i:])

                await db.execute(
                    "INSERT INTO extracted_data "
                    "(match_id, player, opponent, tournament, match_date, minute, "
                    "initial_price, current_price, max_price_after, "
                    "player_ranking, opponent_ranking, player_win_rate_3m, opponent_win_rate_3m) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        match_id,
                        side["player"],
                        side["opponent"],
                        tournament,
                        match_date,
                        minute,
                        initial_price,
                        current_price,
                        max_price_after,
                        p_stats.get("ranking"),
                        o_stats.get("ranking"),
                        p_stats.get("win_rate_3m"),
                        o_stats.get("win_rate_3m"),
                    ),
                )
        await db.commit()

    logger.info(f"Extracted data for {match_id}: {len(yes_prices)} minutes x 2 sides")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_fetcher.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/kalshi/fetcher.py backend/tests/test_fetcher.py
git commit -m "feat: add match data extraction logic (raw -> extracted)"
```

---

## Task 9: API Models

**Files:**
- Create: `backend/app/models.py`

- [ ] **Step 1: Create Pydantic models**

```python
# backend/app/models.py
from pydantic import BaseModel


class QueryParams(BaseModel):
    initial_price_min: float | None = None
    initial_price_max: float | None = None
    current_price_min: float | None = None
    current_price_max: float | None = None
    player_ranking_min: int | None = None
    player_ranking_max: int | None = None
    opponent_ranking_min: int | None = None
    opponent_ranking_max: int | None = None
    player_win_rate_3m_min: float | None = None
    player_win_rate_3m_max: float | None = None
    opponent_win_rate_3m_min: float | None = None
    opponent_win_rate_3m_max: float | None = None


class HistogramBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int
    percentage: float


class Stats(BaseModel):
    mean: float
    median: float
    std: float


class QueryResponse(BaseModel):
    total_count: int
    histogram: list[HistogramBin]
    stats: Stats
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add Pydantic models for query API"
```

---

## Task 10: Query API Endpoint

**Files:**
- Create: `backend/app/routes/__init__.py`
- Create: `backend/app/routes/query.py`
- Test: `backend/tests/test_query.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_query.py
import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_query.db"


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db(DB_TEST_PATH)
    async with get_db(DB_TEST_PATH) as db:
        # Insert 20 extracted data points with varying prices
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
                    50.0,           # initial_price
                    30.0 + i,       # current_price: 30-49
                    40.0 + i * 3,   # max_price_after: 40-97
                    5,              # player_ranking
                    10,             # opponent_ranking
                    0.7,            # player_win_rate_3m
                    0.5,            # opponent_win_rate_3m
                ),
            )
        await db.commit()
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.fixture
def app():
    os.environ["DB_PATH"] = DB_TEST_PATH
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
    assert len(data["histogram"]) == 20  # bins from 0-100 in steps of 5
    assert "mean" in data["stats"]


@pytest.mark.asyncio
async def test_query_with_price_filter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query?initial_price_min=45&initial_price_max=55")
    assert resp.status_code == 200
    data = resp.json()
    # All rows have initial_price=50 which is in [45,55]
    assert data["total_count"] == 20


@pytest.mark.asyncio
async def test_query_with_ranking_filter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/query?player_ranking_min=1&player_ranking_max=3")
    assert resp.status_code == 200
    data = resp.json()
    # All rows have player_ranking=5, which is outside [1,3]
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_query.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/routes/__init__.py` (empty).

```python
# backend/app/routes/query.py
import statistics
from fastapi import APIRouter, Query
from app.config import settings
from app.database import get_db
from app.models import QueryResponse, HistogramBin, Stats

router = APIRouter()


@router.get("/api/query", response_model=QueryResponse)
async def query_data(
    initial_price_min: float | None = Query(None),
    initial_price_max: float | None = Query(None),
    current_price_min: float | None = Query(None),
    current_price_max: float | None = Query(None),
    player_ranking_min: int | None = Query(None),
    player_ranking_max: int | None = Query(None),
    opponent_ranking_min: int | None = Query(None),
    opponent_ranking_max: int | None = Query(None),
    player_win_rate_3m_min: float | None = Query(None),
    player_win_rate_3m_max: float | None = Query(None),
    opponent_win_rate_3m_min: float | None = Query(None),
    opponent_win_rate_3m_max: float | None = Query(None),
):
    conditions = []
    params: list = []

    filters = [
        ("initial_price", initial_price_min, initial_price_max),
        ("current_price", current_price_min, current_price_max),
        ("player_ranking", player_ranking_min, player_ranking_max),
        ("opponent_ranking", opponent_ranking_min, opponent_ranking_max),
        ("player_win_rate_3m", player_win_rate_3m_min, player_win_rate_3m_max),
        ("opponent_win_rate_3m", opponent_win_rate_3m_min, opponent_win_rate_3m_max),
    ]

    for col, min_val, max_val in filters:
        if min_val is not None:
            conditions.append(f"{col} >= ?")
            params.append(min_val)
        if max_val is not None:
            conditions.append(f"{col} <= ?")
            params.append(max_val)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT max_price_after FROM extracted_data {where_clause}"

    async with get_db(settings.db_path) as db:
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()

    values = [row[0] for row in rows]
    total_count = len(values)

    # Build histogram: 20 bins of 5 cents each (0-5, 5-10, ..., 95-100)
    bin_size = 5
    histogram = []
    for bin_start in range(0, 100, bin_size):
        bin_end = bin_start + bin_size
        count = sum(1 for v in values if bin_start <= v < bin_end)
        # Last bin includes 100
        if bin_start == 95:
            count = sum(1 for v in values if bin_start <= v <= bin_end)
        pct = (count / total_count * 100) if total_count > 0 else 0
        histogram.append(
            HistogramBin(
                bin_start=bin_start,
                bin_end=bin_end,
                count=count,
                percentage=round(pct, 2),
            )
        )

    if total_count > 0:
        stats = Stats(
            mean=round(statistics.mean(values), 2),
            median=round(statistics.median(values), 2),
            std=round(statistics.stdev(values), 2) if total_count > 1 else 0,
        )
    else:
        stats = Stats(mean=0, median=0, std=0)

    return QueryResponse(
        total_count=total_count,
        histogram=histogram,
        stats=stats,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_query.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/__init__.py backend/app/routes/query.py backend/app/models.py backend/tests/test_query.py
git commit -m "feat: add query API endpoint with 6 dual-range filters and histogram"
```

---

## Task 11: FastAPI App + Scheduler

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_main.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main.py
import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("KALSHI_API_KEY_ID", "test")
os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")
os.environ["DB_PATH"] = "/tmp/test_main.db"

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes.query import router as query_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def scheduled_fetch():
    """Daily job: discover new matches, fetch candlesticks, extract data."""
    logger.info("Starting scheduled data fetch...")
    # Import here to avoid circular imports and allow running without Kalshi credentials
    try:
        from app.kalshi.auth import KalshiAuth
        from app.kalshi.client import KalshiClient
        from app.kalshi.fetcher import run_full_pipeline
        from app.stats.sackmann import ensure_repos

        ensure_repos(settings.sackmann_data_dir)
        auth = KalshiAuth(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
        client = KalshiClient("https://trading-api.kalshi.com/trade-api/v2", auth)
        await run_full_pipeline(client, settings.db_path, settings.sackmann_data_dir)
        await client.close()
        logger.info("Scheduled fetch complete.")
    except Exception as e:
        logger.error(f"Scheduled fetch failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.db_path)
    logger.info("Database initialized.")

    if settings.kalshi_api_key_id:
        scheduler.add_job(
            scheduled_fetch,
            "cron",
            hour=settings.fetch_cron_hour,
            minute=settings.fetch_cron_minute,
            id="daily_fetch",
        )
        scheduler.start()
        logger.info(
            f"Scheduler started: daily fetch at {settings.fetch_cron_hour:02d}:{settings.fetch_cron_minute:02d}"
        )
    else:
        logger.warning("No Kalshi API key configured. Scheduler not started.")

    yield

    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(title="Tennis Odds Query Tool", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_main.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_main.py
git commit -m "feat: add FastAPI app with lifespan, scheduler, and health endpoint"
```

---

## Task 12: Full Pipeline (Market Discovery + Fetch + Extract)

**Files:**
- Modify: `backend/app/kalshi/fetcher.py` (add `run_full_pipeline`)
- Test: `backend/tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pipeline.py
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.kalshi.fetcher import run_full_pipeline
from app.database import init_db, get_db

DB_TEST_PATH = "/tmp/test_pipeline.db"


@pytest.fixture(autouse=True)
def cleanup():
    yield
    if os.path.exists(DB_TEST_PATH):
        os.remove(DB_TEST_PATH)


@pytest.mark.asyncio
async def test_run_full_pipeline():
    await init_db(DB_TEST_PATH)

    mock_client = AsyncMock()

    # Mock: discover 1 settled event with 1 market
    mock_client.get_events.return_value = [
        {
            "event_ticker": "EVT1",
            "title": "Match: Djokovic vs Alcaraz",
            "category": "tennis",
        }
    ]
    mock_client.get_markets.return_value = [
        {
            "ticker": "MKT1",
            "event_ticker": "EVT1",
            "title": "Djokovic to win",
            "subtitle": "Novak Djokovic vs Carlos Alcaraz",
            "status": "finalized",
            "open_time": "2024-03-01T10:00:00Z",
            "close_time": "2024-03-01T12:00:00Z",
            "yes_sub_title": "Novak Djokovic",
            "no_sub_title": "Carlos Alcaraz",
        }
    ]

    # Mock: 3 candlesticks
    mock_client.get_candlesticks.return_value = [
        {"t": 1709290800, "open": 60, "high": 65, "low": 58, "close": 62, "volume": 100},
        {"t": 1709290860, "open": 62, "high": 70, "low": 60, "close": 55, "volume": 80},
        {"t": 1709290920, "open": 55, "high": 75, "low": 50, "close": 75, "volume": 120},
    ]

    with patch("app.kalshi.fetcher.get_player_stats_for_match", return_value={}):
        await run_full_pipeline(mock_client, DB_TEST_PATH, "/tmp/sackmann_test")

    # Verify raw_prices were inserted
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM raw_prices")
        raw_count = (await cursor.fetchone())[0]
        assert raw_count == 3

    # Verify extracted_data for both sides
    async with get_db(DB_TEST_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM extracted_data")
        ext_count = (await cursor.fetchone())[0]
        assert ext_count == 6  # 3 minutes x 2 sides
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python3 -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_full_pipeline'`

- [ ] **Step 3: Add `run_full_pipeline` and `get_player_stats_for_match` to fetcher.py**

Append to `backend/app/kalshi/fetcher.py`:

```python
# Add these imports at the top of the file
import re
from datetime import datetime
from app.stats.sackmann import parse_rankings, parse_matches, ensure_repos
from app.stats.player_stats import compute_ranking_at_date, compute_win_rate_3m

# Tennis series tickers to search for
TENNIS_SERIES = ["KXATPMATCH", "KXWTAMATCH"]


def parse_player_names(market: dict) -> tuple[str, str]:
    yes_player = market.get("yes_sub_title", "")
    no_player = market.get("no_sub_title", "")
    if not yes_player or not no_player:
        title = market.get("subtitle", market.get("title", ""))
        parts = re.split(r"\s+vs\.?\s+", title, flags=re.IGNORECASE)
        if len(parts) == 2:
            yes_player, no_player = parts[0].strip(), parts[1].strip()
    return yes_player, no_player


def get_player_stats_for_match(
    sackmann_dir: str, player: str, opponent: str, match_date_str: str
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    match_date = datetime.strptime(match_date_str, "%Y-%m-%d")

    for tour in ["atp", "wta"]:
        try:
            repo_dir = f"{sackmann_dir}/tennis_{tour}"
            rankings = parse_rankings(repo_dir, tour)
            matches = parse_matches(repo_dir, tour)

            for name in [player.lower(), opponent.lower()]:
                if name in result:
                    continue
                ranking = compute_ranking_at_date(rankings, name, match_date)
                win_rate = compute_win_rate_3m(matches, name, match_date)
                if ranking is not None or win_rate is not None:
                    result[name] = {
                        "ranking": ranking,
                        "win_rate_3m": win_rate,
                    }
        except Exception:
            continue

    return result


async def run_full_pipeline(client, db_path: str, sackmann_dir: str) -> None:
    # 1. Discover tennis markets
    all_markets = []
    for series in TENNIS_SERIES:
        try:
            events = await client.get_events(series_ticker=series)
            for event in events:
                markets = await client.get_markets(
                    event_ticker=event["event_ticker"], status="finalized"
                )
                all_markets.extend(markets)
        except Exception as e:
            logger.warning(f"Failed to fetch series {series}: {e}")

    # 2. Filter out already-processed matches
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT DISTINCT match_id FROM raw_prices")
        existing = {row[0] for row in await cursor.fetchall()}

    new_markets = [m for m in all_markets if m["ticker"] not in existing]
    logger.info(f"Found {len(new_markets)} new settled markets to process")

    # 3. Fetch + store + extract each market
    for market in new_markets:
        ticker = market["ticker"]
        player, opponent = parse_player_names(market)
        if not player or not opponent:
            logger.warning(f"Cannot parse player names from {ticker}, skipping")
            continue

        tournament = market.get("event_ticker", "Unknown")
        open_time = market.get("open_time", "")
        match_date = open_time[:10] if open_time else "unknown"

        try:
            candles = await client.get_candlesticks(ticker)
        except Exception as e:
            logger.error(f"Failed to fetch candlesticks for {ticker}: {e}")
            continue

        if not candles:
            continue

        # Store raw prices
        async with get_db(db_path) as db:
            for i, candle in enumerate(candles):
                ts = candle.get("t", 0)
                price = candle.get("close", candle.get("open", 0))
                await db.execute(
                    "INSERT INTO raw_prices "
                    "(match_id, player, opponent, tournament, match_date, minute, price, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (ticker, player, opponent, tournament, match_date, i, price,
                     datetime.utcfromtimestamp(ts).isoformat() + "Z" if ts else ""),
                )
            await db.commit()

        # Get player stats
        player_stats = get_player_stats_for_match(
            sackmann_dir, player, opponent, match_date
        )

        # Extract data
        await extract_match_data(db_path, ticker, player_stats)
        logger.info(f"Processed {ticker}: {player} vs {opponent}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python3 -m pytest tests/test_pipeline.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/kalshi/fetcher.py backend/tests/test_pipeline.py
git commit -m "feat: add full pipeline - market discovery, fetch, extract"
```

---

## Task 13: Frontend Scaffolding

**Files:**
- Create: `frontend/` (Vite + React + TypeScript project)

- [ ] **Step 1: Scaffold Vite project**

```bash
cd /Users/ypan12/git_repo/rolling_ball_simple
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install recharts
```

- [ ] **Step 2: Create `frontend/src/types.ts`**

```typescript
// frontend/src/types.ts
export interface HistogramBin {
    bin_start: number;
    bin_end: number;
    count: number;
    percentage: number;
}

export interface Stats {
    mean: number;
    median: number;
    std: number;
}

export interface QueryResponse {
    total_count: number;
    histogram: HistogramBin[];
    stats: Stats;
}

export interface QueryFilters {
    initial_price_min?: number;
    initial_price_max?: number;
    current_price_min?: number;
    current_price_max?: number;
    player_ranking_min?: number;
    player_ranking_max?: number;
    opponent_ranking_min?: number;
    opponent_ranking_max?: number;
    player_win_rate_3m_min?: number;
    player_win_rate_3m_max?: number;
    opponent_win_rate_3m_min?: number;
    opponent_win_rate_3m_max?: number;
}
```

- [ ] **Step 3: Create `frontend/src/api.ts`**

```typescript
// frontend/src/api.ts
import { QueryFilters, QueryResponse } from "./types";

export async function fetchQueryResults(
    filters: QueryFilters
): Promise<QueryResponse> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== null && value !== "") {
            params.set(key, String(value));
        }
    }
    const resp = await fetch(`/api/query?${params.toString()}`);
    if (!resp.ok) {
        throw new Error(`Query failed: ${resp.status}`);
    }
    return resp.json();
}
```

- [ ] **Step 4: Configure Vite proxy**

Replace `frontend/vite.config.ts`:

```typescript
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: {
        port: 3000,
        proxy: {
            "/api": {
                target: "http://localhost:8000",
                changeOrigin: true,
            },
        },
    },
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/vite.config.ts frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/index.html frontend/src/main.tsx frontend/src/vite-env.d.ts frontend/eslint.config.js
git commit -m "feat: scaffold React frontend with types, API client, and Vite proxy"
```

---

## Task 14: QueryForm Component

**Files:**
- Create: `frontend/src/components/QueryForm.tsx`

- [ ] **Step 1: Create QueryForm component**

```tsx
// frontend/src/components/QueryForm.tsx
import { useState } from "react";
import { QueryFilters } from "../types";

interface Props {
    onSearch: (filters: QueryFilters) => void;
    loading: boolean;
}

interface RangeInputProps {
    label: string;
    minKey: keyof QueryFilters;
    maxKey: keyof QueryFilters;
    filters: QueryFilters;
    onChange: (key: keyof QueryFilters, value: string) => void;
    step?: number;
    placeholder?: [string, string];
}

function RangeInput({
    label,
    minKey,
    maxKey,
    filters,
    onChange,
    step = 1,
    placeholder = ["Min", "Max"],
}: RangeInputProps) {
    return (
        <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>
                {label}
            </label>
            <div style={{ display: "flex", gap: 8 }}>
                <input
                    type="number"
                    step={step}
                    placeholder={placeholder[0]}
                    value={filters[minKey] ?? ""}
                    onChange={(e) => onChange(minKey, e.target.value)}
                    style={{ width: 100, padding: "4px 8px" }}
                />
                <span style={{ alignSelf: "center" }}>to</span>
                <input
                    type="number"
                    step={step}
                    placeholder={placeholder[1]}
                    value={filters[maxKey] ?? ""}
                    onChange={(e) => onChange(maxKey, e.target.value)}
                    style={{ width: 100, padding: "4px 8px" }}
                />
            </div>
        </div>
    );
}

export default function QueryForm({ onSearch, loading }: Props) {
    const [filters, setFilters] = useState<QueryFilters>({});

    const handleChange = (key: keyof QueryFilters, value: string) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value === "" ? undefined : Number(value),
        }));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSearch(filters);
    };

    return (
        <form onSubmit={handleSubmit} style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>Query Filters</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <RangeInput
                    label="Initial Price (cents)"
                    minKey="initial_price_min"
                    maxKey="initial_price_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["0", "99"]}
                />
                <RangeInput
                    label="Current Price (cents)"
                    minKey="current_price_min"
                    maxKey="current_price_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["0", "99"]}
                />
                <RangeInput
                    label="Player Ranking"
                    minKey="player_ranking_min"
                    maxKey="player_ranking_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["1", "500"]}
                />
                <RangeInput
                    label="Opponent Ranking"
                    minKey="opponent_ranking_min"
                    maxKey="opponent_ranking_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["1", "500"]}
                />
                <RangeInput
                    label="Player Win Rate (3 months)"
                    minKey="player_win_rate_3m_min"
                    maxKey="player_win_rate_3m_max"
                    filters={filters}
                    onChange={handleChange}
                    step={0.01}
                    placeholder={["0.0", "1.0"]}
                />
                <RangeInput
                    label="Opponent Win Rate (3 months)"
                    minKey="opponent_win_rate_3m_min"
                    maxKey="opponent_win_rate_3m_max"
                    filters={filters}
                    onChange={handleChange}
                    step={0.01}
                    placeholder={["0.0", "1.0"]}
                />
            </div>
            <button
                type="submit"
                disabled={loading}
                style={{
                    marginTop: 16,
                    padding: "8px 24px",
                    fontSize: 16,
                    cursor: loading ? "not-allowed" : "pointer",
                }}
            >
                {loading ? "Searching..." : "Search"}
            </button>
        </form>
    );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/QueryForm.tsx
git commit -m "feat: add QueryForm component with 6 dual-range filter inputs"
```

---

## Task 15: Histogram Component

**Files:**
- Create: `frontend/src/components/Histogram.tsx`

- [ ] **Step 1: Create Histogram component**

```tsx
// frontend/src/components/Histogram.tsx
import { useState } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
} from "recharts";
import { QueryResponse, HistogramBin } from "../types";

interface Props {
    data: QueryResponse | null;
}

export default function Histogram({ data }: Props) {
    const [selectedBin, setSelectedBin] = useState<HistogramBin | null>(null);
    const [cumulativePercent, setCumulativePercent] = useState<number | null>(null);

    if (!data) {
        return <p style={{ textAlign: "center", color: "#888" }}>Run a query to see results.</p>;
    }

    if (data.total_count === 0) {
        return <p style={{ textAlign: "center", color: "#888" }}>No data points match your filters.</p>;
    }

    const chartData = data.histogram.map((bin) => ({
        name: `${bin.bin_start}`,
        percentage: bin.percentage,
        count: bin.count,
        bin_start: bin.bin_start,
        bin_end: bin.bin_end,
    }));

    const handleBarClick = (entry: any) => {
        const clickedStart = entry.bin_start;
        setSelectedBin(entry);
        // Calculate cumulative percentage: sum of all bins with bin_start >= clickedStart
        const cumPct = data.histogram
            .filter((b) => b.bin_start >= clickedStart)
            .reduce((sum, b) => sum + b.percentage, 0);
        setCumulativePercent(Math.round(cumPct * 100) / 100);
    };

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>
                Max Price After — Distribution ({data.total_count.toLocaleString()} data points)
            </h2>

            <ResponsiveContainer width="100%" height={400}>
                <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="name"
                        label={{ value: "Max Price After (cents)", position: "insideBottom", offset: -15 }}
                    />
                    <YAxis
                        label={{ value: "Percentage (%)", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value: number, name: string) => [
                            name === "percentage" ? `${value}%` : value,
                            name === "percentage" ? "Percentage" : "Count",
                        ]}
                        labelFormatter={(label) => `Bin: ${label}-${Number(label) + 5} cents`}
                    />
                    <Bar
                        dataKey="percentage"
                        cursor="pointer"
                        onClick={(_, index) => handleBarClick(chartData[index])}
                    >
                        {chartData.map((entry, index) => (
                            <Cell
                                key={index}
                                fill={
                                    selectedBin && entry.bin_start >= selectedBin.bin_start
                                        ? "#e74c3c"
                                        : "#3498db"
                                }
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>

            {selectedBin && cumulativePercent !== null && (
                <div
                    style={{
                        marginTop: 12,
                        padding: 12,
                        background: "#fef3f3",
                        borderRadius: 6,
                        border: "1px solid #e74c3c",
                    }}
                >
                    <strong>
                        Cumulative: {cumulativePercent}% of data points have max_price_after
                        &ge; {selectedBin.bin_start} cents
                    </strong>
                </div>
            )}

            <div style={{ marginTop: 16, display: "flex", gap: 32 }}>
                <div><strong>Mean:</strong> {data.stats.mean} cents</div>
                <div><strong>Median:</strong> {data.stats.median} cents</div>
                <div><strong>Std Dev:</strong> {data.stats.std} cents</div>
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Histogram.tsx
git commit -m "feat: add Histogram component with clickable bars and cumulative percentage"
```

---

## Task 16: App Integration

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Replace App.tsx**

```tsx
// frontend/src/App.tsx
import { useState } from "react";
import QueryForm from "./components/QueryForm";
import Histogram from "./components/Histogram";
import { fetchQueryResults } from "./api";
import { QueryFilters, QueryResponse } from "./types";

function App() {
    const [data, setData] = useState<QueryResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (filters: QueryFilters) => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchQueryResults(filters);
            setData(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Query failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ maxWidth: 900, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
            <h1>Tennis Match Odds Query Tool</h1>
            <QueryForm onSearch={handleSearch} loading={loading} />
            {error && (
                <div style={{ marginTop: 16, padding: 12, background: "#fee", borderRadius: 6, color: "#c00" }}>
                    {error}
                </div>
            )}
            <div style={{ marginTop: 20 }}>
                <Histogram data={data} />
            </div>
        </div>
    );
}

export default App;
```

- [ ] **Step 2: Clean up default styles**

Replace `frontend/src/index.css`:

```css
/* frontend/src/index.css */
body {
    margin: 0;
    background: #f5f5f5;
    color: #333;
}

input, button {
    border: 1px solid #ccc;
    border-radius: 4px;
}

button:hover:not(:disabled) {
    background: #3498db;
    color: white;
    border-color: #3498db;
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/index.css
git commit -m "feat: integrate QueryForm and Histogram in App"
```

---

## Task 17: Start Script

**Files:**
- Create: `start.sh`

- [ ] **Step 1: Create start script**

```bash
#!/usr/bin/env bash
set -e

echo "=== Tennis Odds Query Tool ==="

# Start backend
echo "Starting backend on port 8000..."
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend on port 3000..."
cd "$(dirname "$0")/frontend"

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
```

- [ ] **Step 2: Make executable**

```bash
chmod +x start.sh
```

- [ ] **Step 3: Commit**

```bash
git add start.sh
git commit -m "feat: add one-command start script for both backend and frontend"
```

---

## Task 18: Manual Fetch Script

**Files:**
- Create: `backend/scripts/fetch_now.py`

This lets users trigger a data fetch without waiting for the cron schedule — useful for initial setup and testing.

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Manually trigger a full data fetch from Kalshi + Sackmann.

Usage: python3 -m scripts.fetch_now
"""
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.database import init_db
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient
from app.kalshi.fetcher import run_full_pipeline
from app.stats.sackmann import ensure_repos

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if not settings.kalshi_api_key_id:
        logger.error("KALSHI_API_KEY_ID not set in .env — cannot fetch data")
        sys.exit(1)

    await init_db(settings.db_path)
    ensure_repos(settings.sackmann_data_dir)

    auth = KalshiAuth(settings.kalshi_api_key_id, settings.kalshi_private_key_path)
    client = KalshiClient("https://trading-api.kalshi.com/trade-api/v2", auth)

    try:
        await run_full_pipeline(client, settings.db_path, settings.sackmann_data_dir)
        logger.info("Done!")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/fetch_now.py
git commit -m "feat: add manual fetch script for on-demand data pull"
```

---

## Task 19: End-to-End Smoke Test

**Files:**
- Test: `backend/tests/test_e2e.py`

- [ ] **Step 1: Write the smoke test**

```python
# backend/tests/test_e2e.py
"""End-to-end test: insert data, query API, verify histogram."""
import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.database import init_db, get_db
from app.kalshi.fetcher import extract_match_data

DB_TEST_PATH = "/tmp/test_e2e.db"

os.environ["DB_PATH"] = DB_TEST_PATH
os.environ.setdefault("KALSHI_API_KEY_ID", "")
os.environ.setdefault("KALSHI_PRIVATE_KEY_PATH", "./secrets/test.pem")


@pytest.fixture(autouse=True)
async def setup():
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

        # Filter by initial price range that excludes some
        resp = await client.get("/api/query?initial_price_min=50&initial_price_max=60")
        data = resp.json()
        # Alice initial=55 (in range), Bob initial=100-55=45 (out of range)
        assert data["total_count"] == 10

        # Verify histogram structure
        assert len(data["histogram"]) == 20
        total_pct = sum(b["percentage"] for b in data["histogram"])
        assert abs(total_pct - 100.0) < 0.1
```

- [ ] **Step 2: Run the full test suite**

Run: `cd backend && python3 -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_e2e.py
git commit -m "test: add end-to-end smoke test for full data flow"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Project scaffolding, dependencies, .gitignore | - |
| 2 | Configuration (pydantic-settings) | 2 tests |
| 3 | Database layer (SQLite tables) | 3 tests |
| 4 | Kalshi RSA auth | 2 tests |
| 5 | Kalshi REST client | 3 tests |
| 6 | Sackmann data parser | 3 tests |
| 7 | Player stats computation | 5 tests |
| 8 | Data extraction logic | 2 tests |
| 9 | Pydantic API models | - |
| 10 | Query API endpoint | 4 tests |
| 11 | FastAPI app + scheduler | 2 tests |
| 12 | Full pipeline (discovery + fetch + extract) | 1 test |
| 13 | Frontend scaffolding (Vite + types + API) | - |
| 14 | QueryForm component | - |
| 15 | Histogram component | - |
| 16 | App integration | - |
| 17 | Start script | - |
| 18 | Manual fetch script | - |
| 19 | End-to-end smoke test | 1 test |
