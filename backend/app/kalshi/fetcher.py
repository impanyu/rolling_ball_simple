import logging
from datetime import datetime, timedelta
from app.database import get_db
from app.stats.sackmann import parse_rankings, parse_matches
from app.stats.player_stats import compute_ranking_at_date, compute_win_rate_3m

logger = logging.getLogger(__name__)


def _detect_match_start(prices: list[tuple[int, float]], density_window: int = 20, density_threshold: int = 5) -> int:
    """Find the index in prices where the match likely started.

    Scans for the first point where at least `density_threshold` trades
    occur within `density_window` minutes — indicating live match trading.
    Returns the index, or 0 if no dense region found.
    """
    for i in range(len(prices)):
        count = sum(1 for m, _ in prices[i:i + density_threshold + 3] if m - prices[i][0] <= density_window)
        if count >= density_threshold:
            return i
    return 0


def _stable_initial_price(pre_prices: list[float], max_std: float = 2.0) -> float | None:
    """Find initial price from a stable window before match start.

    Scans backwards from the end of pre_prices, looking for a window
    of 5-10 trades with std <= max_std. Returns the mean of the first
    stable window found, or the last trade if none found.
    """
    import statistics as _stats
    if not pre_prices:
        return None
    for win_size in [5, 8, 10]:
        if len(pre_prices) < win_size:
            continue
        for end in range(len(pre_prices), win_size - 1, -1):
            window = pre_prices[end - win_size:end]
            if _stats.stdev(window) <= max_std:
                return round(_stats.mean(window), 1)
    return pre_prices[-1]


async def _find_start_from_flashscore(db_path: str, player: str, opponent: str, match_date: str, rows: list) -> int | None:
    """Look up match start time from FlashScore data. Returns trade index or None."""
    player_last = player.split()[-1].lower() if player else ""
    opponent_last = opponent.split()[-1].lower() if opponent else ""
    if not player_last or not opponent_last:
        return None

    async with get_db(db_path) as db:
        cursor = await db.execute(
            """SELECT start_time FROM match_results
               WHERE match_date = ?
                 AND (LOWER(winner) LIKE ? OR LOWER(loser) LIKE ?)
                 AND (LOWER(winner) LIKE ? OR LOWER(loser) LIKE ?)
                 AND start_time IS NOT NULL
               LIMIT 1""",
            (match_date, f"{player_last}%", f"{player_last}%",
             f"{opponent_last}%", f"{opponent_last}%"),
        )
        result = await cursor.fetchone()

    if not result or not result[0]:
        return None

    start_hhmm = result[0]
    try:
        start_hour, start_min = int(start_hhmm.split(":")[0]), int(start_hhmm.split(":")[1])
    except (ValueError, IndexError):
        return None

    # FlashScore times are in local system timezone (CDT = UTC-5)
    # Convert to UTC for comparison with Kalshi timestamps
    import time as _time
    utc_offset_hours = _time.timezone // 3600 if _time.daylight == 0 else _time.altzone // 3600
    start_dt = datetime.fromisoformat(f"{match_date}T{start_hour:02d}:{start_min:02d}:00+00:00")
    start_dt = start_dt + timedelta(hours=utc_offset_hours)

    # Find the last trade before this start time
    for i, r in enumerate(rows):
        trade_ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        if trade_ts >= start_dt:
            return i
    return None


async def extract_match_data(
    db_path: str,
    match_id: str,
    player_stats: dict[str, dict],
) -> None:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT player, opponent, tournament, match_date, minute, price, timestamp "
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

    # Step 1: Find match start
    match_start_idx = await _find_start_from_flashscore(db_path, player, opponent, match_date, rows)
    if match_start_idx is None:
        match_start_idx = _detect_match_start(yes_prices)

    n_pre = match_start_idx
    import statistics as _stats
    pre_prices_vals = [p for _, p in yes_prices[:match_start_idx]] if match_start_idx > 0 else []
    pre_std_yes = _stats.stdev(pre_prices_vals) if len(pre_prices_vals) >= 2 else 0.0

    # Step 2: Linear interpolation helper
    def interpolate_at(raw_prices, target_minute):
        """Get interpolated price at a specific minute."""
        if not raw_prices:
            return None
        if target_minute <= raw_prices[0][0]:
            return raw_prices[0][1]
        if target_minute >= raw_prices[-1][0]:
            return raw_prices[-1][1]
        for i in range(len(raw_prices) - 1):
            m0, p0 = raw_prices[i]
            m1, p1 = raw_prices[i + 1]
            if m0 <= target_minute <= m1:
                if m1 == m0:
                    return p1
                return round(p0 + (p1 - p0) * (target_minute - m0) / (m1 - m0), 1)
        return raw_prices[-1][1]

    def resample_linear(raw_prices):
        if len(raw_prices) < 2:
            return raw_prices[:]
        min_minute = raw_prices[0][0]
        max_minute = raw_prices[-1][0]
        if min_minute == max_minute:
            return raw_prices[:]
        result = []
        raw_idx = 0
        for m in range(min_minute, max_minute + 1):
            while raw_idx < len(raw_prices) - 1 and raw_prices[raw_idx + 1][0] <= m:
                raw_idx += 1
            if raw_idx < len(raw_prices) - 1:
                m0, p0 = raw_prices[raw_idx]
                m1, p1 = raw_prices[raw_idx + 1]
                interp = p0 + (p1 - p0) * (m - m0) / (m1 - m0) if m1 != m0 else p1
                result.append((m, round(interp, 1)))
            else:
                result.append((m, raw_prices[raw_idx][1]))
        return result

    # Step 3: Init price = interpolated price at match start using ALL trades
    start_minute = yes_prices[match_start_idx][0] if match_start_idx < len(yes_prices) else yes_prices[0][0]
    initial_yes = interpolate_at(yes_prices, start_minute)
    if initial_yes is None:
        initial_yes = yes_prices[0][1]

    # Step 4: Only interpolate match-period trades
    match_trades = yes_prices[match_start_idx:]
    if not match_trades:
        match_trades = yes_prices
    match_resampled = resample_linear(match_trades)

    sides = [
        {
            "player": player,
            "opponent": opponent,
            "prices": match_resampled,
            "initial": initial_yes,
            "pre_std": pre_std_yes,
        },
        {
            "player": opponent,
            "opponent": player,
            "prices": [(m, round(100 - p, 1)) for m, p in match_resampled],
            "initial": round(100 - initial_yes, 1),
            "pre_std": pre_std_yes,
        },
    ]

    async with get_db(db_path) as db:
        for side in sides:
            prices = side["prices"]
            initial_price = side["initial"]
            p_name = side["player"].lower()
            o_name = side["opponent"].lower()

            p_stats = player_stats.get(p_name, {})
            o_stats = player_stats.get(o_name, {})

            # Compute suffix max, running min/max for each point
            suffix_max = [0.0] * len(prices)
            suffix_max[-1] = prices[-1][1]
            for i in range(len(prices) - 2, -1, -1):
                suffix_max[i] = max(prices[i][1], suffix_max[i + 1])

            r_min = prices[0][1]
            r_max = prices[0][1]
            running_mins = []
            running_maxs = []
            for _, cp in prices:
                r_min = min(r_min, cp)
                r_max = max(r_max, cp)
                running_mins.append(r_min)
                running_maxs.append(r_max)

            for i, (minute, current_price) in enumerate(prices):
                max_price_after = suffix_max[i]

                await db.execute(
                    "INSERT INTO extracted_data "
                    "(match_id, player, opponent, tournament, match_date, minute, "
                    "initial_price, current_price, max_price_after, "
                    "player_ranking, opponent_ranking, player_win_rate_3m, opponent_win_rate_3m, "
                    "pre_match_std, pre_match_trades, running_min, running_max) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        side["pre_std"],
                        n_pre,
                        running_mins[i],
                        running_maxs[i],
                    ),
                )
        await db.commit()

    logger.info(f"Extracted data for {match_id}: {len(match_resampled)} resampled points x 2 sides (pre={n_pre})")


TENNIS_SERIES = ["KXATPMATCH", "KXWTAMATCH", "KXITFMATCH", "KXITFWMATCH", "KXATPCHALLENGERMATCH", "KXWTACHALLENGERMATCH"]


_sackmann_cache: dict[str, tuple] = {}


def _get_sackmann_data(sackmann_dir: str) -> dict[str, tuple]:
    if not _sackmann_cache:
        for tour in ["atp", "wta"]:
            try:
                repo_dir = f"{sackmann_dir}/tennis_{tour}"
                rankings = parse_rankings(repo_dir, tour)
                matches = parse_matches(repo_dir, tour)
                _sackmann_cache[tour] = (rankings, matches)
                logger.info(f"Cached {tour} Sackmann data: {len(rankings)} rankings, {len(matches)} matches")
            except Exception as e:
                logger.warning(f"Failed to load {tour} Sackmann data: {e}")
    return _sackmann_cache


def get_player_stats_for_match(
    sackmann_dir: str, player: str, opponent: str, match_date_str: str
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    match_date = datetime.strptime(match_date_str, "%Y-%m-%d")
    cache = _get_sackmann_data(sackmann_dir)

    for tour, (rankings, matches) in cache.items():
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

    return result


async def run_full_pipeline(client, db_path: str, sackmann_dir: str, rebuild: bool = False) -> None:
    if rebuild:
        async with get_db(db_path) as db:
            await db.execute("DELETE FROM raw_prices")
            await db.execute("DELETE FROM extracted_data")
            await db.commit()
        logger.info("Cleared all existing data for rebuild")

    event_markets: dict[str, list[dict]] = {}

    for series in TENNIS_SERIES:
        try:
            events = await client.get_events(series_ticker=series)
            logger.info(f"Found {len(events)} events for {series}")
        except Exception as e:
            logger.warning(f"Failed to fetch events for {series}: {e}")
            continue

        for event in events:
            event_ticker = event["event_ticker"]
            try:
                markets = await client.get_markets(event_ticker=event_ticker)
                settled = [m for m in markets if m.get("status") in ("finalized", "settled", "closed")]
                if settled:
                    event_markets.setdefault(event_ticker, []).extend(settled)
            except Exception as e:
                logger.debug(f"Skipping event {event_ticker}: {e}")
                continue

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT DISTINCT match_id FROM raw_prices")
        existing = {row[0] for row in await cursor.fetchall()}

    new_count = 0
    for event_ticker, markets in event_markets.items():
        if event_ticker in existing:
            continue

        seen: set[str] = set()
        unique = []
        for m in markets:
            if m["ticker"] not in seen:
                seen.add(m["ticker"])
                unique.append(m)

        if len(unique) != 2:
            logger.debug(f"Event {event_ticker}: {len(unique)} markets (need 2), skipping")
            continue

        unique.sort(key=lambda m: m["ticker"])
        player_a = unique[0].get("yes_sub_title", "")
        player_b = unique[1].get("yes_sub_title", "")

        if not player_a or not player_b:
            logger.warning(f"Cannot determine player names for {event_ticker}, skipping")
            continue

        open_time = unique[0].get("open_time", "")
        match_date = open_time[:10] if open_time else "unknown"
        start_time = unique[0].get("close_time") or ""

        try:
            trades = await client.get_trades(unique[0]["ticker"])
        except Exception as e:
            logger.error(f"Failed to fetch trades for {unique[0]['ticker']}: {e}")
            continue

        if not trades:
            continue

        trades_sorted = sorted(trades, key=lambda t: t["created_time"])
        minute_prices: dict[int, tuple[float, str]] = {}
        t0 = datetime.fromisoformat(trades_sorted[0]["created_time"].replace("Z", "+00:00"))

        for trade in trades_sorted:
            t = datetime.fromisoformat(trade["created_time"].replace("Z", "+00:00"))
            minute = int((t - t0).total_seconds() / 60)
            price_cents = float(trade["yes_price_dollars"]) * 100
            minute_prices[minute] = (price_cents, trade["created_time"])

        if not minute_prices:
            continue

        async with get_db(db_path) as db:
            for minute in sorted(minute_prices.keys()):
                price, ts = minute_prices[minute]
                await db.execute(
                    "INSERT INTO raw_prices "
                    "(match_id, player, opponent, tournament, match_date, minute, price, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_ticker, player_a, player_b, event_ticker, match_date, minute, price, ts),
                )
            if start_time:
                await db.execute(
                    "INSERT OR REPLACE INTO match_start_times (match_id, start_time) VALUES (?, ?)",
                    (event_ticker, start_time),
                )
            await db.commit()

        player_stats = get_player_stats_for_match(sackmann_dir, player_a, player_b, match_date)
        await extract_match_data(db_path, event_ticker, player_stats)

        # Store actual match result
        result_a = unique[0].get("result", "")
        if result_a in ("yes", "no"):
            won_a = 1 if result_a == "yes" else 0
            async with get_db(db_path) as db:
                await db.execute("UPDATE extracted_data SET won = ? WHERE match_id = ? AND player = ?",
                                 (won_a, event_ticker, player_a))
                await db.execute("UPDATE extracted_data SET won = ? WHERE match_id = ? AND player = ?",
                                 (1 - won_a, event_ticker, player_b))
                await db.commit()

        new_count += 1
        logger.info(f"Processed {event_ticker}: {player_a} vs {player_b}")

    if new_count > 0:
        async with get_db(db_path) as db:
            await db.execute("""UPDATE extracted_data SET player_ranking = (
                SELECT r.ranking FROM flashscore_rankings r WHERE LOWER(extracted_data.player) = r.player_name
            ) WHERE player_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.player) = r.player_name)""")
            await db.execute("""UPDATE extracted_data SET opponent_ranking = (
                SELECT r.ranking FROM flashscore_rankings r WHERE LOWER(extracted_data.opponent) = r.player_name
            ) WHERE opponent_ranking IS NULL
              AND EXISTS (SELECT 1 FROM flashscore_rankings r WHERE LOWER(extracted_data.opponent) = r.player_name)""")
            await db.commit()
        logger.info("Updated rankings for new matches")

    logger.info(f"Pipeline complete: processed {new_count} new events")
