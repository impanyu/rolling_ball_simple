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
            const update = await fetchMatchUpdate(lookup.match_url, lookup.p_a_prior, lookup.p_b_prior);
            if (update.error) return;
            setLookup(prev => prev ? { ...prev, current_score: update.current_score, p_a_updated: update.p_a_updated, p_b_updated: update.p_b_updated } : prev);
            setPA(update.p_a_updated);
            setPB(update.p_b_updated);
            setSimResult({ current_win_prob: update.current_win_prob, total_count: update.total_count, histogram: update.histogram, stats: update.stats });
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

    const histogramData: QueryResponse | null = simResult
        ? { total_count: simResult.total_count, histogram: simResult.histogram, stats: simResult.stats }
        : null;

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
                <Histogram
                    data={histogramData}
                    xLabel="Max Win Probability (%)"
                    unit="%"
                    title={lookup ? `Max Win Probability — ${lookup.player_a}` : "Max Win Probability Distribution"}
                />
            </div>
        </div>
    );
}
