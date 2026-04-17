import { useState, useEffect, useRef } from "react";
import MatchInput from "../components/MatchInput";
import MatchStatus from "../components/MatchStatus";
import Histogram from "../components/Histogram";
import { lookupMatch, runSimulation, fetchMatchUpdate } from "../api";
import type { LookupResult, SimulateResult, QueryResponse } from "../types";

export default function SimulatorPage() {
    const [lookup, setLookup] = useState<LookupResult | null>(null);
    const [simResult, setSimResult] = useState<SimulateResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [simulating, setSimulating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [pA, setPA] = useState(0.64);
    const [pB, setPB] = useState(0.64);
    const [autoUpdating, setAutoUpdating] = useState(false);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const handleLookup = async (input: string) => {
        setLoading(true);
        setError(null);
        setSimResult(null);
        try {
            const result = await lookupMatch(input);
            if (result.error) { setError(result.error); return; }
            setLookup(result);
            setPA(result.p_a_updated);
            setPB(result.p_b_updated);
            setSimulating(true);
            const sim = await runSimulation(result.p_a_updated, result.p_b_updated, result.current_score, 100000);
            setSimResult(sim);
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
                const sim = await runSimulation(newPA, newPB, lookup.current_score, 100000);
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
                lookup.match_url, lookup.serve_a_prior, lookup.serve_b_prior
            );
            if (update.error) return;
            setLookup(prev => prev ? {
                ...prev,
                current_score: update.current_score,
                p_a_updated: update.p_a_updated,
                p_b_updated: update.p_b_updated,
            } : prev);
            setPA(update.p_a_updated);
            setPB(update.p_b_updated);
            setSimResult({
                current_win_prob: update.current_win_prob,
                slices: update.slices,
                combined: update.combined,
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
            intervalRef.current = setInterval(doAutoUpdate, 30000);
            setAutoUpdating(true);
        }
    };

    useEffect(() => { return () => { if (intervalRef.current) clearInterval(intervalRef.current); }; }, []);

    const playerName = lookup?.player_a ?? "";

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
                        autoUpdating={autoUpdating} onToggleAutoUpdate={toggleAutoUpdate} />
                </div>
            )}
            <div style={{ marginTop: 16 }}>
                {simulating && <p style={{ textAlign: "center", color: "#888" }}>Simulating...</p>}

                {simResult && (
                    <>
                        {/* Per-horizon small histograms */}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                            {simResult.slices.map((slice) => {
                                const sliceData: QueryResponse = {
                                    total_count: slice.total_count,
                                    histogram: slice.histogram,
                                    stats: slice.stats,
                                };
                                return (
                                    <div key={slice.horizon} style={{ minHeight: 300 }}>
                                        <Histogram
                                            data={sliceData}
                                            xLabel="P(win) %"
                                            unit="%"
                                            title={`After ${slice.horizon} pts`}
                                            compact
                                            currentProb={simResult.current_win_prob}
                                        />
                                    </div>
                                );
                            })}
                        </div>

                        {/* Weighted combined histogram */}
                        <div style={{ marginTop: 20 }}>
                            <Histogram
                                data={{
                                    total_count: simResult.combined.total_count,
                                    histogram: simResult.combined.histogram,
                                    stats: simResult.combined.stats,
                                }}
                                xLabel="P(win) %"
                                unit="%"
                                title={`Weighted Combined — ${playerName} (1/N weighting)`}
                                currentProb={simResult.current_win_prob}
                            />
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}
