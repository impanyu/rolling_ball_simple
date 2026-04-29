import logging
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Query
import app.config
from app.database import get_db, init_db
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)
router = APIRouter()

_monitor_task: asyncio.Task | None = None
_client: KalshiClient | None = None

TRADE_COUNT = 1


def _get_client() -> KalshiClient:
    global _client
    if _client is None:
        s = app.config.settings
        auth = KalshiAuth(s.kalshi_api_key_id, s.kalshi_private_key_path)
        _client = KalshiClient("https://api.elections.kalshi.com/trade-api/v2", auth)
    return _client


async def _get_ranking(db_path: str, player_name: str) -> int | None:
    async with get_db(db_path) as db:
        for pattern in [player_name.lower(), f"%{player_name.split()[-1].lower()}"]:
            cursor = await db.execute(
                "SELECT ranking FROM flashscore_rankings WHERE player_name LIKE ? LIMIT 1",
                (pattern,),
            )
            row = await cursor.fetchone()
            if row:
                return row[0]
    return None


# ─── Phase 1: Discovery (every hour) ───

async def _discover_matches(client: KalshiClient, db_path: str):
    """Fetch all open markets, record upcoming matches with scheduled times."""
    now = datetime.utcnow().isoformat() + "Z"

    for series in ["KXATPMATCH", "KXWTAMATCH", "KXITFMATCH", "KXITFWMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH"]:
        try:
            markets = await client._paginate("GET", "/markets", "markets", {
                "limit": 200, "series_ticker": series, "status": "open",
            })
        except Exception as e:
            logger.error(f"Failed to fetch open markets for {series}: {e}")
            continue

        by_event: dict[str, list] = defaultdict(list)
        for m in markets:
            by_event[m.get("event_ticker", "")].append(m)

        async with get_db(db_path) as db:
            for event_ticker, event_markets in by_event.items():
                if len(event_markets) != 2:
                    continue

                event_markets.sort(key=lambda m: m["ticker"])
                player_a = event_markets[0].get("yes_sub_title", "")
                player_b = event_markets[1].get("yes_sub_title", "")
                scheduled = event_markets[0].get("occurrence_datetime") or ""
                if not player_a or not player_b:
                    continue

                rank_a = await _get_ranking(db_path, player_a)
                rank_b = await _get_ranking(db_path, player_b)

                # Only record the side where player is ranked higher
                for ticker, player, opponent, rank_p, rank_o in [
                    (event_markets[0]["ticker"], player_a, player_b, rank_a, rank_b),
                    (event_markets[1]["ticker"], player_b, player_a, rank_b, rank_a),
                ]:
                    if not (rank_p and rank_o and rank_p < rank_o and rank_p <= 2000 and rank_o <= 2000):
                        continue

                    existing = await db.execute(
                        "SELECT 1 FROM monitored_matches WHERE ticker = ?", (ticker,)
                    )
                    if not await existing.fetchone():
                        await db.execute(
                            """INSERT INTO monitored_matches
                               (ticker, event_ticker, player, opponent, player_ranking, opponent_ranking,
                                initial_price, current_price, status, scheduled_time, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 'not started', ?, ?, ?)""",
                            (ticker, event_ticker, player, opponent, rank_p, rank_o,
                             scheduled, now, now),
                        )

            await db.commit()

    logger.info("Discovery complete")


# ─── Phase 2: Monitor started matches (every 15s) ───

async def _poll_monitored(client: KalshiClient, db_path: str):
    """Fast poll for matches that have started."""
    now_utc = datetime.utcnow()
    now = now_utc.isoformat() + "Z"

    async with get_db(db_path) as db:
        # Get pending matches whose scheduled time has passed -> check init price
        cursor = await db.execute(
            """SELECT ticker, player, opponent, player_ranking, opponent_ranking, scheduled_time
               FROM monitored_matches WHERE status = 'not started' AND scheduled_time IS NOT NULL"""
        )
        pending = await cursor.fetchall()

        for row in pending:
            ticker, player, opponent, rank_p, rank_o, scheduled = row
            try:
                sched_dt = datetime.fromisoformat(scheduled.replace("Z", "+00:00")).replace(tzinfo=None)
                if now_utc < sched_dt:
                    continue
            except Exception:
                continue

            # Match should have started - get current price as initial price
            try:
                market_data = await client.get_market(ticker)
                market = market_data.get("market", market_data)
                if market.get("status") != "open":
                    await db.execute(
                        "UPDATE monitored_matches SET status = 'completed', updated_at = ? WHERE ticker = ?",
                        (now, ticker),
                    )
                    continue

                price = round(float(market.get("last_price_dollars", 0)) * 100)
                volume = float(market.get("volume_fp", 0))

                # Skip matches with no price or very low volume
                if price == 0 or volume < 100:
                    continue

                # Check criteria: init 0-80 AND ranked higher
                if price <= 80 and rank_p and rank_o and rank_p < rank_o:
                    await db.execute(
                        """UPDATE monitored_matches
                           SET initial_price = ?, current_price = ?, status = 'in match', updated_at = ?
                           WHERE ticker = ?""",
                        (price, price, now, ticker),
                    )
                    logger.info(f"Started monitoring: {player} (#{rank_p}) vs {opponent} (#{rank_o}), init={price}")
                else:
                    await db.execute(
                        "UPDATE monitored_matches SET status = 'skipped', initial_price = ?, updated_at = ? WHERE ticker = ?",
                        (price, now, ticker),
                    )
                    logger.info(f"Skipped: {player} (#{rank_p}) vs {opponent} (#{rank_o}), init={price} (criteria not met)")

            except Exception as e:
                logger.debug(f"Failed to check {ticker}: {e}")

        await db.commit()

        # Fast poll active monitoring matches
        cursor2 = await db.execute(
            "SELECT ticker, player, opponent, initial_price, status FROM monitored_matches WHERE status IN ('in match', 'traded')"
        )
        active = await cursor2.fetchall()

    for row in active:
        ticker, player, opponent, init_price, status = row
        try:
            market_data = await client.get_market(ticker)
            market = market_data.get("market", market_data)
            market_status = market.get("status", "")

            if market_status != "open":
                async with get_db(db_path) as db:
                    await db.execute(
                        "UPDATE monitored_matches SET status = 'completed', updated_at = ? WHERE ticker = ?",
                        (now, ticker),
                    )
                    await db.commit()
                continue

            price = round(float(market.get("last_price_dollars", 0)) * 100)
            yes_ask = round(float(market.get("yes_ask_dollars", 0)) * 100)

            async with get_db(db_path) as db:
                await db.execute(
                    "UPDATE monitored_matches SET current_price = ?, updated_at = ? WHERE ticker = ?",
                    (price, now, ticker),
                )

                volume = float(market.get("volume_fp", 0))
                if init_price and init_price <= 80 and 87 <= yes_ask <= 91 and status == "in match" and volume >= 100:
                    await _execute_trade(client, db, ticker, player, opponent, init_price, yes_ask, now)

                if status == "traded" and price < 87:
                    await _cancel_pending_orders(client, db, ticker, player, now)

                await db.commit()

        except Exception as e:
            logger.debug(f"Poll failed for {ticker}: {e}")


# ─── Trading ───

async def _execute_trade(client, db, ticker, player, opponent, init_price, price, now):
    if price < 87 or price > 91:
        return

    try:
        result = await client.place_order(
            ticker=ticker, side="yes", action="buy",
            count=TRADE_COUNT, type="limit", yes_price=price,
        )
        order_id = result.get("order", {}).get("order_id", "")
        logger.info(f"TRADE: Buy {player} at {price}c (init={init_price}), order={order_id}")

        await db.execute(
            """INSERT INTO trade_log
               (ticker, player, opponent, side, action, price, count, initial_price, status, order_id, created_at)
               VALUES (?, ?, ?, 'yes', 'buy', ?, ?, ?, 'placed', ?, ?)""",
            (ticker, player, opponent, price, TRADE_COUNT, init_price, order_id, now),
        )
        await db.execute(
            "UPDATE monitored_matches SET status = 'traded', updated_at = ? WHERE ticker = ?",
            (now, ticker),
        )

    except Exception as e:
        logger.error(f"Trade failed for {player} at {price}: {e}")
        await db.execute(
            """INSERT INTO trade_log
               (ticker, player, opponent, side, action, price, count, initial_price, status, order_id, created_at)
               VALUES (?, ?, ?, 'yes', 'buy', ?, ?, ?, 'failed', ?, ?)""",
            (ticker, player, opponent, price, TRADE_COUNT, init_price, str(e)[:100], now),
        )


async def _cancel_pending_orders(client, db, ticker, player, now):
    cursor = await db.execute(
        "SELECT order_id FROM trade_log WHERE ticker = ? AND status = 'placed'",
        (ticker,),
    )
    rows = await cursor.fetchall()

    for row in rows:
        order_id = row[0]
        if not order_id:
            continue
        try:
            await client._request("DELETE", f"/portfolio/orders/{order_id}")
            await db.execute(
                "UPDATE trade_log SET status = 'cancelled' WHERE order_id = ?",
                (order_id,),
            )
            logger.info(f"Cancelled order {order_id} for {player} (price dropped below 87)")
        except Exception as e:
            logger.debug(f"Cancel failed for {order_id}: {e}")

    await db.execute(
        "UPDATE monitored_matches SET status = 'in match', updated_at = ? WHERE ticker = ?",
        (now, ticker),
    )


# ─── Monitor loop ───

async def _monitor_loop():
    db_path = app.config.settings.db_path
    await init_db(db_path)
    client = _get_client()
    logger.info("Monitor loop started")

    last_discover = 0
    while True:
        try:
            now_ts = datetime.utcnow().timestamp()

            # Discovery: on start and every hour
            if now_ts - last_discover >= 3600:
                await _discover_matches(client, db_path)
                last_discover = now_ts

            # Fast poll: only matches that have started and are monitoring/traded
            await _poll_monitored(client, db_path)

        except asyncio.CancelledError:
            logger.info("Monitor loop cancelled")
            return
        except Exception as e:
            logger.error(f"Monitor tick error: {e}")

        await asyncio.sleep(15)


# ─── API endpoints ───

@router.get("/api/active-matches")
async def active_matches():
    client = _get_client()
    db_path = app.config.settings.db_path
    results = []

    for series in ["KXATPMATCH", "KXWTAMATCH", "KXITFMATCH", "KXITFWMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH"]:
        try:
            markets = await client._paginate("GET", "/markets", "markets", {
                "limit": 200, "series_ticker": series, "status": "open",
            })
        except Exception:
            continue

        by_event: dict[str, list] = defaultdict(list)
        for m in markets:
            by_event[m.get("event_ticker", "")].append(m)

        for event_ticker, event_markets in by_event.items():
            if len(event_markets) != 2:
                continue

            event_markets.sort(key=lambda m: m["ticker"])
            player_a = event_markets[0].get("yes_sub_title", "")
            player_b = event_markets[1].get("yes_sub_title", "")
            price_a = round(float(event_markets[0].get("last_price_dollars", 0)) * 100)
            price_b = round(float(event_markets[1].get("last_price_dollars", 0)) * 100)
            scheduled = event_markets[0].get("occurrence_datetime", "")
            rank_a = await _get_ranking(db_path, player_a)
            rank_b = await _get_ranking(db_path, player_b)

            for ticker, player, opponent, price, rank_p, rank_o in [
                (event_markets[0]["ticker"], player_a, player_b, price_a, rank_a, rank_b),
                (event_markets[1]["ticker"], player_b, player_a, price_b, rank_b, rank_a),
            ]:
                if rank_p and rank_o and rank_p < rank_o and price <= 80:
                    results.append({
                        "event_ticker": event_ticker,
                        "ticker": ticker,
                        "player": player,
                        "opponent": opponent,
                        "player_ranking": rank_p,
                        "opponent_ranking": rank_o,
                        "current_price": price,
                        "scheduled": scheduled[:16] if scheduled else "",
                        "tradeable": 87 <= price <= 91,
                    })

    return {"matches": results}


@router.post("/api/monitor-start")
async def monitor_start():
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        return {"status": "already running"}
    _monitor_task = asyncio.create_task(_monitor_loop())
    return {"status": "started"}


@router.post("/api/monitor-stop")
async def monitor_stop():
    global _monitor_task
    if _monitor_task and not _monitor_task.done():
        _monitor_task.cancel()
        _monitor_task = None
        return {"status": "stopped"}
    return {"status": "not running"}


@router.get("/api/monitor-status")
async def monitor_status():
    running = _monitor_task is not None and not _monitor_task.done()
    db_path = app.config.settings.db_path

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM monitored_matches WHERE status IN ('not started', 'in match', 'traded') ORDER BY scheduled_time"
        )
        matches = [dict(r) for r in await cursor.fetchall()]

        cursor2 = await db.execute(
            "SELECT * FROM trade_log ORDER BY created_at DESC LIMIT 50"
        )
        trades = [dict(r) for r in await cursor2.fetchall()]

    return {"running": running, "matches": matches, "trades": trades}
