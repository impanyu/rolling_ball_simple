import type { LookupResult, ScoreState } from "../types";

interface Props {
    lookup: LookupResult;
    pA: number;
    pB: number;
    onPChange: (pA: number, pB: number) => void;
    currentWinProb: number | null;
    autoUpdating: boolean;
    onToggleAutoUpdate: () => void;
}

const POINT_LABELS = ["0", "15", "30", "40", "AD"];

function formatScore(score: ScoreState, playerA: string, playerB: string): string {
    const sets = score.sets.join("-");
    const games = score.games.join("-");
    const pa = score.points[0];
    const pb = score.points[1];
    const points = pa <= 4 && pb <= 4
        ? `${POINT_LABELS[pa] || pa}-${POINT_LABELS[pb] || pb}`
        : `${pa}-${pb}`;
    const server = score.serving === "a" ? playerA.split(" ").pop() : playerB.split(" ").pop();
    return `Sets: ${sets}  Games: ${games}  Points: ${points}  (${server} serving)`;
}

export default function MatchStatus({
    lookup, pA, pB, onPChange, currentWinProb, autoUpdating, onToggleAutoUpdate
}: Props) {
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
            <div style={{ display: "flex", gap: 24, marginTop: 12 }}>
                <div>
                    <label style={{ fontWeight: 600 }}>{lookup.player_a.split(" ").pop()} p:</label>
                    {" "}<span style={{ color: "#888", fontSize: 14 }}>prior {lookup.p_a_prior.toFixed(3)}</span>
                    <br />
                    <input type="number" step={0.001} value={pA}
                        onChange={(e) => onPChange(Number(e.target.value), pB)}
                        style={{ width: 80, padding: "4px 8px", marginTop: 4 }} />
                </div>
                <div>
                    <label style={{ fontWeight: 600 }}>{lookup.player_b.split(" ").pop()} p:</label>
                    {" "}<span style={{ color: "#888", fontSize: 14 }}>prior {lookup.p_b_prior.toFixed(3)}</span>
                    <br />
                    <input type="number" step={0.001} value={pB}
                        onChange={(e) => onPChange(pA, Number(e.target.value))}
                        style={{ width: 80, padding: "4px 8px", marginTop: 4 }} />
                </div>
            </div>
            {currentWinProb !== null && (
                <p style={{ fontSize: 18, marginTop: 12 }}>
                    Current P({lookup.player_a.split(" ").pop()} wins):{" "}
                    <strong>{currentWinProb.toFixed(1)}%</strong>
                </p>
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
