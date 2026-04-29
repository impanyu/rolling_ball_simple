import type { QueryFilters, QueryResponse, LookupResult, SimulateResult, ScoreState, MatchUpdateResult } from "./types";

export async function fetchQueryResults(
    filters: QueryFilters
): Promise<QueryResponse> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== null && value !== "") {
            params.set(key, String(value));
        }
    }
    const resp = await fetch(`/api/query?${params.toString()}`);
    if (!resp.ok) {
        throw new Error(`Query failed: ${resp.status}`);
    }
    return resp.json();
}

export async function lookupMatch(playerInput: string): Promise<LookupResult> {
    const resp = await fetch("/api/lookup-match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ player_input: playerInput }),
    });
    if (!resp.ok) throw new Error(`Lookup failed: ${resp.status}`);
    return resp.json();
}

export async function runSimulation(
    p_a: number, p_b: number, score: ScoreState, firstServer: string = "a", num_simulations: number = 10000
): Promise<SimulateResult> {
    const resp = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ p_a, p_b, score, first_server: firstServer, num_simulations }),
    });
    if (!resp.ok) throw new Error(`Simulation failed: ${resp.status}`);
    return resp.json();
}

import type { ServeComponents } from "./types";

export async function runSimulateMax(
    p_a: number, p_b: number, score: ScoreState, firstServer: string = "a", num_simulations: number = 10000
): Promise<QueryResponse & { current_win_prob: number }> {
    const resp = await fetch("/api/simulate-max", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ p_a, p_b, score, first_server: firstServer, num_simulations }),
    });
    if (!resp.ok) throw new Error(`Simulate-max failed: ${resp.status}`);
    return resp.json();
}

export async function rescrapePlayer(
    url: string, player: "a" | "b", surface?: string, opponentRank?: number
): Promise<{ player: string; serve_stats: ServeComponents; error?: string }> {
    const resp = await fetch("/api/rescrape-player", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, player, surface: surface || null, opponent_rank: opponentRank || null }),
    });
    if (!resp.ok) throw new Error(`Rescrape failed: ${resp.status}`);
    return resp.json();
}

export interface GridSearchResult {
    initial: string;
    current: string;
    n: number;
    wins: number;
    p_win: number;
    implied: number;
    excess: number;
    roi: number;
}

export async function fetchGridSearch(minExcess: number = 5, minN: number = 10): Promise<{ results: GridSearchResult[] }> {
    const resp = await fetch(`/api/grid-search?min_excess=${minExcess}&min_n=${minN}`);
    if (!resp.ok) throw new Error(`Grid search failed: ${resp.status}`);
    return resp.json();
}

export interface PlayerWinRate {
    player: string;
    tour: string;
    wins: number;
    losses: number;
    total: number;
    win_rate: number;
    href: string;
    ranking: number | null;
}

export async function fetchPlayerWinRates(minWinRate: number = 80, minMatches: number = 5, days: number = 30): Promise<{ players: PlayerWinRate[]; total_matches: number }> {
    const resp = await fetch(`/api/player-winrates?min_win_rate=${minWinRate}&min_matches=${minMatches}&days=${days}`);
    if (!resp.ok) throw new Error(`Win rates failed: ${resp.status}`);
    return resp.json();
}

export async function refreshWinRates(): Promise<{ inserted: number }> {
    const resp = await fetch("/api/refresh-winrates", { method: "POST" });
    if (!resp.ok) throw new Error(`Refresh failed: ${resp.status}`);
    return resp.json();
}

export async function fetchCloseoutAnalysis(minMatches: number = 3, maxRank: number = 500): Promise<{ players: any[] }> {
    const resp = await fetch(`/api/closeout-analysis?min_matches=${minMatches}&max_rank=${maxRank}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchLiveSignal(params: {
    player_a: string; player_b: string; current_price: number;
    init_price?: number; running_min?: number; running_max?: number; minutes_played?: number;
}): Promise<any> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) qs.set(k, String(v));
    }
    const resp = await fetch(`/api/live-signal?${qs.toString()}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchPlayerProfile(player: string): Promise<any> {
    const resp = await fetch(`/api/player-profile?player=${encodeURIComponent(player)}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchLiveMatches(q: string = ""): Promise<{ matches: any[] }> {
    const resp = await fetch(`/api/live-signal/matches?q=${encodeURIComponent(q)}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function backfillLiveMatch(params: {
    event_ticker: string; ticker_a: string; match_start: string;
}): Promise<any> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) qs.set(k, String(v));
    const resp = await fetch(`/api/live-signal/backfill?${qs.toString()}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function pollLiveMatch(params: {
    event_ticker: string; ticker_a: string;
    init_price?: number; running_min?: number; running_max?: number;
    match_start?: string; prev_price?: number;
}): Promise<any> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) qs.set(k, String(v));
    }
    const resp = await fetch(`/api/live-signal/poll?${qs.toString()}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchPathQuery(params: {
    init_min?: number; init_max?: number;
    current_min?: number; current_max?: number;
    path_min_min?: number; path_min_max?: number;
    path_max_min?: number; path_max_max?: number;
    path_range_min?: number; path_range_max?: number;
    ranked_higher?: boolean;
}): Promise<QueryResponse> {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const resp = await fetch(`/api/path-query?${qs.toString()}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchMatchSignal(playerA: string, playerB: string, initPrice: number): Promise<any> {
    const resp = await fetch(`/api/match-signal?player_a=${encodeURIComponent(playerA)}&player_b=${encodeURIComponent(playerB)}&init_price=${initPrice}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchComebackAnalysis(minMatches: number = 3, maxRank: number = 500): Promise<{ players: any[] }> {
    const resp = await fetch(`/api/comeback-analysis?min_matches=${minMatches}&max_rank=${maxRank}`);
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchActiveMatches(): Promise<{ matches: any[] }> {
    const resp = await fetch("/api/active-matches");
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function monitorStart(): Promise<{ status: string }> {
    const resp = await fetch("/api/monitor-start", { method: "POST" });
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function monitorStop(): Promise<{ status: string }> {
    const resp = await fetch("/api/monitor-stop", { method: "POST" });
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchMonitorStatus(): Promise<{ running: boolean; matches: any[]; trades: any[] }> {
    const resp = await fetch("/api/monitor-status");
    if (!resp.ok) throw new Error(`Failed: ${resp.status}`);
    return resp.json();
}

export async function fetchMatchUpdate(
    matchUrl: string,
    serveAPrior: ServeComponents,
    serveBPrior: ServeComponents,
    statsHistory: Record<string, number>[],
    firstServer: string = "a",
    prevScore: ScoreState | null = null,
    simMode: string = "timeslice",
    num_simulations: number = 10000
): Promise<MatchUpdateResult> {
    const resp = await fetch("/api/match-update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            match_url: matchUrl,
            serve_a_prior: serveAPrior,
            serve_b_prior: serveBPrior,
            stats_history: statsHistory,
            first_server: firstServer,
            prev_score: prevScore,
            sim_mode: simMode,
            num_simulations,
        }),
    });
    if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
    return resp.json();
}
