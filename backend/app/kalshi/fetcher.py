import logging
from app.database import get_db

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
