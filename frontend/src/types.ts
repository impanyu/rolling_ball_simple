export interface HistogramBin {
    bin_start: number;
    bin_end: number;
    count: number;
    percentage: number;
}

export interface Stats {
    mean: number;
    median: number;
    std: number;
}

export interface QueryResponse {
    total_count: number;
    histogram: HistogramBin[];
    stats: Stats;
}

export interface QueryFilters {
    initial_price_min?: number;
    initial_price_max?: number;
    current_price_min?: number;
    current_price_max?: number;
    player_ranking_min?: number;
    player_ranking_max?: number;
    opponent_ranking_min?: number;
    opponent_ranking_max?: number;
    player_win_rate_3m_min?: number;
    player_win_rate_3m_max?: number;
    opponent_win_rate_3m_min?: number;
    opponent_win_rate_3m_max?: number;
}
