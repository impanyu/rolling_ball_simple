import statistics
from fastapi import APIRouter, Query
import app.config
from app.database import get_db
from app.models import QueryResponse, HistogramBin, Stats

router = APIRouter()


@router.get("/api/query", response_model=QueryResponse)
async def query_data(
    initial_price_min: float | None = Query(None),
    initial_price_max: float | None = Query(None),
    current_price_min: float | None = Query(None),
    current_price_max: float | None = Query(None),
    player_ranking_min: int | None = Query(None),
    player_ranking_max: int | None = Query(None),
    opponent_ranking_min: int | None = Query(None),
    opponent_ranking_max: int | None = Query(None),
    player_win_rate_3m_min: float | None = Query(None),
    player_win_rate_3m_max: float | None = Query(None),
    opponent_win_rate_3m_min: float | None = Query(None),
    opponent_win_rate_3m_max: float | None = Query(None),
    ranking_compare: str | None = Query(None),
):
    conditions = []
    params: list = []

    # Non-current_price filters apply to all rows
    non_cp_filters = [
        ("initial_price", initial_price_min, initial_price_max),
        ("player_ranking", player_ranking_min, player_ranking_max),
        ("opponent_ranking", opponent_ranking_min, opponent_ranking_max),
        ("player_win_rate_3m", player_win_rate_3m_min, player_win_rate_3m_max),
        ("opponent_win_rate_3m", opponent_win_rate_3m_min, opponent_win_rate_3m_max),
    ]

    has_initial_filter = initial_price_min is not None or initial_price_max is not None

    for col, min_val, max_val in non_cp_filters:
        if min_val is not None:
            conditions.append(f"{col} >= ?")
            params.append(min_val)
        if max_val is not None:
            conditions.append(f"{col} <= ?")
            params.append(max_val)

    conditions.append("player_ranking IS NOT NULL AND player_ranking <= 2000")
    conditions.append("opponent_ranking IS NOT NULL AND opponent_ranking <= 2000")

    if ranking_compare == "higher":
        conditions.append("player_ranking < opponent_ranking")
    elif ranking_compare == "lower":
        conditions.append("player_ranking > opponent_ranking")

    if has_initial_filter:
        conditions.append("pre_match_trades > 0")


    # current_price filter: only take the FIRST minute per (match_id, player)
    # where current_price enters the query range
    has_cp_filter = current_price_min is not None or current_price_max is not None

    cp_conditions = []
    cp_params: list = []
    if current_price_min is not None:
        cp_conditions.append("current_price >= ?")
        cp_params.append(current_price_min)
    if current_price_max is not None:
        cp_conditions.append("current_price <= ?")
        cp_params.append(current_price_max)

    if has_cp_filter:
        # Use a CTE to find the first minute each (match_id, player) enters the range,
        # then join back to get the max_price_after for that specific minute
        all_conditions = conditions + cp_conditions
        all_params = params + cp_params
        where_clause = ""
        if all_conditions:
            where_clause = "WHERE " + " AND ".join(all_conditions)

        sql = f"""
            WITH first_entry AS (
                SELECT match_id, player, MIN(minute) as first_minute
                FROM extracted_data
                {where_clause}
                GROUP BY match_id, player
            )
            SELECT e.max_price_after, e.won
            FROM extracted_data e
            INNER JOIN first_entry f
                ON e.match_id = f.match_id
                AND e.player = f.player
                AND e.minute = f.first_minute
        """
        final_params = all_params
    else:
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        sql = f"SELECT max_price_after, won FROM extracted_data {where_clause}"
        final_params = params

    async with get_db(app.config.settings.db_path) as db:
        cursor = await db.execute(sql, final_params)
        rows = await cursor.fetchall()

    values = [row[0] for row in rows]
    won_flags = [row[1] for row in rows]
    total_count = len(values)

    bin_size = 5
    histogram = []
    for bin_start in range(0, 100, bin_size):
        bin_end = bin_start + bin_size
        if bin_start == 95:
            count = sum(1 for v in values if bin_start <= v <= bin_end)
        else:
            count = sum(1 for v in values if bin_start <= v < bin_end)
        pct = (count / total_count * 100) if total_count > 0 else 0
        histogram.append(
            HistogramBin(
                bin_start=bin_start,
                bin_end=bin_end,
                count=count,
                percentage=round(pct, 2),
            )
        )

    if total_count > 0:
        stats = Stats(
            mean=round(statistics.mean(values), 2),
            median=round(statistics.median(values), 2),
            std=round(statistics.stdev(values), 2) if total_count > 1 else 0,
        )
    else:
        stats = Stats(mean=0, median=0, std=0)

    win_count = sum(1 for v, w in zip(values, won_flags) if w == 1 or (w is None and v >= 99))
    win_pct = round(win_count / total_count * 100, 1) if total_count > 0 else 0.0

    return QueryResponse(
        total_count=total_count,
        histogram=histogram,
        stats=stats,
        win_count=win_count,
        win_pct=win_pct,
    )


@router.get("/api/grid-search")
async def grid_search(
    min_excess: float = Query(5.0),
    min_n: int = Query(10),
    bin_size: int = Query(5),
):
    async with get_db(app.config.settings.db_path) as db:
        cursor = await db.execute("""
            WITH bucketed AS (
                SELECT match_id, player,
                       CAST(initial_price / ? AS INT) * ? AS ip_bucket,
                       CAST(current_price / ? AS INT) * ? AS cp_bucket,
                       MIN(minute) AS first_minute
                FROM extracted_data
                WHERE pre_match_trades > 0
                  AND player_ranking IS NOT NULL AND player_ranking <= 2000
                  AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                GROUP BY match_id, player, ip_bucket, cp_bucket
            ),
            first_entries AS (
                SELECT b.match_id, b.player, b.ip_bucket, b.cp_bucket, b.first_minute
                FROM bucketed b
                INNER JOIN (
                    SELECT match_id, player, cp_bucket, MIN(first_minute) AS min_minute
                    FROM bucketed
                    GROUP BY match_id, player, cp_bucket
                ) m ON b.match_id = m.match_id AND b.player = m.player
                    AND b.cp_bucket = m.cp_bucket AND b.first_minute = m.min_minute
            )
            SELECT f.ip_bucket, f.cp_bucket,
                   COUNT(*) AS n,
                   SUM(CASE WHEN COALESCE(e.won, CASE WHEN e.max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END) AS wins
            FROM first_entries f
            INNER JOIN extracted_data e
                ON e.match_id = f.match_id AND e.player = f.player AND e.minute = f.first_minute
            GROUP BY f.ip_bucket, f.cp_bucket
        """, (bin_size, bin_size, bin_size, bin_size))
        rows = await cursor.fetchall()

    results = []
    for row in rows:
        ip_start, cp_start, n, wins = row[0], row[1], row[2], row[3]
        ip_end = ip_start + bin_size
        cp_end = cp_start + bin_size
        if n < min_n:
            continue
        p_win = wins / n * 100
        implied = cp_end
        excess = p_win - implied
        if excess < min_excess:
            continue
        roi = (p_win - cp_end - 2) / cp_end * 100 if cp_end > 0 else 0
        results.append({
            "initial": f"{ip_start}-{ip_end}",
            "current": f"{cp_start}-{cp_end}",
            "n": n,
            "wins": wins,
            "p_win": round(p_win, 1),
            "implied": implied,
            "excess": round(excess, 1),
            "roi": round(roi, 1),
        })

    results.sort(key=lambda x: -x["excess"])
    return {"results": results}


@router.get("/api/player-winrates")
async def player_winrates(
    min_win_rate: float = Query(80.0),
    min_matches: int = Query(5),
    days: int = Query(30),
):
    from app.scraper.flashscore_results import get_winrates_from_db
    return await get_winrates_from_db(
        app.config.settings.db_path, min_win_rate, min_matches, days
    )


@router.get("/api/comeback-analysis")
async def comeback_analysis(
    min_matches: int = Query(3),
    max_rank: int = Query(1000),
    min_init_price: int = Query(0),
):
    async with get_db(app.config.settings.db_path) as db:
        cursor = await db.execute("""
            WITH player_drops AS (
                SELECT player, player_ranking,
                       MIN(current_price) as min_price,
                       MAX(CASE WHEN COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END) as won,
                       match_id
                FROM extracted_data
                WHERE player_ranking IS NOT NULL AND player_ranking <= ?
                  AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                  AND initial_price >= ?
                GROUP BY match_id, player
            )
            SELECT player, MIN(player_ranking) as ranking,
                   COUNT(*) as total_matches,
                   SUM(CASE WHEN min_price <= 30 THEN 1 ELSE 0 END) as n30,
                   SUM(CASE WHEN min_price <= 30 AND won = 1 THEN 1 ELSE 0 END) as w30,
                   SUM(CASE WHEN min_price <= 20 THEN 1 ELSE 0 END) as n20,
                   SUM(CASE WHEN min_price <= 20 AND won = 1 THEN 1 ELSE 0 END) as w20,
                   SUM(CASE WHEN min_price <= 15 THEN 1 ELSE 0 END) as n15,
                   SUM(CASE WHEN min_price <= 15 AND won = 1 THEN 1 ELSE 0 END) as w15,
                   SUM(CASE WHEN min_price <= 10 THEN 1 ELSE 0 END) as n10,
                   SUM(CASE WHEN min_price <= 10 AND won = 1 THEN 1 ELSE 0 END) as w10
            FROM player_drops
            GROUP BY player
            HAVING n30 >= ?
            ORDER BY CAST(w30 AS REAL) / n30 DESC
        """, (max_rank, min_init_price, min_matches))
        rows = await cursor.fetchall()

        results = []
        for r in rows:
            player, ranking = r[0], r[1]
            rr = await db.execute(
                "SELECT href FROM flashscore_rankings WHERE ranking = ? LIMIT 1", (ranking,)
            )
            href_row = await rr.fetchone()

            results.append({
                "player": player,
                "ranking": ranking,
                "href": href_row[0] if href_row else "",
                "total_matches": r[2],
                "n30": r[3], "w30": r[4], "rate30": round(r[4]/r[3]*100, 1) if r[3] else 0,
                "n20": r[5], "w20": r[6], "rate20": round(r[6]/r[5]*100, 1) if r[5] else 0,
                "n15": r[7], "w15": r[8], "rate15": round(r[8]/r[7]*100, 1) if r[7] else 0,
                "n10": r[9], "w10": r[10], "rate10": round(r[10]/r[9]*100, 1) if r[9] else 0,
            })

    return {"players": results}


@router.get("/api/closeout-analysis")
async def closeout_analysis(
    min_matches: int = Query(3),
    max_rank: int = Query(1000),
):
    async with get_db(app.config.settings.db_path) as db:
        cursor = await db.execute("""
            WITH player_highs AS (
                SELECT player, player_ranking, match_id,
                       MAX(current_price) as max_price,
                       MAX(CASE WHEN COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END) as won
                FROM extracted_data
                WHERE player_ranking IS NOT NULL AND player_ranking <= ?
                  AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                GROUP BY match_id, player
            )
            SELECT player, MIN(player_ranking) as ranking,
                   COUNT(*) as total_matches,
                   SUM(CASE WHEN max_price >= 70 THEN 1 ELSE 0 END) as n70,
                   SUM(CASE WHEN max_price >= 70 AND won = 1 THEN 1 ELSE 0 END) as w70,
                   SUM(CASE WHEN max_price >= 80 THEN 1 ELSE 0 END) as n80,
                   SUM(CASE WHEN max_price >= 80 AND won = 1 THEN 1 ELSE 0 END) as w80,
                   SUM(CASE WHEN max_price >= 90 THEN 1 ELSE 0 END) as n90,
                   SUM(CASE WHEN max_price >= 90 AND won = 1 THEN 1 ELSE 0 END) as w90
            FROM player_highs
            GROUP BY player
            HAVING n70 >= ?
            ORDER BY CAST(w90 AS REAL) / CASE WHEN n90 > 0 THEN n90 ELSE 1 END DESC
        """, (max_rank, min_matches))
        rows = await cursor.fetchall()

        results = []
        for r in rows:
            player, ranking = r[0], r[1]
            rr = await db.execute(
                "SELECT href FROM flashscore_rankings WHERE ranking = ? LIMIT 1", (ranking,)
            )
            href_row = await rr.fetchone()

            n70, w70, n80, w80, n90, w90 = r[3], r[4], r[5], r[6], r[7], r[8]
            results.append({
                "player": player,
                "ranking": ranking,
                "href": href_row[0] if href_row else "",
                "total_matches": r[2],
                "n70": n70, "w70": w70, "rate70": round(w70/n70*100, 1) if n70 else 0,
                "n80": n80, "w80": w80, "rate80": round(w80/n80*100, 1) if n80 else 0,
                "n90": n90, "w90": w90, "rate90": round(w90/n90*100, 1) if n90 else 0,
            })

    return {"players": results}


@router.get("/api/match-signal")
async def match_signal(
    player_a: str = Query(...),
    player_b: str = Query(...),
    init_price: int = Query(65),
):
    """Collect all signals for a specific matchup."""
    db_path = app.config.settings.db_path

    # Find exact player names in extracted_data first
    async with get_db(db_path) as db:
        async def resolve_name(name_input):
            parts = name_input.strip().split()
            # Try all combinations of parts as first/last name
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
            # Single word - search as last name
            longest = max(parts, key=len).lower() if parts else name_input.lower()
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
            return row[0] if row else name_input

        player_a = await resolve_name(player_a)
        player_b = await resolve_name(player_b)

    # Find rankings after name resolution
    async with get_db(db_path) as db:
        async def find_rank(name):
            c = await db.execute("SELECT ranking FROM flashscore_rankings WHERE player_name = ? LIMIT 1", (name.lower(),))
            r = await c.fetchone()
            if r: return r[0]
            c2 = await db.execute("SELECT DISTINCT player_ranking FROM extracted_data WHERE player = ? AND player_ranking IS NOT NULL LIMIT 1", (name,))
            r2 = await c2.fetchone()
            return r2[0] if r2 else None

        rank_a = await find_rank(player_a)
        rank_b = await find_rank(player_b)

    # Determine who is ranked higher
    if rank_a and rank_b:
        if rank_a <= rank_b:
            fav, fav_rank, dog, dog_rank = player_a, rank_a, player_b, rank_b
        else:
            fav, fav_rank, dog, dog_rank = player_b, rank_b, player_a, rank_a
    else:
        fav, fav_rank, dog, dog_rank = player_a, rank_a, player_b, rank_b

    # Alpha curve: sample current_price from 70-91, step 3
    alpha_curve = []
    async with get_db(db_path) as db:
        for cp in range(70, 92, 3):
            cursor = await db.execute("""
                WITH first_entry AS (
                    SELECT match_id, player, MIN(minute) as first_minute
                    FROM extracted_data
                    WHERE initial_price >= 0 AND initial_price <= ?
                      AND current_price = ?
                      AND pre_match_trades > 0
                      AND player_ranking IS NOT NULL AND player_ranking <= 2000
                      AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                      AND player_ranking < opponent_ranking
                    GROUP BY match_id, player
                )
                SELECT COUNT(*), SUM(CASE WHEN e.COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END)
                FROM extracted_data e
                INNER JOIN first_entry f ON e.match_id = f.match_id AND e.player = f.player AND e.minute = f.first_minute
            """, (init_price, cp))
            row = await cursor.fetchone()
            n, wins = row[0], row[1] or 0
            p_win = wins / n * 100 if n > 0 else 0
            alpha = p_win - cp - 2
            alpha_curve.append({"current_price": cp, "n": n, "p_win": round(p_win, 1), "alpha": round(alpha, 1)})

    # Closeout for favorite
    async with get_db(db_path) as db:
        fav_closeout = {}
        for threshold in [70, 80, 90]:
            cursor = await db.execute("""
                SELECT COUNT(*), SUM(won)
                FROM (
                    SELECT match_id, MAX(current_price) as peak,
                           MAX(CASE WHEN COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END) as won
                    FROM extracted_data
                    WHERE player = ?
                      AND player_ranking IS NOT NULL AND player_ranking <= 2000
                      AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                    GROUP BY match_id
                    HAVING peak >= ?
                )
            """, (fav, threshold))
            row = await cursor.fetchone()
            n, w = row[0], row[1] or 0
            fav_closeout[threshold] = {"n": n, "wins": w, "rate": round(w/n*100, 1) if n > 0 else 0}

        # Comeback for underdog
        dog_comeback = {}
        for threshold in [30, 20, 10]:
            cursor = await db.execute("""
                SELECT COUNT(*), SUM(won)
                FROM (
                    SELECT match_id, MIN(current_price) as trough,
                           MAX(CASE WHEN COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) = 1 THEN 1 ELSE 0 END) as won
                    FROM extracted_data
                    WHERE player = ?
                      AND player_ranking IS NOT NULL AND player_ranking <= 2000
                      AND opponent_ranking IS NOT NULL AND opponent_ranking <= 2000
                    GROUP BY match_id
                    HAVING trough <= ?
                )
            """, (dog, threshold))
            row = await cursor.fetchone()
            n, w = row[0], row[1] or 0
            dog_comeback[threshold] = {"n": n, "wins": w, "rate": round(w/n*100, 1) if n > 0 else 0}

    return {
        "favorite": fav, "fav_rank": fav_rank,
        "underdog": dog, "dog_rank": dog_rank,
        "init_price": init_price,
        "alpha_curve": alpha_curve,
        "fav_closeout": fav_closeout,
        "dog_comeback": dog_comeback,
    }


@router.get("/api/path-query")
async def path_query(
    init_min: float = Query(0),
    init_max: float = Query(70),
    current_min: float = Query(87),
    current_max: float = Query(91),
    path_min_min: float = Query(None),
    path_min_max: float = Query(None),
    path_max_min: float = Query(None),
    path_max_max: float = Query(None),
    path_range_min: float = Query(None),
    path_range_max: float = Query(None),
    ranked_higher: bool = Query(True),
):
    """Path-aware query: every trade is an independent point.
    Features: init_price, current_price, running_min, running_max.
    """
    db_path = app.config.settings.db_path

    conditions = [
        "initial_price >= ? AND initial_price <= ?",
        "current_price >= ? AND current_price <= ?",
        "player_ranking IS NOT NULL AND player_ranking <= 2000",
        "opponent_ranking IS NOT NULL AND opponent_ranking <= 2000",
    ]
    params: list = [init_min, init_max, current_min, current_max]

    if ranked_higher:
        conditions.append("player_ranking < opponent_ranking")
    if path_min_min is not None:
        conditions.append("running_min >= ?")
        params.append(path_min_min)
    if path_min_max is not None:
        conditions.append("running_min <= ?")
        params.append(path_min_max)
    if path_max_min is not None:
        conditions.append("running_max >= ?")
        params.append(path_max_min)
    if path_max_max is not None:
        conditions.append("running_max <= ?")
        params.append(path_max_max)
    if path_range_min is not None:
        conditions.append("running_min >= ?")
        params.append(path_range_min)
    if path_range_max is not None:
        conditions.append("running_max <= ?")
        params.append(path_range_max)

    where = "WHERE " + " AND ".join(conditions)

    # Load matching rows, then deduplicate by "visit" (each entry into range = one point)
    async with get_db(db_path) as db:
        cursor = await db.execute(f"""
            SELECT match_id, player, minute, current_price, max_price_after,
                   COALESCE(won, CASE WHEN max_price_after >= 99 THEN 1 ELSE 0 END) as won
            FROM extracted_data
            {where}
            ORDER BY match_id, player, minute
        """, params)
        matching = await cursor.fetchall()

    # For each match+player, find "visits": consecutive runs in the range
    # Take the first minute of each visit as the data point
    values = []
    wins = 0
    total = 0

    prev_key = None
    prev_minute = -999
    for mid, player, minute, cp, mpa, won in matching:
        key = (mid, player)
        # New visit if: new match OR gap in minutes > 1 (left the range and came back)
        if key != prev_key or minute > prev_minute + 1:
            total += 1
            values.append(mpa)
            if won == 1:
                wins += 1
        prev_key = key
        prev_minute = minute

    # Build histogram
    bin_size = 5
    histogram = []
    for bin_start in range(0, 100, bin_size):
        bin_end = bin_start + bin_size
        if bin_start == 95:
            count = sum(1 for v in values if bin_start <= v <= bin_end)
        else:
            count = sum(1 for v in values if bin_start <= v < bin_end)
        pct = (count / total * 100) if total > 0 else 0
        histogram.append({
            "bin_start": bin_start, "bin_end": bin_end,
            "count": count, "percentage": round(pct, 2),
        })

    if total > 0:
        import statistics as _stats
        mean_val = round(_stats.mean(values), 2)
        median_val = round(_stats.median(values), 2)
        std_val = round(_stats.stdev(values), 2) if total > 1 else 0
    else:
        mean_val = median_val = std_val = 0

    win_pct = round(wins / total * 100, 1) if total > 0 else 0

    return {
        "total_count": total,
        "win_count": wins,
        "win_pct": win_pct,
        "histogram": histogram,
        "stats": {"mean": mean_val, "median": median_val, "std": std_val},
    }


@router.post("/api/refresh-winrates")
async def refresh_winrates(max_per_tour: int = Query(600)):
    from app.scraper.flashscore_results import scrape_and_store_results
    inserted = await scrape_and_store_results(app.config.settings.db_path, max_per_tour=max_per_tour)
    return {"inserted": inserted}
