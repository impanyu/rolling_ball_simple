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
    p_a: number, p_b: number, score: ScoreState, num_simulations: number = 100000
): Promise<SimulateResult> {
    const resp = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ p_a, p_b, score, num_simulations }),
    });
    if (!resp.ok) throw new Error(`Simulation failed: ${resp.status}`);
    return resp.json();
}

import type { ServeComponents } from "./types";

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
    serveA: ServeComponents,
    serveB: ServeComponents,
    num_simulations: number = 100000
): Promise<MatchUpdateResult> {
    const params = new URLSearchParams({
        match_url: matchUrl,
        a_first_in: String(serveA.first_in),
        a_first_won: String(serveA.first_won),
        a_second_won: String(serveA.second_won),
        b_first_in: String(serveB.first_in),
        b_first_won: String(serveB.first_won),
        b_second_won: String(serveB.second_won),
        num_simulations: String(num_simulations),
    });
    const resp = await fetch(`/api/match-update?${params}`);
    if (!resp.ok) throw new Error(`Update failed: ${resp.status}`);
    return resp.json();
}
