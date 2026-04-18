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

export interface ScoreState {
    sets: number[];
    games: number[];
    points: number[];
    serving: string;
}

export interface ServeComponents {
    first_in: number;
    first_won: number;
    second_won: number;
    p_serve: number;
    is_default?: boolean;
}

export interface LookupResult {
    player_a: string;
    player_b: string;
    gender: string;
    surface: string | null;
    match_stats: Record<string, number> | null;
    p_a_prior: number;
    p_b_prior: number;
    serve_a_prior: ServeComponents;
    serve_a_updated: ServeComponents;
    serve_b_prior: ServeComponents;
    serve_b_updated: ServeComponents;
    match_found: boolean;
    match_url: string;
    current_score: ScoreState;
    total_points: number;
    p_a_updated: number;
    p_b_updated: number;
    error?: string;
}

export interface TimeSlice {
    horizon: number;
    total_count: number;
    histogram: HistogramBin[];
    stats: Stats;
}

export interface SimulateResult {
    current_win_prob: number;
    slices: TimeSlice[];
    combined: {
        total_count: number;
        histogram: HistogramBin[];
        stats: Stats;
    };
}

export interface MatchUpdateResult {
    current_win_prob: number;
    current_score: ScoreState;
    total_points: number;
    p_a_updated: number;
    p_b_updated: number;
    match_stats: Record<string, number> | null;
    slices: TimeSlice[];
    combined: {
        total_count: number;
        histogram: HistogramBin[];
        stats: Stats;
    };
    error?: string;
}
