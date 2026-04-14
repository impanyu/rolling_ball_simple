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
