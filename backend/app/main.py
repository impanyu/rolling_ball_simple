# backend/app/main.py
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes.query import router as query_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()
_db_initialized = False


async def scheduled_fetch():
    """Daily job: discover new matches, fetch candlesticks, extract data."""
    logger.info("Starting scheduled data fetch...")
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
    global _db_initialized
    await init_db(settings.db_path)
    _db_initialized = True
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


@app.middleware("http")
async def ensure_db_initialized(request: Request, call_next):
    """Ensure DB is initialized before handling requests (fallback for test environments)."""
    global _db_initialized
    if not _db_initialized:
        await init_db(settings.db_path)
        _db_initialized = True
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok"}
