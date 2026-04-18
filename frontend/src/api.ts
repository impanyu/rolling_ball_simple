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
    p_a: number, p_b: number, score: ScoreState, firstServer: string = "a", num_simulations: number = 100000
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
    p_a: number, p_b: number, score: ScoreState, firstServer: string = "a", num_simulations: number = 100000
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

export async function fetchMatchUpdate(
    matchUrl: string,
    serveAPrior: ServeComponents,
    serveBPrior: ServeComponents,
    statsHistory: Record<string, number>[],
    firstServer: string = "a",
    prevScore: ScoreState | null = null,
    simMode: string = "timeslice",
    num_simulations: number = 100000
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
