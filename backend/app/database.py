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
    opponent_win_rate_3m REAL,
    pre_match_std REAL,
    pre_match_trades INTEGER,
    running_min REAL,
    running_max REAL
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

SQL_CREATE_MATCH_RESULTS = """
CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    winner TEXT NOT NULL,
    loser TEXT NOT NULL,
    match_date TEXT NOT NULL,
    tour TEXT NOT NULL,
    tournament TEXT,
    UNIQUE(winner, loser, match_date, tour)
)
"""

SQL_CREATE_MATCH_START_TIMES = """
CREATE TABLE IF NOT EXISTS match_start_times (
    match_id TEXT PRIMARY KEY,
    start_time TEXT NOT NULL
)
"""

SQL_CREATE_FLASHSCORE_RANKINGS = """
CREATE TABLE IF NOT EXISTS flashscore_rankings (
    player_name TEXT NOT NULL,
    tour TEXT NOT NULL,
    ranking INTEGER NOT NULL,
    href TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (player_name, tour)
)
"""

SQL_CREATE_MONITORED_MATCHES = """
CREATE TABLE IF NOT EXISTS monitored_matches (
    ticker TEXT PRIMARY KEY,
    event_ticker TEXT NOT NULL,
    player TEXT NOT NULL,
    opponent TEXT NOT NULL,
    player_ranking INTEGER,
    opponent_ranking INTEGER,
    initial_price REAL,
    current_price REAL,
    status TEXT DEFAULT 'monitoring',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

SQL_CREATE_TRADE_LOG = """
CREATE TABLE IF NOT EXISTS trade_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    player TEXT NOT NULL,
    opponent TEXT NOT NULL,
    side TEXT NOT NULL,
    action TEXT NOT NULL,
    price INTEGER NOT NULL,
    count INTEGER NOT NULL,
    initial_price REAL,
    status TEXT DEFAULT 'placed',
    order_id TEXT,
    created_at TEXT NOT NULL
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
        await db.execute(SQL_CREATE_MATCH_RESULTS)
        await db.execute(SQL_CREATE_MATCH_START_TIMES)
        await db.execute(SQL_CREATE_FLASHSCORE_RANKINGS)
        await db.execute(SQL_CREATE_MONITORED_MATCHES)
        await db.execute(SQL_CREATE_TRADE_LOG)
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
