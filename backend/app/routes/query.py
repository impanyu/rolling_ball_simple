import statistics
from fastapi import APIRouter, Query
from app.config import settings
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

    filters = [
        ("initial_price", initial_price_min, initial_price_max),
        ("current_price", current_price_min, current_price_max),
        ("player_ranking", player_ranking_min, player_ranking_max),
        ("opponent_ranking", opponent_ranking_min, opponent_ranking_max),
        ("player_win_rate_3m", player_win_rate_3m_min, player_win_rate_3m_max),
        ("opponent_win_rate_3m", opponent_win_rate_3m_min, opponent_win_rate_3m_max),
    ]

    for col, min_val, max_val in filters:
        if min_val is not None:
            conditions.append(f"{col} >= ?")
            params.append(min_val)
        if max_val is not None:
            conditions.append(f"{col} <= ?")
            params.append(max_val)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT max_price_after FROM extracted_data {where_clause}"

    async with get_db(settings.db_path) as db:
        cursor = await db.execute(sql, params)
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
