# Tennis Match Odds Query Tool — Design Spec

## 1. Overview

A web-based tool for querying and visualizing historical tennis match odds data from Kalshi. Users can filter by match conditions and view the distribution of maximum price recovery after a given moment in a match.

**Future direction**: This tool may be upgraded into an AI agent for automated live betting.

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python + FastAPI | Lightweight, async, good for future AI/ML extension |
| Frontend | React + Vite + Recharts | Fast build, good chart interactivity |
| Database | SQLite | Zero config, single file, easy migration to PostgreSQL |
| Scheduler | APScheduler | Periodic data fetching within the FastAPI process |
| Data source | Kalshi REST API | MVP; architecture abstracts data source for future expansion (Betfair, etc.) |
| Player stats | Jeff Sackmann tennis repos | Rankings + match results for win rate calculation |

---

## 3. Project Structure

```
rolling_ball_simple/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point + scheduler setup
│   │   ├── config.py            # Settings (Kalshi credentials, DB path, fetch interval)
│   │   ├── database.py          # SQLite connection + table init
│   │   ├── models.py            # Table definitions (raw_prices, extracted_data, player_stats)
│   │   ├── kalshi/
│   │   │   ├── auth.py          # RSA signing for Kalshi API
│   │   │   ├── client.py        # REST API client (events, markets, candlesticks)
│   │   │   └── fetcher.py       # Scheduled fetch + data extraction logic
│   │   ├── stats/
│   │   │   ├── sackmann.py      # Clone/update Sackmann repos, parse rankings + results
│   │   │   └── player_stats.py  # Compute ranking + 3-month win rate per player per match
│   │   └── routes/
│   │       └── query.py         # Query API endpoint
│   ├── requirements.txt
│   ├── .env.example             # Credential template
│   └── .env                     # Actual credentials (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── QueryForm.tsx    # 6 dual-range filter inputs
│   │   │   └── Histogram.tsx    # Chart + click interaction
│   │   └── api.ts               # Backend API calls
│   ├── package.json
│   └── vite.config.ts
├── data/                        # SQLite DB + Sackmann repos (gitignored)
├── secrets/                     # RSA key (gitignored)
├── start.sh                     # One-command startup for both frontend + backend
└── README.md
```

---

## 4. Data Model

### 4.1 `raw_prices` — Raw candlestick data from Kalshi

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| match_id | TEXT | Kalshi market ticker |
| player | TEXT | Player name (the YES side of the contract) |
| opponent | TEXT | Opponent name |
| tournament | TEXT | Tournament name |
| match_date | TEXT | Match date (YYYY-MM-DD) |
| minute | INTEGER | Minutes since match start |
| price | REAL | YES contract price in cents (0-99) |
| timestamp | TEXT | Original UTC timestamp |

### 4.2 `player_stats` — Rankings and win rates from Sackmann data

| Column | Type | Description |
|---|---|---|
| player_name | TEXT | Standardized player name |
| match_date | TEXT | Date of the match |
| ranking | INTEGER | Player ranking at that time |
| win_rate_3m | REAL | Win rate over prior 3 months (0.0–1.0) |

### 4.3 `extracted_data` — Processed data points for querying

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| match_id | TEXT | Kalshi market ticker |
| player | TEXT | Player name |
| opponent | TEXT | Opponent name |
| tournament | TEXT | Tournament name |
| match_date | TEXT | Match date |
| minute | INTEGER | Minute of this data point |
| initial_price | REAL | Contract price just before match start |
| current_price | REAL | Contract price at this minute |
| max_price_after | REAL | Max contract price from this minute to match end |
| player_ranking | INTEGER | Player's ranking at match time |
| opponent_ranking | INTEGER | Opponent's ranking at match time |
| player_win_rate_3m | REAL | Player's 3-month win rate |
| opponent_win_rate_3m | REAL | Opponent's 3-month win rate |

Each match produces data points for **both** players independently:
- Player A: uses YES contract price directly
- Player B: uses `100 - YES price` (the NO side)

---

## 5. Data Pipeline

### 5.1 Kalshi Data Fetching

**Scheduled task**: Runs once per day (default: 3:00 AM local time, configurable via `.env`).

Each execution:

1. **Market Discovery**: Call `GET /events` and `GET /markets` filtered by tennis series tickers (e.g., `KXATPMATCH`, `KXWTAMATCH`, Grand Slam series). Maintain an internal index of all known tennis markets.

2. **Fetch settled matches**: For matches that are settled but not yet in `raw_prices`, fetch full 1-minute candlestick data via `GET /markets/{ticker}/candlesticks?period_interval=1`. Store each minute's data as a row in `raw_prices`.

3. **Extract data points**: For newly fetched settled matches, run the extraction logic (§5.3) and populate `extracted_data`.

### 5.2 Player Stats (Sackmann)

On first run (or when data is stale):

1. Clone `JeffSackmann/tennis_atp` and `JeffSackmann/tennis_wta` into `data/sackmann/`
2. On subsequent runs, `git pull` to update
3. Parse `atp_rankings_*.csv` / `wta_rankings_*.csv` for weekly rankings
4. Parse `atp_matches_*.csv` / `wta_matches_*.csv` for match results
5. For each player + match date combo, compute:
   - **Ranking**: Most recent ranking on or before match date
   - **Win rate (3 months)**: Wins / (Wins + Losses) in the 90 days before match date
6. Store in `player_stats` table

**Name matching**: Kalshi uses display names (e.g., "Novak Djokovic"), Sackmann uses first + last name columns. Match by normalized `"{first} {last}"`. Log unmatched names for manual review.

### 5.3 Extraction Logic

```
For each settled match:
    For each player (YES side and NO side):
        prices[] = all minute-by-minute prices for this player (sorted by minute)
        initial_price = prices[0]  # just before match start

        For each minute t in prices:
            current_price = prices[t]
            max_price_after = max(prices[t], prices[t+1], ..., prices[end])

            Look up player_ranking, opponent_ranking, player_win_rate_3m, opponent_win_rate_3m
            from player_stats table

            Insert into extracted_data
```

---

## 6. Query API

### Endpoint

```
GET /api/query
```

### Query Parameters (all optional, dual-bound ranges)

| Parameter | Type | Description |
|---|---|---|
| initial_price_min / initial_price_max | float | Initial price range (cents) |
| current_price_min / current_price_max | float | Current price range (cents) |
| player_ranking_min / player_ranking_max | int | Player ranking range |
| opponent_ranking_min / opponent_ranking_max | int | Opponent ranking range |
| player_win_rate_3m_min / player_win_rate_3m_max | float | Player 3-month win rate range |
| opponent_win_rate_3m_min / opponent_win_rate_3m_max | float | Opponent 3-month win rate range |

### Response

```json
{
    "total_count": 1234,
    "histogram": [
        {"bin_start": 0, "bin_end": 5, "count": 45, "percentage": 3.6},
        {"bin_start": 5, "bin_end": 10, "count": 78, "percentage": 6.3},
        ...
    ],
    "stats": {
        "mean": 42.3,
        "median": 39.0,
        "std": 18.7
    }
}
```

- Histogram bins: 5 cents each (0-5, 5-10, ..., 95-100)
- `percentage`: count / total_count * 100

---

## 7. Frontend

### Layout

Three sections stacked vertically:

1. **Query Filters**: 6 range sliders (or dual number inputs), each with min/max. A "Search" button.
2. **Histogram**: Bar chart (Recharts `BarChart`). X-axis = max_price_after bins (5-cent increments). Y-axis = percentage. Clickable bars.
3. **Summary Stats**: Total data points, mean, median, std deviation.

### Interaction

- Adjust any filter → click Search → API call → re-render histogram
- Click a histogram bar → display cumulative probability: "Percentage of data points with max_price_after > [clicked bin's left edge]"
- The cumulative percentage is shown as an overlay or info box near the chart

### API Proxy

Vite dev server proxies `/api` to `http://localhost:8000` to avoid CORS issues in development.

---

## 8. Configuration

### `.env.example`

```
# Kalshi API
KALSHI_API_KEY_ID=your_key_id_here
KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi_private.pem

# Database
DB_PATH=./data/tennis_odds.db

# Scheduler
FETCH_CRON_HOUR=3
FETCH_CRON_MINUTE=0

# Sackmann data
SACKMANN_DATA_DIR=./data/sackmann
```

---

## 9. Data Source Abstraction

The Kalshi client is behind an interface so future data sources can be added:

```python
class OddsDataSource:
    async def discover_matches(self) -> list[Match]
    async def fetch_match_prices(self, match_id: str) -> list[PricePoint]
```

`KalshiSource` implements this. Future `BetfairSource`, etc. implement the same interface.

---

## 10. Startup

`start.sh`:
```bash
# Start backend
cd backend && uvicorn app.main:app --port 8000 &

# Start frontend
cd frontend && npm run dev &

wait
```

First run will:
1. Create SQLite database and tables
2. Clone Sackmann repos
3. Wait for Kalshi credentials to be configured before fetching odds data

---

## 11. Scope Boundaries

**In scope (MVP)**:
- Kalshi historical data fetch (daily cron)
- Sackmann player rankings + win rates
- Extraction pipeline (raw → processed)
- Query API with 6 dual-range filters
- Histogram visualization with cumulative click
- Summary statistics

**Out of scope (future)**:
- Real-time WebSocket streaming
- AI/ML predictions
- Automated trading
- Multiple data source integration (Betfair, etc.)
- User authentication
- Cloud deployment
