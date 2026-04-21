import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
    Legend,
} from "recharts";

interface DataPoint {
    points: number;
    prob: number;
    pA?: number;
    pB?: number;
}

interface Props {
    data: DataPoint[];
    playerName: string;
    playerAName?: string;
    playerBName?: string;
}

export default function WinProbChart({ data, playerName, playerAName, playerBName }: Props) {
    if (data.length < 2) {
        return <p style={{ textAlign: "center", color: "#888" }}>Collecting data... (auto-update must be running)</p>;
    }

    const hasPValues = data.some(d => d.pA != null || d.pB != null);

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>
                Live Tracker — P({playerName} wins) + serve p values
            </h3>
            <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="points"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        allowDecimals={false}
                        label={{ value: "Points played", position: "insideBottom", offset: -15 }}
                    />
                    <YAxis
                        domain={[0, 100]}
                        label={{ value: "%", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value, name) => {
                            const label = name === "prob" ? "P(win)" : name === "pA" ? (playerAName || "A") + " p" : (playerBName || "B") + " p";
                            return [`${Number(value).toFixed(1)}%`, label];
                        }}
                        labelFormatter={(label) => `Point ${label}`}
                    />
                    <Legend formatter={(value) => value === "prob" ? `P(${playerName} wins)` : value === "pA" ? `${playerAName || "A"} p` : `${playerBName || "B"} p`} />
                    <ReferenceLine y={50} stroke="#999" strokeDasharray="3 3" />
                    <Line
                        type="monotone"
                        dataKey="prob"
                        stroke="#3498db"
                        strokeWidth={2}
                        dot={{ r: 2 }}
                        activeDot={{ r: 4 }}
                    />
                    {hasPValues && (
                        <Line
                            type="monotone"
                            dataKey="pA"
                            stroke="#e67e22"
                            strokeWidth={1.5}
                            strokeDasharray="4 4"
                            dot={false}
                        />
                    )}
                    {hasPValues && (
                        <Line
                            type="monotone"
                            dataKey="pB"
                            stroke="#9b59b6"
                            strokeWidth={1.5}
                            strokeDasharray="4 4"
                            dot={false}
                        />
                    )}
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
