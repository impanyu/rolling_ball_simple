"""Auto Trading: automatically discover, track, and trade Kalshi tennis matches."""
import logging
import asyncio
from datetime import datetime, timezone
from collections import defaultdict
from fastapi import APIRouter
import app.config
from app.database import get_db, init_db
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient
from app.analysis.predictor_v2 import match_rules, compute_score_v2

logger = logging.getLogger(__name__)
router = APIRouter()

TENNIS_SERIES = [
    "KXATPMATCH", "KXWTAMATCH", "KXITFMATCH", "KXITFWMATCH",
    "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH",
]

MAX_DAILY_MATCHES = 30
POLL_INTERVAL = 15
DISCOVER_INTERVAL = 1800
COOLDOWN_MINUTES = 15
MAX_CONTRACTS = 5
DOLLARS_PER_UNIT = 10

_auto_task: asyncio.Task | None = None
_client: KalshiClient | None = None


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


async def _get_player_rules(db_path, player):
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT category, condition, win_rate, sample_size, description FROM player_rules_v2 WHERE player = ?",
            (player,),
        )
        rows = await cursor.fetchall()
    return [{'category': r[0], 'condition': r[1], 'win_rate': r[2], 'sample_size': r[3], 'description': r[4]} for r in rows]


async def _resolve_player(db_path, name):
    async with get_db(db_path) as db:
        parts = name.strip().split()
        for i in range(len(parts)):
            for j in range(len(parts)):
                if i == j:
                    continue
                cursor = await db.execute(
                    "SELECT DISTINCT player FROM extracted_data WHERE LOWER(player) LIKE ? AND LOWER(player) LIKE ? LIMIT 1",
                    (f"{parts[i].lower()}%", f"%{parts[j].lower()}"),
                )
                row = await cursor.fetchone()
                if row:
                    return row[0]
        longest = max(parts, key=len).lower() if parts else name.lower()
        cursor = await db.execute(
            "SELECT DISTINCT player FROM extracted_data WHERE LOWER(player) LIKE ? LIMIT 1",
            (f"%{longest}%",),
        )
        row = await cursor.fetchone()
        return row[0] if row else name


async def _init_auto_tables(db_path):
    async with get_db(db_path) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL,
            recorded_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS auto_matches (
            event_ticker TEXT PRIMARY KEY,
            ticker_a TEXT, ticker_b TEXT,
            player_a TEXT, player_b TEXT,
            rank_a INTEGER, rank_b INTEGER,
            priority REAL,
            status TEXT DEFAULT 'upcoming',
            init_price INTEGER, current_price INTEGER,
            running_min INTEGER, running_max INTEGER,
            match_start TEXT,
            last_diff REAL, last_contracts INTEGER, last_rec TEXT,
            price_history TEXT DEFAULT '[]',
            trade_date TEXT,
            created_at TEXT, updated_at TEXT
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS auto_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_ticker TEXT, ticker TEXT,
            player TEXT, side TEXT,
            price INTEGER, contracts INTEGER,
            score_diff REAL, order_id TEXT,
            status TEXT DEFAULT 'placed',
            won INTEGER, pnl REAL,
            created_at TEXT
        )""")
        await db.commit()


async def _discover_matches(client, db_path):
    """Find qualifying matches: both ranked ≤ 500, sufficient volume."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now = datetime.now(timezone.utc).isoformat() + "Z"
    candidates = []

    for series in TENNIS_SERIES:
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
            if not player_a or not player_b:
                continue

            rank_a = await _get_ranking(db_path, player_a)
            rank_b = await _get_ranking(db_path, player_b)

            if not rank_a or not rank_b or rank_a > 500 or rank_b > 500:
                continue

            volume = float(event_markets[0].get("volume", event_markets[0].get("volume_fp", 0)))
            price_a = round(float(event_markets[0].get("last_price_dollars", 0)) * 100)

            # Priority: lower combined rank + higher volume = better
            priority = (1000 - rank_a - rank_b) + min(volume / 100, 500)

            candidates.append({
                "event_ticker": event_ticker,
                "ticker_a": event_markets[0]["ticker"],
                "ticker_b": event_markets[1]["ticker"],
                "player_a": player_a,
                "player_b": player_b,
                "rank_a": rank_a,
                "rank_b": rank_b,
                "price_a": price_a,
                "volume": volume,
                "priority": priority,
            })

    candidates.sort(key=lambda x: -x["priority"])
    selected = candidates[:MAX_DAILY_MATCHES]

    async with get_db(db_path) as db:
        for c in selected:
            existing = await db.execute(
                "SELECT 1 FROM auto_matches WHERE event_ticker = ? AND trade_date = ?",
                (c["event_ticker"], today),
            )
            if await existing.fetchone():
                continue
            await db.execute(
                """INSERT OR REPLACE INTO auto_matches
                   (event_ticker, ticker_a, ticker_b, player_a, player_b, rank_a, rank_b,
                    priority, status, current_price, trade_date, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'upcoming', ?, ?, ?, ?)""",
                (c["event_ticker"], c["ticker_a"], c["ticker_b"],
                 c["player_a"], c["player_b"], c["rank_a"], c["rank_b"],
                 c["priority"], c["price_a"], today, now, now),
            )
        await db.commit()

    logger.info(f"Auto-discover: {len(selected)} qualifying matches (from {len(candidates)} candidates)")


async def _compute_signal(db_path, player_a, player_b, rank_a, rank_b, cp, ip, rmin, rmax, minutes_played, recent_change):
    """Compute signal for a match using v3_penalty strategy."""
    # Ensure A is higher ranked
    swapped = False
    if rank_a and rank_b and rank_a > rank_b:
        player_a, player_b = player_b, player_a
        rank_a, rank_b = rank_b, rank_a
        cp = 100 - cp
        ip = 100 - ip
        rmin, rmax = 100 - rmax, 100 - rmin
        recent_change = -recent_change
        swapped = True

    rules_a = await _get_player_rules(db_path, player_a)
    rules_b = await _get_player_rules(db_path, player_b)
    global_rules = await _get_player_rules(db_path, "__GLOBAL__")

    state_a = {'current_price': cp, 'init_price': ip,
               'running_min': rmin, 'running_max': rmax,
               'minutes_played': minutes_played, 'recent_change': recent_change,
               'opponent_rank': rank_b, 'player_rank': rank_a}
    state_b = {'current_price': 100 - cp, 'init_price': 100 - ip,
               'running_min': 100 - rmax, 'running_max': 100 - rmin,
               'minutes_played': minutes_played, 'recent_change': -recent_change,
               'opponent_rank': rank_a, 'player_rank': rank_b}

    t_a = match_rules(rules_a, state_a)
    t_b = match_rules(rules_b, state_b)
    gt_a = match_rules(global_rules, state_a)
    gt_b = match_rules(global_rules, state_b)

    conf_a = min(len(rules_a) / 20, 1.0)
    conf_b = min(len(rules_b) / 20, 1.0)
    sa = compute_score_v2(t_a) + compute_score_v2(gt_a) * (1 - conf_a)
    sb = compute_score_v2(t_b) + compute_score_v2(gt_b) * (1 - conf_b)
    diff = sa - sb

    # v3_penalty sizing
    abs_diff = abs(diff)
    if diff > 0:
        buy_player = player_a
        buy_price = cp
        buy_side = "yes" if not swapped else "no"
        buy_ticker_idx = 0 if not swapped else 1
    else:
        buy_player = player_b
        buy_price = 100 - cp
        buy_side = "no" if not swapped else "yes"
        buy_ticker_idx = 1 if not swapped else 0

    ev = max(0, abs_diff / 500) * (100 - buy_price - 2) - max(0, 1 - abs_diff / 500) * (buy_price + 2)
    penalty = max(0, 1 - ((buy_price - 50) / 25) ** 2)
    contracts = min(MAX_CONTRACTS, max(0, round(ev * penalty / 5))) if ev > 0 else 0

    if contracts >= 4:
        strength = "STRONG"
    elif contracts >= 2:
        strength = "MODERATE"
    elif contracts >= 1:
        strength = "WEAK"
    else:
        strength = "NO SIGNAL"

    rec = f"{strength} BUY {buy_player} x{contracts}" if contracts > 0 else "NO TRADE"

    return {
        "diff": round(diff, 1),
        "contracts": contracts,
        "buy_player": buy_player,
        "buy_price": buy_price,
        "buy_side": buy_side,
        "buy_ticker_idx": buy_ticker_idx,
        "rec": rec,
        "strength": strength,
        "score_a": round(sa, 1),
        "score_b": round(sb, 1),
        "swapped": swapped,
    }


async def _poll_and_trade(client, db_path):
    """Poll active matches, compute signals, execute trades."""
    now = datetime.now(timezone.utc)
    now_str = now.isoformat() + "Z"
    today = now.strftime("%Y-%m-%d")

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM auto_matches WHERE trade_date = ? AND status IN ('upcoming', 'active')",
            (today,),
        )
        matches = [dict(r) for r in await cursor.fetchall()]

    for m in matches:
        try:
            market_data = await client.get_market(m["ticker_a"])
            market = market_data.get("market", market_data)
            status = market.get("status", "")

            if status not in ("open", "active", "trading"):
                # Match ended — check trade results
                async with get_db(db_path) as db:
                    await db.execute(
                        "UPDATE auto_matches SET status = 'completed', updated_at = ? WHERE event_ticker = ? AND trade_date = ?",
                        (now_str, m["event_ticker"], today),
                    )
                    # Update trade results
                    pending = await db.execute(
                        "SELECT id, ticker, side, price, contracts FROM auto_trades WHERE event_ticker = ? AND status = 'placed'",
                        (m["event_ticker"],),
                    )
                    for trade in await pending.fetchall():
                        try:
                            mk = await client.get_market(trade[1])
                            result = mk.get("market", mk).get("result", "")
                            if result in ("yes", "no"):
                                won = 1 if result == trade[3] else 0  # side matches result
                                bp = trade[3]  # price
                                contracts = trade[4]
                                pnl = ((100 - bp - 2) * contracts) if won else (-(bp + 2) * contracts)
                                await db.execute(
                                    "UPDATE auto_trades SET status = 'settled', won = ?, pnl = ? WHERE id = ?",
                                    (won, pnl, trade[0]),
                                )
                        except Exception:
                            pass
                    await db.commit()
                continue

            cp = round(float(market.get("last_price_dollars", 0)) * 100)
            if cp == 0:
                continue

            # Update match status
            ip = m["init_price"] or cp
            rmin = min(m["running_min"] or cp, cp)
            rmax = max(m["running_max"] or cp, cp)

            # Estimate minutes played
            minutes_played = 0
            if m.get("match_start"):
                try:
                    start_dt = datetime.fromisoformat(m["match_start"].replace("Z", "+00:00"))
                    minutes_played = max(0, int((now - start_dt).total_seconds() / 60))
                except Exception:
                    pass

            # Detect match start from occurrence_datetime if not set
            if not m.get("match_start"):
                occ = market.get("occurrence_datetime")
                if occ:
                    try:
                        occ_dt = datetime.fromisoformat(occ.replace("Z", "+00:00"))
                        if now > occ_dt:
                            # Try FlashScore
                            try:
                                from app.scraper.flashscore_results import scrape_live_match_start
                                fs_start = await scrape_live_match_start(m["player_a"], m["player_b"])
                                if fs_start:
                                    async with get_db(db_path) as db:
                                        await db.execute(
                                            "UPDATE auto_matches SET match_start = ? WHERE event_ticker = ? AND trade_date = ?",
                                            (fs_start, m["event_ticker"], today),
                                        )
                                        await db.commit()
                                    start_dt = datetime.fromisoformat(fs_start.replace("Z", "+00:00"))
                                    minutes_played = max(0, int((now - start_dt).total_seconds() / 60))
                            except Exception:
                                pass
                    except Exception:
                        pass

            # Recent change
            import json
            history = json.loads(m.get("price_history", "[]"))
            prev_price = history[-1]["cp"] if history else cp
            recent_change = cp - prev_price

            # Add to history
            history.append({"t": now_str[:19], "cp": cp, "min": minutes_played})
            if len(history) > 500:
                history = history[-500:]

            # Resolve player names
            pa = await _resolve_player(db_path, m["player_a"])
            pb = await _resolve_player(db_path, m["player_b"])

            # Compute signal
            signal = await _compute_signal(
                db_path, pa, pb, m["rank_a"], m["rank_b"],
                cp, ip, rmin, rmax, minutes_played, recent_change,
            )

            new_status = "active" if minutes_played > 0 else "upcoming"

            async with get_db(db_path) as db:
                await db.execute(
                    """UPDATE auto_matches SET status = ?, current_price = ?, init_price = ?,
                       running_min = ?, running_max = ?,
                       last_diff = ?, last_contracts = ?, last_rec = ?,
                       price_history = ?, updated_at = ?
                       WHERE event_ticker = ? AND trade_date = ?""",
                    (new_status, cp, ip, rmin, rmax,
                     signal["diff"], signal["contracts"], signal["rec"],
                     json.dumps(history), now_str,
                     m["event_ticker"], today),
                )
                await db.commit()

            # Execute trade if signal is strong enough
            if signal["contracts"] > 0 and minutes_played > 0:
                # Check cooldown
                async with get_db(db_path) as db:
                    last_trade = await db.execute(
                        "SELECT created_at FROM auto_trades WHERE event_ticker = ? ORDER BY created_at DESC LIMIT 1",
                        (m["event_ticker"],),
                    )
                    lt = await last_trade.fetchone()

                if lt:
                    try:
                        last_t = datetime.fromisoformat(lt[0].replace("Z", "+00:00"))
                        if (now - last_t).total_seconds() < COOLDOWN_MINUTES * 60:
                            continue
                    except Exception:
                        pass

                # Place order
                ticker = m["ticker_a"] if signal["buy_ticker_idx"] == 0 else m["ticker_b"]
                try:
                    count = signal["contracts"]
                    price_cents = signal["buy_price"]
                    result = await client.place_order(
                        ticker=ticker,
                        side=signal["buy_side"],
                        action="buy",
                        count=count,
                        type="limit",
                        yes_price=price_cents if signal["buy_side"] == "yes" else None,
                        no_price=price_cents if signal["buy_side"] == "no" else None,
                    )
                    order_id = result.get("order", {}).get("order_id", "")
                    logger.info(f"AUTO TRADE: {signal['rec']} @ {price_cents}c, order={order_id}")

                    async with get_db(db_path) as db:
                        await db.execute(
                            """INSERT INTO auto_trades
                               (event_ticker, ticker, player, side, price, contracts, score_diff, order_id, status, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'placed', ?)""",
                            (m["event_ticker"], ticker, signal["buy_player"],
                             signal["buy_side"], price_cents, count,
                             signal["diff"], order_id, now_str),
                        )
                        await db.commit()

                except Exception as e:
                    logger.error(f"Auto trade failed: {e}")

        except Exception as e:
            logger.debug(f"Poll error for {m['event_ticker']}: {e}")


async def _auto_loop():
    """Main auto trading loop."""
    db_path = app.config.settings.db_path
    await _init_auto_tables(db_path)
    client = _get_client()
    logger.info("Auto trading loop started")

    last_discover = 0
    last_balance_record = -600  # Record immediately on start
    while True:
        try:
            now_ts = datetime.now(timezone.utc).timestamp()

            if now_ts - last_discover >= DISCOVER_INTERVAL:
                await _discover_matches(client, db_path)
                last_discover = now_ts

            # Record balance every 10 minutes
            if now_ts - last_balance_record >= 600:
                try:
                    bal_data = await client.get_balance()
                    bal = bal_data.get("balance", 0)
                    if isinstance(bal, (int, float)) and bal > 1:
                        bal = bal / 100
                    async with get_db(db_path) as db:
                        await db.execute(
                            "INSERT INTO balance_history (balance, recorded_at) VALUES (?, ?)",
                            (bal, datetime.now(timezone.utc).isoformat() + "Z"),
                        )
                        await db.commit()
                    last_balance_record = now_ts
                except Exception:
                    pass

            await _poll_and_trade(client, db_path)

        except asyncio.CancelledError:
            logger.info("Auto trading loop cancelled")
            return
        except Exception as e:
            logger.error(f"Auto trading error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ── API Endpoints ──

@router.post("/api/auto-trading/start")
async def auto_start():
    global _auto_task
    if _auto_task and not _auto_task.done():
        return {"status": "already running"}
    _auto_task = asyncio.create_task(_auto_loop())
    return {"status": "started"}


@router.post("/api/auto-trading/stop")
async def auto_stop():
    global _auto_task
    if _auto_task and not _auto_task.done():
        _auto_task.cancel()
        _auto_task = None
        return {"status": "stopped"}
    return {"status": "not running"}


@router.get("/api/auto-trading/status")
async def auto_status():
    running = _auto_task is not None and not _auto_task.done()
    db_path = app.config.settings.db_path
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    await _init_auto_tables(db_path)

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM auto_matches WHERE trade_date = ? ORDER BY priority DESC",
            (today,),
        )
        matches = [dict(r) for r in await cursor.fetchall()]

        cursor2 = await db.execute(
            "SELECT * FROM auto_trades ORDER BY created_at DESC LIMIT 50",
        )
        trades = [dict(r) for r in await cursor2.fetchall()]

    total_pnl = sum(t.get("pnl", 0) or 0 for t in trades)
    active = sum(1 for m in matches if m["status"] == "active")
    upcoming = sum(1 for m in matches if m["status"] == "upcoming")

    return {
        "running": running,
        "today": today,
        "matches": matches,
        "trades": trades,
        "summary": {
            "total_matches": len(matches),
            "active": active,
            "upcoming": upcoming,
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 2),
        },
    }


@router.get("/api/auto-trading/match/{event_ticker}")
async def auto_match_detail(event_ticker: str):
    db_path = app.config.settings.db_path
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM auto_matches WHERE event_ticker = ? AND trade_date = ?",
            (event_ticker, today),
        )
        row = await cursor.fetchone()
        match = dict(row) if row else None

        cursor2 = await db.execute(
            "SELECT * FROM auto_trades WHERE event_ticker = ? ORDER BY created_at DESC",
            (event_ticker,),
        )
        trades = [dict(r) for r in await cursor2.fetchall()]

    if not match:
        return {"error": "Match not found"}

    import json
    history = json.loads(match.get("price_history", "[]"))

    return {
        "match": match,
        "trades": trades,
        "history": history,
    }


@router.get("/api/auto-trading/balance")
async def auto_balance():
    """Get Kalshi account balance + history."""
    client = _get_client()
    db_path = app.config.settings.db_path
    balance = None
    try:
        data = await client.get_balance()
        bal = data.get("balance", 0)
        balance = round(bal / 100, 2) if isinstance(bal, (int, float)) and bal > 1 else bal
    except Exception as e:
        pass

    await _init_auto_tables(db_path)
    history = []
    try:
        async with get_db(db_path) as db:
            cursor = await db.execute(
                "SELECT balance, recorded_at FROM balance_history ORDER BY recorded_at DESC LIMIT 200",
            )
            history = [{"balance": r[0], "time": r[1]} for r in await cursor.fetchall()]
    except Exception:
        pass

    return {"balance": balance, "history": list(reversed(history))}


@router.post("/api/auto-trading/discover")
async def auto_discover_now():
    """Manually trigger match discovery."""
    client = _get_client()
    db_path = app.config.settings.db_path
    await _init_auto_tables(db_path)
    await _discover_matches(client, db_path)
    return {"status": "done"}
