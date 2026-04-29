from pydantic import BaseModel


class QueryParams(BaseModel):
    initial_price_min: float | None = None
    initial_price_max: float | None = None
    current_price_min: float | None = None
    current_price_max: float | None = None
    player_ranking_min: int | None = None
    player_ranking_max: int | None = None
    opponent_ranking_min: int | None = None
    opponent_ranking_max: int | None = None
    player_win_rate_3m_min: float | None = None
    player_win_rate_3m_max: float | None = None
    opponent_win_rate_3m_min: float | None = None
    opponent_win_rate_3m_max: float | None = None


class HistogramBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int
    percentage: float


class Stats(BaseModel):
    mean: float
    median: float
    std: float


class QueryResponse(BaseModel):
    total_count: int
    histogram: list[HistogramBin]
    stats: Stats
    win_count: int = 0
    win_pct: float = 0.0
