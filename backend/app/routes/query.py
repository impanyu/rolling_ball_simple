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

    for col, min_val, max_val in non_cp_filters:
        if min_val is not None:
            conditions.append(f"{col} >= ?")
            params.append(min_val)
        if max_val is not None:
            conditions.append(f"{col} <= ?")
            params.append(max_val)

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
            SELECT e.max_price_after
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
        sql = f"SELECT max_price_after FROM extracted_data {where_clause}"
        final_params = params

    async with get_db(app.config.settings.db_path) as db:
        cursor = await db.execute(sql, final_params)
        rows = await cursor.fetchall()

    values = [row[0] for row in rows]
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

    return QueryResponse(
        total_count=total_count,
        histogram=histogram,
        stats=stats,
    )
