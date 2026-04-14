import type { QueryFilters, QueryResponse } from "./types";

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
