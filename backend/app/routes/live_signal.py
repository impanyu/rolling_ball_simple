"""Live Signal API: real-time match tracking with rule-based recommendations."""
import logging
import math
import sqlite3
from datetime import datetime
from collections import defaultdict
from fastapi import APIRouter, Query
import app.config
from app.database import get_db
from app.analysis.predictor_v2 import compute_score_v2, match_rules
from app.kalshi.auth import KalshiAuth
from app.kalshi.client import KalshiClient

logger = logging.getLogger(__name__)
router = APIRouter()

TENNIS_SERIES = [
    "KXATPMATCH", "KXWTAMATCH", "KXITFMATCH", "KXITFWMATCH",
    "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH",
]

_kalshi_client: KalshiClient | None = None


def _get_kalshi_client() -> KalshiClient:
    global _kalshi_client
    if _kalshi_client is None:
        s = app.config.settings
        auth = KalshiAuth(s.kalshi_api_key_id, s.kalshi_private_key_path)
        _kalshi_client = KalshiClient("https://api.elections.kalshi.com/trade-api/v2", auth)
    return _kalshi_client


async def _resolve_player(db_path, name):
    """Resolve input name to exact extracted_data player name."""
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
            (f"% {longest}%",),
        )
        row = await cursor.fetchone()
        if row:
            return row[0]
        cursor = await db.execute(
            "SELECT DISTINCT player FROM extracted_data WHERE LOWER(player) LIKE ? LIMIT 1",
            (f"%{longest}%",),
        )
        row = await cursor.fetchone()
        return row[0] if row else name


async def _get_player_rules(db_path, player):
    """Get V2 rules for a player from DB."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT category, condition, win_rate, sample_size, description FROM player_rules_v2 WHERE player = ?",
            (player,),
        )
        rows = await cursor.fetchall()
    return [{'category': r[0], 'condition': r[1], 'win_rate': r[2], 'sample_size': r[3], 'description': r[4]} for r in rows]


async def _get_ranking(db_path, player):
    async with get_db(db_path) as db:
        c = await db.execute("SELECT ranking FROM flashscore_rankings WHERE player_name = ? LIMIT 1", (player.lower(),))
        r = await c.fetchone()
        if r: return r[0]
        c2 = await db.execute("SELECT DISTINCT player_ranking FROM extracted_data WHERE player = ? AND player_ranking IS NOT NULL LIMIT 1", (player,))
        r2 = await c2.fetchone()
        return r2[0] if r2 else None


@router.get("/api/live-signal")
async def live_signal(
    player_a: str = Query(...),
    player_b: str = Query(...),
    current_price: int = Query(...),
    init_price: int = Query(None),
    running_min: int = Query(None),
    running_max: int = Query(None),
    minutes_played: int = Query(60),
):
    """Compute live signal for a match given current state."""
    db_path = app.config.settings.db_path

    # Resolve names
    player_a = await _resolve_player(db_path, player_a)
    player_b = await _resolve_player(db_path, player_b)

    rank_a = await _get_ranking(db_path, player_a)
    rank_b = await _get_ranking(db_path, player_b)

    # Determine favorite (A = ranked higher)
    if rank_a and rank_b and rank_a > rank_b:
        player_a, player_b = player_b, player_a
        rank_a, rank_b = rank_b, rank_a
        current_price = 100 - current_price
        if init_price: init_price = 100 - init_price
        if running_min is not None and running_max is not None:
            running_min, running_max = 100 - running_max, 100 - running_min

    cp = current_price
    ip = init_price or cp
    rmin = running_min if running_min is not None else cp
    rmax = running_max if running_max is not None else cp

    recent_change = 0  # Can't know without price history

    state_a = {
        'current_price': cp, 'init_price': ip,
        'running_min': rmin, 'running_max': rmax,
        'minutes_played': minutes_played, 'recent_change': recent_change,
        'opponent_rank': rank_b, 'player_rank': rank_a,
    }
    state_b = {
        'current_price': 100 - cp, 'init_price': 100 - ip,
        'running_min': 100 - rmax, 'running_max': 100 - rmin,
        'minutes_played': minutes_played, 'recent_change': -recent_change,
        'opponent_rank': rank_a, 'player_rank': rank_b,
    }

    # Get rules (player-specific + global)
    rules_a = await _get_player_rules(db_path, player_a)
    rules_b = await _get_player_rules(db_path, player_b)
    global_rules = await _get_player_rules(db_path, "__GLOBAL__")

    triggered_a = match_rules(rules_a, state_a)
    triggered_b = match_rules(rules_b, state_b)
    global_triggered_a = match_rules(global_rules, state_a)
    global_triggered_b = match_rules(global_rules, state_b)

    player_score_a = compute_score_v2(triggered_a)
    player_score_b = compute_score_v2(triggered_b)
    global_score_a = compute_score_v2(global_triggered_a)
    global_score_b = compute_score_v2(global_triggered_b)

    conf_a = min(len(rules_a) / 20, 1.0)
    conf_b = min(len(rules_b) / 20, 1.0)
    score_a = player_score_a + global_score_a * (1 - conf_a)
    score_b = player_score_b + global_score_b * (1 - conf_b)
    score_diff = score_a - score_b

    # EV-weighted soft sizing with price penalty (v3_penalty)
    abs_diff = abs(score_diff)
    if score_diff > 0:
        buy_side_player = player_a
        buy_price = cp
        buy_side = "A"
    else:
        buy_side_player = player_b
        buy_price = 100 - cp
        buy_side = "B"

    max_size = 5
    ev_per_unit = max(0, abs_diff / 500) * (100 - buy_price - 2) - max(0, 1 - abs_diff / 500) * (buy_price + 2)
    price_penalty = max(0, 1 - ((buy_price - 50) / 25) ** 2)
    contracts = min(max_size, max(0, round(ev_per_unit * price_penalty / 5))) if ev_per_unit > 0 else 0

    if contracts > 0:
        if contracts >= 4:
            strength = "STRONG"
        elif contracts >= 2:
            strength = "MODERATE"
        else:
            strength = "WEAK"
        recommendation = f"{strength} BUY {buy_side_player} x{contracts}"
    else:
        strength = "NO SIGNAL"
        recommendation = "NO TRADE"
        buy_side = None
        buy_price = None
        contracts = 0

    return {
        "player_a": player_a, "rank_a": rank_a,
        "player_b": player_b, "rank_b": rank_b,
        "current_price_a": cp, "current_price_b": 100 - cp,
        "score_a": round(score_a, 1), "score_b": round(score_b, 1), "score_diff": round(score_diff, 1),
        "player_score_a": player_score_a, "player_score_b": player_score_b,
        "global_score_a": round(global_score_a * (1 - conf_a), 1), "global_score_b": round(global_score_b * (1 - conf_b), 1),
        "confidence_a": round(conf_a, 2), "confidence_b": round(conf_b, 2),
        "recommendation": recommendation,
        "buy_side": buy_side, "buy_price": buy_price,
        "contracts": contracts, "strength": strength,
        "triggered_a": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in triggered_a],
        "triggered_b": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in triggered_b],
        "global_triggered_a": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in global_triggered_a],
        "global_triggered_b": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in global_triggered_b],
    }


@router.get("/api/player-profile")
async def player_profile(player: str = Query(...)):
    """Get a player's full rule profile."""
    db_path = app.config.settings.db_path
    player = await _resolve_player(db_path, player)
    rank = await _get_ranking(db_path, player)
    rules = await _get_player_rules(db_path, player)

    return {
        "player": player, "rank": rank,
        "rules": rules,
        "total_rules": len(rules),
    }


@router.get("/api/live-signal/matches")
async def live_matches(q: str = Query("")):
    """List active tennis matches on Kalshi. Optional search filter."""
    client = _get_kalshi_client()
    db_path = app.config.settings.db_path
    results = []
    q_lower = q.strip().lower()

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

            if q_lower and q_lower not in player_a.lower() and q_lower not in player_b.lower():
                continue

            price_a = round(float(event_markets[0].get("last_price_dollars", 0)) * 100)
            volume = int(float(event_markets[0].get("volume", event_markets[0].get("volume_fp", 0))))
            rank_a = await _get_ranking(db_path, player_a)
            rank_b = await _get_ranking(db_path, player_b)

            results.append({
                "event_ticker": event_ticker,
                "ticker_a": event_markets[0]["ticker"],
                "ticker_b": event_markets[1]["ticker"],
                "player_a": player_a,
                "player_b": player_b,
                "rank_a": rank_a,
                "rank_b": rank_b,
                "price_a": price_a,
                "price_b": 100 - price_a,
                "volume": volume,
            })

    results.sort(key=lambda x: x["volume"], reverse=True)
    return {"matches": results}


async def _estimate_match_start(client, ticker_a: str, db_path: str, player_a: str, player_b: str) -> str | None:
    """Get match start time from FlashScore only. No unreliable fallbacks."""

    # 1. Scrape FlashScore live page
    try:
        from app.scraper.flashscore_results import scrape_live_match_start
        fs_time = await scrape_live_match_start(player_a, player_b)
        if fs_time:
            return fs_time
    except Exception as e:
        logger.debug(f"FlashScore live scrape failed: {e}")

    # 2. Check match_results table (FlashScore historical)
    from datetime import datetime as dt
    today = dt.now().strftime("%Y-%m-%d")
    try:
        async with get_db(db_path) as db:
            last_a = player_a.split()[-1] if player_a else ""
            last_b = player_b.split()[-1] if player_b else ""
            cursor = await db.execute(
                """SELECT start_time, match_date FROM match_results
                   WHERE match_date >= ? AND start_time IS NOT NULL
                     AND ((winner LIKE ? AND loser LIKE ?) OR (winner LIKE ? AND loser LIKE ?))
                   ORDER BY match_date DESC LIMIT 1""",
                (today, f"%{last_a}%", f"%{last_b}%", f"%{last_b}%", f"%{last_a}%"),
            )
            row = await cursor.fetchone()
            if row and row[0] and row[1]:
                return f"{row[1]}T{row[0]}:00Z"
    except Exception:
        pass

    # No fallback — return None if FlashScore can't find it
    return None


@router.get("/api/live-signal/poll")
async def live_poll(
    event_ticker: str = Query(...),
    ticker_a: str = Query(...),
    init_price: int = Query(None),
    running_min: int = Query(None),
    running_max: int = Query(None),
    match_start: str = Query(None),
    prev_price: int = Query(None),
):
    """Poll current Kalshi price and compute live signal."""
    client = _get_kalshi_client()
    db_path = app.config.settings.db_path

    try:
        market_data = await client.get_market(ticker_a)
        market = market_data.get("market", market_data)
    except Exception as e:
        return {"error": f"Failed to fetch market: {e}"}

    status = market.get("status", "")
    if status not in ("open", "active", "trading"):
        return {"status": "closed", "market_status": status}

    cp = round(float(market.get("last_price_dollars", 0)) * 100)
    yes_bid = round(float(market.get("yes_bid_dollars", 0)) * 100)
    yes_ask = round(float(market.get("yes_ask_dollars", 0)) * 100)

    player_a = market.get("yes_sub_title", "")
    player_b = ""
    try:
        all_markets = await client.get_markets(event_ticker=event_ticker)
        all_markets.sort(key=lambda m: m["ticker"])
        if len(all_markets) >= 2:
            player_b = all_markets[1].get("yes_sub_title", "")
    except Exception:
        pass

    # Determine match start time — FlashScore is the authoritative source
    if not match_start:
        try:
            from app.scraper.flashscore_results import scrape_live_match_start
            match_start = await scrape_live_match_start(player_a, player_b)
        except Exception as e:
            logger.warning(f"FlashScore scrape failed: {e}")
        if not match_start:
            match_start = await _estimate_match_start(client, ticker_a, db_path, player_a, player_b)

    minutes_played = 0
    if match_start:
        try:
            from datetime import datetime as dt, timezone
            start_dt = dt.fromisoformat(match_start.replace("Z", "+00:00"))
            now_dt = dt.now(timezone.utc)
            minutes_played = max(0, int((now_dt - start_dt).total_seconds() / 60))
        except Exception:
            pass

    ip = init_price if init_price is not None else cp
    rmin = min(running_min, cp) if running_min is not None else cp
    rmax = max(running_max, cp) if running_max is not None else cp
    recent_change = (cp - prev_price) if prev_price is not None else 0

    player_a_resolved = await _resolve_player(db_path, player_a) if player_a else player_a
    player_b_resolved = await _resolve_player(db_path, player_b) if player_b else player_b

    rank_a = await _get_ranking(db_path, player_a_resolved)
    rank_b = await _get_ranking(db_path, player_b_resolved)

    # Ensure A is the higher-ranked player
    swapped = False
    if rank_a and rank_b and rank_a > rank_b:
        player_a_resolved, player_b_resolved = player_b_resolved, player_a_resolved
        rank_a, rank_b = rank_b, rank_a
        cp = 100 - cp
        ip = 100 - ip
        rmin, rmax = 100 - rmax, 100 - rmin
        recent_change = -recent_change
        swapped = True

    state_a = {
        'current_price': cp, 'init_price': ip,
        'running_min': rmin, 'running_max': rmax,
        'minutes_played': minutes_played, 'recent_change': recent_change,
        'opponent_rank': rank_b, 'player_rank': rank_a,
    }
    state_b = {
        'current_price': 100 - cp, 'init_price': 100 - ip,
        'running_min': 100 - rmax, 'running_max': 100 - rmin,
        'minutes_played': minutes_played, 'recent_change': -recent_change,
        'opponent_rank': rank_a, 'player_rank': rank_b,
    }

    rules_a = await _get_player_rules(db_path, player_a_resolved)
    rules_b = await _get_player_rules(db_path, player_b_resolved)
    global_rules = await _get_player_rules(db_path, "__GLOBAL__")

    triggered_a = match_rules(rules_a, state_a)
    triggered_b = match_rules(rules_b, state_b)
    global_triggered_a = match_rules(global_rules, state_a)
    global_triggered_b = match_rules(global_rules, state_b)

    player_score_a = compute_score_v2(triggered_a)
    player_score_b = compute_score_v2(triggered_b)
    global_score_a = compute_score_v2(global_triggered_a)
    global_score_b = compute_score_v2(global_triggered_b)

    conf_a = min(len(rules_a) / 20, 1.0)
    conf_b = min(len(rules_b) / 20, 1.0)
    score_a = player_score_a + global_score_a * (1 - conf_a)
    score_b = player_score_b + global_score_b * (1 - conf_b)
    score_diff = score_a - score_b

    # EV-weighted soft sizing with price penalty (v3_penalty)
    abs_diff = abs(score_diff)
    if score_diff > 0:
        buy_side_player = player_a_resolved
        buy_price = cp
        buy_side = "A"
    else:
        buy_side_player = player_b_resolved
        buy_price = 100 - cp
        buy_side = "B"

    max_size = 5
    ev_per_unit = max(0, abs_diff / 500) * (100 - buy_price - 2) - max(0, 1 - abs_diff / 500) * (buy_price + 2)
    price_penalty = max(0, 1 - ((buy_price - 50) / 25) ** 2)
    contracts = min(max_size, max(0, round(ev_per_unit * price_penalty / 5))) if ev_per_unit > 0 else 0

    if contracts > 0:
        if contracts >= 4:
            strength = "STRONG"
        elif contracts >= 2:
            strength = "MODERATE"
        else:
            strength = "WEAK"
        recommendation = f"{strength} BUY {buy_side_player} x{contracts}"
    else:
        strength = "NO SIGNAL"
        recommendation = "NO TRADE"
        buy_side = None
        buy_price = None
        contracts = 0

    # raw_price: in ticker_a's original orientation (for tracking running_min/max consistently)
    raw_price = (100 - cp) if swapped else cp

    return {
        "status": "open",
        "raw_price": raw_price,
        "yes_bid": yes_bid, "yes_ask": yes_ask,
        "player_a": player_a_resolved, "rank_a": rank_a,
        "player_b": player_b_resolved, "rank_b": rank_b,
        "current_price_a": cp,
        "running_min": min(running_min, raw_price) if running_min is not None else raw_price,
        "running_max": max(running_max, raw_price) if running_max is not None else raw_price,
        "score_a": round(score_a, 1), "score_b": round(score_b, 1),
        "score_diff": round(score_diff, 1),
        "player_score_a": player_score_a, "player_score_b": player_score_b,
        "global_score_a": round(global_score_a * (1 - conf_a), 1),
        "global_score_b": round(global_score_b * (1 - conf_b), 1),
        "confidence_a": round(conf_a, 2), "confidence_b": round(conf_b, 2),
        "recommendation": recommendation,
        "buy_side": buy_side, "buy_price": buy_price,
        "contracts": contracts, "strength": strength,
        "triggered_a": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in triggered_a],
        "triggered_b": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in triggered_b],
        "global_triggered_a": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in global_triggered_a],
        "global_triggered_b": [{"category": r["category"], "condition": r["condition"], "win_rate": r["win_rate"], "sample_size": r["sample_size"]} for r in global_triggered_b],
        "swapped": swapped,
        "match_start": match_start,
        "minutes_played": minutes_played,
    }


@router.get("/api/live-signal/backfill")
async def live_backfill(
    event_ticker: str = Query(...),
    ticker_a: str = Query(...),
    match_start: str = Query(...),
):
    """Backfill price + signal history from match start to now."""
    client = _get_kalshi_client()
    db_path = app.config.settings.db_path
    from datetime import datetime as dt, timezone

    try:
        start_dt = dt.fromisoformat(match_start.replace("Z", "+00:00"))
    except Exception:
        return {"error": "Invalid match_start"}

    # Fetch all trades
    try:
        trades = await client.get_trades(ticker_a)
    except Exception as e:
        return {"error": f"Failed to fetch trades: {e}"}

    if not trades:
        return {"history": []}

    trades_sorted = sorted(trades, key=lambda t: t["created_time"])

    # Get player info
    try:
        market_data = await client.get_market(ticker_a)
        market = market_data.get("market", market_data)
        player_a_raw = market.get("yes_sub_title", "")
        all_markets = await client.get_markets(event_ticker=event_ticker)
        all_markets.sort(key=lambda m: m["ticker"])
        player_b_raw = all_markets[1].get("yes_sub_title", "") if len(all_markets) >= 2 else ""
    except Exception:
        return {"history": []}

    player_a = await _resolve_player(db_path, player_a_raw) if player_a_raw else player_a_raw
    player_b = await _resolve_player(db_path, player_b_raw) if player_b_raw else player_b_raw
    rank_a = await _get_ranking(db_path, player_a)
    rank_b = await _get_ranking(db_path, player_b)

    swapped = False
    if rank_a and rank_b and rank_a > rank_b:
        player_a, player_b = player_b, player_a
        rank_a, rank_b = rank_b, rank_a
        swapped = True

    # Get rules
    rules_a = await _get_player_rules(db_path, player_a)
    rules_b = await _get_player_rules(db_path, player_b)
    global_rules = await _get_player_rules(db_path, "__GLOBAL__")
    conf_a = min(len(rules_a) / 20, 1.0)
    conf_b = min(len(rules_b) / 20, 1.0)

    # Resample trades to 1-min prices from match start
    now_dt = dt.now(timezone.utc)
    total_minutes = int((now_dt - start_dt).total_seconds() / 60)

    minute_prices = {}
    for trade in trades_sorted:
        t = dt.fromisoformat(trade["created_time"].replace("Z", "+00:00"))
        minute = int((t - start_dt).total_seconds() / 60)
        if minute < 0:
            minute = 0
        price = round(float(trade["yes_price_dollars"]) * 100)
        minute_prices[minute] = price

    if not minute_prices:
        return {"history": []}

    # Interpolate and compute signals every 5 minutes
    history = []
    last_price = list(minute_prices.values())[0]
    init_price = None
    rmin = rmax = last_price

    for m in range(0, min(total_minutes + 1, 300), 5):
        # Find closest price
        for mm in range(m, m - 5, -1):
            if mm in minute_prices:
                last_price = minute_prices[mm]
                break

        cp = last_price
        if init_price is None:
            init_price = cp

        rmin = min(rmin, cp)
        rmax = max(rmax, cp)

        # Apply swap
        if swapped:
            s_cp = 100 - cp
            s_ip = 100 - init_price
            s_rmin, s_rmax = 100 - rmax, 100 - rmin
        else:
            s_cp = cp
            s_ip = init_price
            s_rmin, s_rmax = rmin, rmax

        lookback_price = None
        for mm in range(m - 10, m - 5, 1):
            if mm >= 0 and mm in minute_prices:
                lookback_price = minute_prices[mm]
        recent = (cp - lookback_price) if lookback_price is not None else 0
        if swapped:
            recent = -recent

        state_a = {'current_price': s_cp, 'init_price': s_ip,
                    'running_min': s_rmin, 'running_max': s_rmax,
                    'minutes_played': m, 'recent_change': recent,
                    'opponent_rank': rank_b}
        state_b = {'current_price': 100 - s_cp, 'init_price': 100 - s_ip,
                    'running_min': 100 - s_rmax, 'running_max': 100 - s_rmin,
                    'minutes_played': m, 'recent_change': -recent,
                    'opponent_rank': rank_a}

        t_a = match_rules(rules_a, state_a)
        t_b = match_rules(rules_b, state_b)
        gt_a = match_rules(global_rules, state_a)
        gt_b = match_rules(global_rules, state_b)

        ps_a = compute_score_v2(t_a)
        ps_b = compute_score_v2(t_b)
        gs_a = compute_score_v2(gt_a)
        gs_b = compute_score_v2(gt_b)
        sa = ps_a + gs_a * (1 - conf_a)
        sb = ps_b + gs_b * (1 - conf_b)
        diff = sa - sb

        point_dt = start_dt + __import__('datetime').timedelta(minutes=m)
        time_str = point_dt.isoformat()

        history.append({
            "time": time_str,
            "minutes": m,
            "price_a": s_cp,
            "price_b": 100 - s_cp,
            "score_a": round(sa, 1),
            "score_b": round(sb, 1),
            "diff": round(diff, 1),
        })

    return {
        "player_a": player_a, "player_b": player_b,
        "rank_a": rank_a, "rank_b": rank_b,
        "raw_init_price": init_price,
        "history": history,
    }
