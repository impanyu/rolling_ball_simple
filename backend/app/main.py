# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings as _settings_ref
import app.config as _config_module
from app.database import init_db
from app.routes.query import router as query_router
from app.routes.simulate import router as simulate_router
from app.routes.trading import router as trading_router
from app.routes.live_signal import router as live_signal_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _get_settings():
    """Get current settings (supports test-time reloads)."""
    return _config_module.settings


async def scheduled_fetch():
    """Daily job: discover new matches, fetch candlesticks, extract data, regenerate rules."""
    logger.info("Starting scheduled data fetch...")
    try:
        from app.kalshi.auth import KalshiAuth
        from app.kalshi.client import KalshiClient
        from app.kalshi.fetcher import run_full_pipeline
        from app.stats.sackmann import ensure_repos

        s = _get_settings()
        ensure_repos(s.sackmann_data_dir)
        auth = KalshiAuth(s.kalshi_api_key_id, s.kalshi_private_key_path)
        client = KalshiClient("https://api.elections.kalshi.com/trade-api/v2", auth)
        await run_full_pipeline(client, s.db_path, s.sackmann_data_dir)
        await client.close()
        logger.info("Scheduled fetch complete.")
    except Exception as e:
        logger.error(f"Scheduled fetch failed: {e}")

    logger.info("Regenerating rules...")
    try:
        await regenerate_rules()
    except Exception as e:
        logger.error(f"Rule regeneration failed: {e}")


async def regenerate_rules():
    """Regenerate all player + global rules from current data."""
    import sqlite3
    from collections import defaultdict
    from app.analysis.predictor_v2 import extract_match_samples, _generate_rules, generate_global_rules

    s = _get_settings()
    db = sqlite3.connect(s.db_path, timeout=120)
    db.execute("PRAGMA journal_mode=WAL")

    all_data = db.execute('''
        SELECT match_id, player, minute, current_price, max_price_after,
               running_min, running_max, initial_price, player_ranking, opponent_ranking,
               COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) as won
        FROM extracted_data
        WHERE player_ranking IS NOT NULL AND player_ranking <= 2000
          AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
        ORDER BY match_id, player, minute
    ''').fetchall()

    matches = defaultdict(list)
    for row in all_data:
        matches[(row[0], row[1])].append({
            'minute': row[2], 'cp': row[3], 'mpa': row[4],
            'rmin': row[5], 'rmax': row[6], 'ip': row[7],
            'p_rank': row[8], 'o_rank': row[9], 'won': row[10],
        })

    player_features = defaultdict(list)
    all_features = []
    for (mid, player), prices in matches.items():
        samples = extract_match_samples(prices, interval=5, match_id=mid)
        for s_item in samples:
            s_item['opp_rank'] = prices[0]['o_rank']
            s_item['rank_gap'] = (prices[0]['o_rank'] - prices[0]['p_rank']) if prices[0]['p_rank'] and prices[0]['o_rank'] else None
        player_features[player].extend(samples)
        all_features.extend(samples)

    db.execute('DELETE FROM player_rules_v2')
    db.commit()

    total = 0
    for player, feats in player_features.items():
        if len(feats) < 10:
            continue
        r = db.execute('SELECT DISTINCT player_ranking FROM extracted_data WHERE player=? AND player_ranking IS NOT NULL LIMIT 1', (player,)).fetchone()
        rank = r[0] if r else None
        rules = _generate_rules(player, feats, {})
        for rule in rules:
            db.execute('INSERT OR REPLACE INTO player_rules_v2 (player,rank,category,condition,win_rate,sample_size,description,updated_at) VALUES (?,?,?,?,?,?,?,datetime("now"))',
                (player, rank, rule['category'], rule['condition'], rule['win_rate'], rule['sample_size'], rule.get('description', '')))
            total += 1

    global_rules = generate_global_rules(all_features)
    for rule in global_rules:
        db.execute('INSERT OR REPLACE INTO player_rules_v2 (player,rank,category,condition,win_rate,sample_size,description,updated_at) VALUES (?,?,?,?,?,?,?,datetime("now"))',
            ('__GLOBAL__', None, rule['category'], rule['condition'], rule['win_rate'], rule['sample_size'], rule.get('description', '')))
        total += 1

    db.commit()
    db.close()
    logger.info(f"Rules regenerated: {total} total")


async def scheduled_winrates_refresh():
    """Daily job: scrape FlashScore results and update win rates."""
    logger.info("Starting scheduled winrates refresh...")
    try:
        from app.scraper.flashscore_results import scrape_and_store_results
        s = _get_settings()
        inserted = await scrape_and_store_results(s.db_path, max_per_tour=600)
        logger.info(f"Winrates refresh complete: {inserted} results stored.")
    except Exception as e:
        logger.error(f"Winrates refresh failed: {e}")


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    s = _get_settings()
    await init_db(s.db_path)
    logger.info("Database initialized.")

    scheduler.add_job(
        scheduled_winrates_refresh,
        "cron",
        hour=4,
        minute=0,
        id="daily_winrates",
    )

    if s.kalshi_api_key_id:
        scheduler.add_job(
            scheduled_fetch,
            "cron",
            hour=s.fetch_cron_hour,
            minute=s.fetch_cron_minute,
            id="daily_fetch",
        )

    scheduler.start()
    if s.kalshi_api_key_id:
        logger.info(
            f"Scheduler started: Kalshi fetch at {s.fetch_cron_hour:02d}:{s.fetch_cron_minute:02d}, winrates at 04:00"
        )
    else:
        logger.info("Scheduler started: winrates at 04:00 (no Kalshi API key)")

    yield

    from app.scraper.browser import close_browser
    await close_browser()

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
app.include_router(simulate_router)
app.include_router(trading_router)
app.include_router(live_signal_router)


@app.middleware("http")
async def ensure_db_initialized(request: Request, call_next):
    """Ensure DB is initialized before handling requests (fallback for test environments)."""
    await init_db(_get_settings().db_path)
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/regenerate-rules")
async def api_regenerate_rules():
    """Manually trigger rule regeneration."""
    import asyncio
    asyncio.create_task(regenerate_rules())
    return {"status": "started"}
