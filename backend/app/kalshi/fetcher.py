import logging
import re
from datetime import datetime
from app.database import get_db
from app.stats.sackmann import parse_rankings, parse_matches
from app.stats.player_stats import compute_ranking_at_date, compute_win_rate_3m

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

    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT DISTINCT match_id FROM raw_prices")
        existing = {row[0] for row in await cursor.fetchall()}

    seen_tickers: set[str] = set()
    unique_markets = []
    for m in all_markets:
        if m["ticker"] not in seen_tickers:
            seen_tickers.add(m["ticker"])
            unique_markets.append(m)
    all_markets = unique_markets

    new_markets = [m for m in all_markets if m["ticker"] not in existing]
    logger.info(f"Found {len(new_markets)} new settled markets to process")

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

        player_stats = get_player_stats_for_match(
            sackmann_dir, player, opponent, match_date
        )

        await extract_match_data(db_path, ticker, player_stats)
        logger.info(f"Processed {ticker}: {player} vs {opponent}")
