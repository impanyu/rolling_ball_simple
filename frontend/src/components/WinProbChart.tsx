import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
} from "recharts";

interface DataPoint {
    points: number;
    prob: number;
}

interface Props {
    data: DataPoint[];
    playerName: string;
}

export default function WinProbChart({ data, playerName }: Props) {
    if (data.length < 2) {
        return <p style={{ textAlign: "center", color: "#888" }}>Collecting data... (auto-update must be running)</p>;
    }

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>
                P({playerName} wins) — Live Tracker
            </h3>
            <ResponsiveContainer width="100%" height={250}>
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
                        label={{ value: "P(win) %", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(1)}%`, "P(win)"]}
                        labelFormatter={(label) => `Point ${label}`}
                    />
                    <ReferenceLine y={50} stroke="#999" strokeDasharray="3 3" />
                    <Line
                        type="monotone"
                        dataKey="prob"
                        stroke="#3498db"
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        activeDot={{ r: 5 }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
