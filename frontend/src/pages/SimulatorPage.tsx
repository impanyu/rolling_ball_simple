import { useState, useEffect, useRef } from "react";
import MatchInput from "../components/MatchInput";
import MatchStatus from "../components/MatchStatus";
import Histogram from "../components/Histogram";
import WinProbChart from "../components/WinProbChart";
import DeltaCurve from "../components/DeltaCurve";
import { lookupMatch, runSimulation, runSimulateMax, fetchMatchUpdate, rescrapePlayer } from "../api";
import type { LookupResult, SimulateResult, QueryResponse, HistogramBin } from "../types";

function flipHistogram(histogram: HistogramBin[]): HistogramBin[] {
    const flipped = histogram.map((bin) => ({
        ...bin,
        bin_start: 100 - bin.bin_end,
        bin_end: 100 - bin.bin_start,
    }));
    return flipped.reverse();
}

function flipStats(stats: { mean: number; median: number; std: number }): { mean: number; median: number; std: number } {
    return {
        mean: Math.round((100 - stats.mean) * 100) / 100,
        median: Math.round((100 - stats.median) * 100) / 100,
        std: stats.std,
    };
}

interface ProbPoint {
    points: number;
    prob: number;
}

// Session storage helpers
function loadSession<T>(key: string, fallback: T): T {
    try {
        const v = sessionStorage.getItem(`sim_${key}`);
        return v ? JSON.parse(v) : fallback;
    } catch { return fallback; }
}
function saveSession(key: string, value: unknown) {
    try { sessionStorage.setItem(`sim_${key}`, JSON.stringify(value)); } catch {}
}

export default function SimulatorPage() {
    const [lookup, setLookup] = useState<LookupResult | null>(() => loadSession("lookup", null));
    const [simResult, setSimResult] = useState<SimulateResult | null>(() => loadSession("simResult", null));
    const [loading, setLoading] = useState(false);
    const [simulating, setSimulating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [pA, setPA] = useState(() => loadSession("pA", 0.64));
    const [pB, setPB] = useState(() => loadSession("pB", 0.64));
    const [autoUpdating, setAutoUpdating] = useState(false);
    const [firstServer, setFirstServer] = useState<"a" | "b">(() => loadSession("firstServer", "a"));
    const [viewPlayer, setViewPlayer] = useState<"a" | "b">(() => loadSession("viewPlayer", "a"));
    const [probHistory, setProbHistory] = useState<ProbPoint[]>(() => loadSession("probHistory", []));
    const [urlA, setUrlA] = useState("");
    const [urlB, setUrlB] = useState("");
    const [rescraping, setRescraping] = useState(false);
    const [statsHistory, setStatsHistory] = useState<Record<string, number>[]>(() => loadSession("statsHistory", []));
    const [simTab, setSimTab] = useState<"timeslice" | "maxprob">(() => loadSession("simTab", "timeslice"));
    const [maxResult, setMaxResult] = useState<(QueryResponse & { current_win_prob: number }) | null>(() => loadSession("maxResult", null));
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Persist key state to sessionStorage
    useEffect(() => { saveSession("lookup", lookup); }, [lookup]);
    useEffect(() => { saveSession("simResult", simResult); }, [simResult]);
    useEffect(() => { saveSession("maxResult", maxResult); }, [maxResult]);
    useEffect(() => { saveSession("pA", pA); }, [pA]);
    useEffect(() => { saveSession("pB", pB); }, [pB]);
    useEffect(() => { saveSession("firstServer", firstServer); }, [firstServer]);
    useEffect(() => { saveSession("viewPlayer", viewPlayer); }, [viewPlayer]);
    useEffect(() => { saveSession("probHistory", probHistory); }, [probHistory]);
    useEffect(() => { saveSession("statsHistory", statsHistory); }, [statsHistory]);
    useEffect(() => { saveSession("simTab", simTab); }, [simTab]);

    const handleLookup = async (input: string) => {
        // Stop any running auto-update from previous match
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }
        setAutoUpdating(false);
        setLoading(true);
        setError(null);
        setSimResult(null);
        setProbHistory([]);
        setStatsHistory([]);
        try {
            const result = await lookupMatch(input);
            if (result.error) { setError(result.error); return; }
            setLookup(result);
            setPA(result.p_a_updated);
            setPB(result.p_b_updated);
            if (result.match_stats) setStatsHistory([result.match_stats]);
            setSimulating(true);
            const [sim, maxSim] = await Promise.all([
                runSimulation(result.p_a_updated, result.p_b_updated, result.current_score, firstServer, 100000),
                runSimulateMax(result.p_a_updated, result.p_b_updated, result.current_score, firstServer, 100000),
            ]);
            setSimResult(sim);
            setMaxResult(maxSim);
            setProbHistory([{ points: result.total_points || 0, prob: sim.current_win_prob }]);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Lookup failed");
        } finally {
            setLoading(false);
            setSimulating(false);
        }
    };

    const handlePChange = async (newPA: number, newPB: number) => {
        setPA(newPA);
        setPB(newPB);
        if (lookup) {
            setSimulating(true);
            try {
                const sim = await runSimulation(newPA, newPB, lookup.current_score, firstServer, 100000);
                setSimResult(sim);
            } catch (err) {
                setError(err instanceof Error ? err.message : "Simulation failed");
            } finally {
                setSimulating(false);
            }
        }
    };

    const doAutoUpdate = async () => {
        if (!lookup?.match_url) return;
        try {
            const update = await fetchMatchUpdate(
                lookup.match_url, lookup.serve_a_prior, lookup.serve_b_prior, statsHistory, firstServer,
                lookup.current_score
            );
            if (update.error) return;
            if (!update.changed) return;
            if (update.match_stats) {
                setStatsHistory(prev => [...prev, update.match_stats!]);
            }
            setLookup(prev => prev ? {
                ...prev,
                current_score: update.current_score,
                p_a_updated: update.p_a_updated,
                p_b_updated: update.p_b_updated,
                serve_a_updated: update.serve_a_updated ?? prev.serve_a_updated,
                serve_b_updated: update.serve_b_updated ?? prev.serve_b_updated,
            } : prev);
            setPA(update.p_a_updated);
            setPB(update.p_b_updated);
            setSimResult({
                current_win_prob: update.current_win_prob,
                slices: update.slices,
                combined: update.combined,
            });
            // Also update max prob simulation
            if (lookup) {
                const maxSim = await runSimulateMax(update.p_a_updated, update.p_b_updated, update.current_score, firstServer, 100000);
                setMaxResult(maxSim);
            }
            setProbHistory(prev => {
                const tp = update.total_points;
                // Skip if total_points is missing/zero but we already have real data
                if (!tp && prev.length > 0 && prev[prev.length - 1].points > 0) {
                    return prev;
                }
                // Skip if points went backwards (stale read)
                if (prev.length > 0 && tp < prev[prev.length - 1].points) {
                    return prev;
                }
                // Same point count as last entry — update in place
                if (prev.length > 0 && prev[prev.length - 1].points === tp) {
                    const updated = [...prev];
                    updated[updated.length - 1] = { points: tp, prob: update.current_win_prob };
                    return updated;
                }
                return [...prev, { points: tp, prob: update.current_win_prob }];
            });
        } catch { /* silent fail on auto-update */ }
    };

    const toggleAutoUpdate = () => {
        if (autoUpdating) {
            if (intervalRef.current) clearInterval(intervalRef.current);
            intervalRef.current = null;
            setAutoUpdating(false);
        } else {
            doAutoUpdate();
            intervalRef.current = setInterval(doAutoUpdate, 5000);
            setAutoUpdating(true);
        }
    };

    useEffect(() => { return () => { if (intervalRef.current) clearInterval(intervalRef.current); }; }, []);

    const isFlipped = viewPlayer === "b";
    const viewName = lookup ? (isFlipped ? lookup.player_b : lookup.player_a) : "";
    const currentProb = simResult
        ? (isFlipped ? 100 - simResult.current_win_prob : simResult.current_win_prob)
        : null;

    const viewHistory = probHistory.map(pt => ({
        points: pt.points,
        prob: isFlipped ? 100 - pt.prob : pt.prob,
    }));

    function toViewData(histogram: HistogramBin[], stats: { mean: number; median: number; std: number }, count: number): QueryResponse {
        return {
            total_count: count,
            histogram: isFlipped ? flipHistogram(histogram) : histogram,
            stats: isFlipped ? flipStats(stats) : stats,
        };
    }

    return (
        <div>
            <MatchInput onLookup={handleLookup} loading={loading} />
            {error && (
                <div style={{ marginTop: 16, padding: 12, background: "#fee", borderRadius: 6, color: "#c00" }}>{error}</div>
            )}
            {lookup && (
                <div style={{ marginTop: 16 }}>
                    <MatchStatus lookup={lookup} pA={pA} pB={pB} onPChange={handlePChange}
                        currentWinProb={simResult?.current_win_prob ?? null}
                        viewPlayer={viewPlayer}
                        autoUpdating={autoUpdating} onToggleAutoUpdate={toggleAutoUpdate} />
                </div>
            )}

            {/* Missing player URL prompt */}
            {lookup && (lookup.serve_a_prior?.is_default || lookup.serve_b_prior?.is_default) && (
                <div style={{ marginTop: 16, padding: 16, border: "1px solid #f0ad4e", borderRadius: 8, background: "#fef9e7" }}>
                    <p style={{ margin: 0, fontWeight: 600, color: "#856404" }}>
                        Could not find serve stats on Tennis Abstract for:
                    </p>
                    {lookup.serve_a_prior?.is_default && (
                        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                            <label style={{ minWidth: 120 }}>{lookup.player_a}:</label>
                            <input
                                type="text"
                                value={urlA}
                                onChange={(e) => setUrlA(e.target.value)}
                                placeholder="Paste Tennis Abstract URL"
                                style={{ flex: 1, padding: "6px 10px" }}
                            />
                        </div>
                    )}
                    {lookup.serve_b_prior?.is_default && (
                        <div style={{ marginTop: 8, display: "flex", gap: 8, alignItems: "center" }}>
                            <label style={{ minWidth: 120 }}>{lookup.player_b}:</label>
                            <input
                                type="text"
                                value={urlB}
                                onChange={(e) => setUrlB(e.target.value)}
                                placeholder="Paste Tennis Abstract URL"
                                style={{ flex: 1, padding: "6px 10px" }}
                            />
                        </div>
                    )}
                    <button
                        disabled={rescraping || (!urlA && !urlB)}
                        onClick={async () => {
                            setRescraping(true);
                            try {
                                if (urlA && lookup.serve_a_prior?.is_default) {
                                    const res = await rescrapePlayer(urlA, "a", lookup.surface ?? undefined);
                                    if (!res.error && res.serve_stats) {
                                        setLookup(prev => prev ? {
                                            ...prev,
                                            serve_a_prior: { ...res.serve_stats, is_default: undefined },
                                            serve_a_updated: { ...res.serve_stats, is_default: undefined },
                                            p_a_prior: res.serve_stats.p_serve,
                                            p_a_updated: res.serve_stats.p_serve,
                                        } : prev);
                                        setPA(res.serve_stats.p_serve);
                                    }
                                }
                                if (urlB && lookup.serve_b_prior?.is_default) {
                                    const res = await rescrapePlayer(urlB, "b", lookup.surface ?? undefined);
                                    if (!res.error && res.serve_stats) {
                                        setLookup(prev => prev ? {
                                            ...prev,
                                            serve_b_prior: { ...res.serve_stats, is_default: undefined },
                                            serve_b_updated: { ...res.serve_stats, is_default: undefined },
                                            p_b_prior: res.serve_stats.p_serve,
                                            p_b_updated: res.serve_stats.p_serve,
                                        } : prev);
                                        setPB(res.serve_stats.p_serve);
                                    }
                                }
                                // Re-run simulation with new p values
                                if (lookup) {
                                    const sim = await runSimulation(pA, pB, lookup.current_score, firstServer, 100000);
                                    setSimResult(sim);
                                }
                            } catch (err) {
                                setError(err instanceof Error ? err.message : "Rescrape failed");
                            } finally {
                                setRescraping(false);
                            }
                        }}
                        style={{ marginTop: 12, padding: "6px 16px", cursor: rescraping ? "not-allowed" : "pointer" }}
                    >
                        {rescraping ? "Fetching..." : "Fetch Stats"}
                    </button>
                </div>
            )}

            {/* First server + Player perspective selector */}
            {lookup && (
                <div style={{ marginTop: 16, display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: 600 }}>First server:</span>
                        <button
                            onClick={async () => {
                                setFirstServer("a");
                                if (lookup && simResult) {
                                    const sim = await runSimulation(pA, pB, lookup.current_score, "a", 100000);
                                    setSimResult(sim);
                                }
                            }}
                            style={{
                                padding: "4px 12px", border: "1px solid #888", borderRadius: 4, cursor: "pointer",
                                background: firstServer === "a" ? "#555" : "white",
                                color: firstServer === "a" ? "white" : "#555", fontSize: 13,
                            }}
                        >
                            {lookup.player_a.split(" ").pop()}
                        </button>
                        <button
                            onClick={async () => {
                                setFirstServer("b");
                                if (lookup && simResult) {
                                    const sim = await runSimulation(pA, pB, lookup.current_score, "b", 100000);
                                    setSimResult(sim);
                                }
                            }}
                            style={{
                                padding: "4px 12px", border: "1px solid #888", borderRadius: 4, cursor: "pointer",
                                background: firstServer === "b" ? "#555" : "white",
                                color: firstServer === "b" ? "white" : "#555", fontSize: 13,
                            }}
                        >
                            {lookup.player_b.split(" ").pop()}
                        </button>
                    </div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontWeight: 600 }}>View perspective:</span>
                    <button
                        onClick={() => setViewPlayer("a")}
                        style={{
                            padding: "6px 16px", border: "1px solid #3498db", borderRadius: 4, cursor: "pointer",
                            background: viewPlayer === "a" ? "#3498db" : "white",
                            color: viewPlayer === "a" ? "white" : "#3498db",
                        }}
                    >
                        {lookup.player_a.split(" ").pop()}
                    </button>
                    <button
                        onClick={() => setViewPlayer("b")}
                        style={{
                            padding: "6px 16px", border: "1px solid #e74c3c", borderRadius: 4, cursor: "pointer",
                            background: viewPlayer === "b" ? "#e74c3c" : "white",
                            color: viewPlayer === "b" ? "white" : "#e74c3c",
                        }}
                    >
                        {lookup.player_b.split(" ").pop()}
                    </button>
                    </div>
                </div>
            )}

            {/* Live win probability chart */}
            {probHistory.length > 0 && (
                <div style={{ marginTop: 16 }}>
                    <WinProbChart data={viewHistory} playerName={viewName} />
                </div>
            )}

            {/* Simulation mode tabs */}
            {(simResult || maxResult) && (
                <div style={{ marginTop: 16, display: "flex", gap: 0, borderBottom: "2px solid #ddd" }}>
                    <button
                        onClick={() => setSimTab("timeslice")}
                        style={{
                            padding: "8px 20px", border: "none", cursor: "pointer", fontSize: 14, fontWeight: 600,
                            background: simTab === "timeslice" ? "white" : "#f0f0f0",
                            borderBottom: simTab === "timeslice" ? "2px solid #3498db" : "2px solid transparent",
                            color: simTab === "timeslice" ? "#3498db" : "#888",
                        }}
                    >
                        Time Slices
                    </button>
                    <button
                        onClick={() => setSimTab("maxprob")}
                        style={{
                            padding: "8px 20px", border: "none", cursor: "pointer", fontSize: 14, fontWeight: 600,
                            background: simTab === "maxprob" ? "white" : "#f0f0f0",
                            borderBottom: simTab === "maxprob" ? "2px solid #e74c3c" : "2px solid transparent",
                            color: simTab === "maxprob" ? "#e74c3c" : "#888",
                        }}
                    >
                        Max Prob (100 pts)
                    </button>
                </div>
            )}

            <div style={{ marginTop: 16 }}>
                {simulating && <p style={{ textAlign: "center", color: "#888" }}>Simulating...</p>}

                {simTab === "maxprob" && maxResult && (
                    <Histogram
                        data={{ total_count: maxResult.total_count, histogram: isFlipped ? flipHistogram(maxResult.histogram) : maxResult.histogram, stats: isFlipped ? flipStats(maxResult.stats) : maxResult.stats }}
                        xLabel="Max P(win) %"
                        unit="%"
                        title={`Max Win Probability in next 100 pts — ${viewName}`}
                        currentProb={currentProb ?? undefined}
                    />
                )}

                {simTab === "timeslice" && simResult && (
                    <>
                        {/* Per-horizon small histograms (collapsible) */}
                        <details style={{ marginBottom: 12 }}>
                            <summary style={{ cursor: "pointer", fontWeight: 600, padding: "8px 0", color: "#555" }}>
                                Per-horizon histograms ({simResult.slices.map(s => s.horizon).join(" / ")} pts)
                            </summary>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginTop: 8 }}>
                                {simResult.slices.map((slice) => (
                                    <div key={slice.horizon} style={{ minHeight: 300 }}>
                                        <Histogram
                                            data={toViewData(slice.histogram, slice.stats, slice.total_count)}
                                            xLabel="P(win) %"
                                            unit="%"
                                            title={`After ${slice.horizon} pts`}
                                            compact
                                            currentProb={currentProb ?? undefined}
                                        />
                                    </div>
                                ))}
                            </div>
                        </details>

                        {/* Weighted combined histogram */}
                        <div style={{ marginTop: 20 }}>
                            <Histogram
                                data={toViewData(simResult.combined.histogram, simResult.combined.stats, simResult.combined.total_count)}
                                xLabel="P(win) %"
                                unit="%"
                                title={`Weighted Combined — ${viewName} (1/N weighting)`}
                                currentProb={currentProb ?? undefined}
                            />
                        </div>

                        {/* Delta cumulative curve */}
                        {currentProb !== null && (
                            <div style={{ marginTop: 20 }}>
                                <DeltaCurve
                                    histogram={toViewData(simResult.combined.histogram, simResult.combined.stats, simResult.combined.total_count).histogram}
                                    currentProb={currentProb}
                                    playerName={viewName}
                                />
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
