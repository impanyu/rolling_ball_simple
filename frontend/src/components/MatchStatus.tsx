import type { LookupResult, ScoreState } from "../types";

interface Props {
    lookup: LookupResult;
    pA: number;
    pB: number;
    onPChange: (pA: number, pB: number) => void;
    currentWinProb: number | null;
    viewPlayer: "a" | "b";
    autoUpdating: boolean;
    onToggleAutoUpdate: () => void;
    pMaxUpsideRatio?: number | null;
    pUpsideRatio?: number | null;
    combinedDelta?: number | null;
}

const POINT_LABELS = ["0", "15", "30", "40", "AD"];

function formatScore(score: ScoreState, _playerA: string, _playerB: string): string {
    const sets = score.sets.join("-");
    const games = score.games.join("-");
    const pa = score.points[0];
    const pb = score.points[1];
    const isTiebreak = score.games[0] === 6 && score.games[1] === 6;
    const points = isTiebreak
        ? `${pa}-${pb} (tiebreak)`
        : `${POINT_LABELS[pa] ?? pa}-${POINT_LABELS[pb] ?? pb}`;
    return `Sets: ${sets}  Games: ${games}  Points: ${points}`;
}

export default function MatchStatus({
    lookup, pA, pB, onPChange, currentWinProb, viewPlayer, autoUpdating, onToggleAutoUpdate,
    pMaxUpsideRatio, pUpsideRatio, combinedDelta,
}: Props) {
    const viewName = viewPlayer === "a" ? lookup.player_a.split(" ").pop() : lookup.player_b.split(" ").pop();
    const displayProb = currentWinProb !== null
        ? (viewPlayer === "b" ? 100 - currentWinProb : currentWinProb)
        : null;
    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>
                {lookup.player_a} vs {lookup.player_b}
            </h2>
            <p style={{ fontSize: 18, fontFamily: "monospace" }}>
                {formatScore(lookup.current_score, lookup.player_a, lookup.player_b)}
            </p>
            {!lookup.match_found && (
                <p style={{ color: "#888" }}>No live match found. Using default score 0-0.</p>
            )}
            <table style={{ marginTop: 12, fontSize: 14, borderCollapse: "collapse" }}>
                <thead>
                    <tr style={{ borderBottom: "1px solid #ddd" }}>
                        <th style={{ textAlign: "left", padding: "4px 12px" }}></th>
                        <th style={{ padding: "4px 12px" }}>1st In</th>
                        <th style={{ padding: "4px 12px" }}>1st Won</th>
                        <th style={{ padding: "4px 12px" }}>2nd Won</th>
                        <th style={{ padding: "4px 12px" }}>window</th>
                        <th style={{ padding: "4px 12px" }}>p</th>
                    </tr>
                </thead>
                <tbody>
                    {[
                        { name: lookup.player_a.split(" ").pop(), prior: lookup.serve_a_prior, updated: lookup.serve_a_updated, isA: true },
                        { name: lookup.player_b.split(" ").pop(), prior: lookup.serve_b_prior, updated: lookup.serve_b_updated, isA: false },
                    ].map(({ name, prior, updated, isA }) => (
                        <tr key={name} style={{ borderBottom: "1px solid #eee" }}>
                            <td style={{ fontWeight: 600, padding: "4px 12px" }}>{name}</td>
                            <td style={{ padding: "4px 12px", textAlign: "center" }}>
                                <span style={{ color: "#888" }}>{(prior.first_in * 100).toFixed(1)}%</span>
                                {" → "}<strong>{(updated.first_in * 100).toFixed(1)}%</strong>
                            </td>
                            <td style={{ padding: "4px 12px", textAlign: "center" }}>
                                <span style={{ color: "#888" }}>{(prior.first_won * 100).toFixed(1)}%</span>
                                {" → "}<strong>{(updated.first_won * 100).toFixed(1)}%</strong>
                            </td>
                            <td style={{ padding: "4px 12px", textAlign: "center" }}>
                                <span style={{ color: "#888" }}>{(prior.second_won * 100).toFixed(1)}%</span>
                                {" → "}<strong>{(updated.second_won * 100).toFixed(1)}%</strong>
                            </td>
                            <td style={{ padding: "4px 12px", textAlign: "center", fontSize: 13 }}>
                                {(updated as any).window_size != null ? `${(updated as any).window_size} srv` : "—"}
                            </td>
                            <td style={{ padding: "4px 12px", textAlign: "center" }}>
                                <input type="number" step={0.001}
                                    value={isA ? pA : pB}
                                    onChange={(e) => isA ? onPChange(Number(e.target.value), pB) : onPChange(pA, Number(e.target.value))}
                                    style={{ width: 70, padding: "2px 6px" }} />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {displayProb !== null && (
                <div style={{ fontSize: 18, marginTop: 12 }}>
                    Current P({viewName} wins):{" "}
                    <strong>{displayProb.toFixed(1)}%</strong>
                    {pMaxUpsideRatio != null && (
                        <span style={{ marginLeft: 16, fontSize: 14, color: pMaxUpsideRatio >= 1 ? "#27ae60" : "#e74c3c" }}>
                            P(max upside) ratio: <strong>{pMaxUpsideRatio.toFixed(2)}</strong>
                        </span>
                    )}
                    {pUpsideRatio != null && (
                        <span style={{ marginLeft: 16, fontSize: 14, color: pUpsideRatio >= 1 ? "#27ae60" : "#e74c3c" }}>
                            P(upside) ratio: <strong>{pUpsideRatio.toFixed(2)}</strong>
                        </span>
                    )}
                    {combinedDelta != null && (
                        <span style={{ marginLeft: 16, fontSize: 14, color: combinedDelta >= 0 ? "#27ae60" : "#e74c3c" }}>
                            &Delta;E: <strong>{combinedDelta >= 0 ? "+" : ""}{combinedDelta.toFixed(1)}%</strong>
                        </span>
                    )}
                </div>
            )}
            {lookup.match_found && (
                <div style={{ marginTop: 12 }}>
                    <button onClick={onToggleAutoUpdate}
                        style={{ padding: "6px 16px", cursor: "pointer",
                            background: autoUpdating ? "#e74c3c" : "#27ae60",
                            color: "white", border: "none", borderRadius: 4 }}>
                        {autoUpdating ? "Stop Auto-Update" : "Start Auto-Update (30s)"}
                    </button>
                </div>
            )}
        </div>
    );
}
