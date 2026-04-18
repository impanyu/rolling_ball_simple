import {
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    ReferenceLine,
} from "recharts";
import type { HistogramBin } from "../types";

interface Props {
    histogram: HistogramBin[];
    currentProb: number;
    playerName: string;
}

export default function DeltaCurve({ histogram, currentProb, playerName }: Props) {
    // Build delta -> upper tail cumulative data
    // For each bin, delta = bin_start - currentProb
    // Upper tail = sum of percentage for bins >= this bin
    // Compute cumulative from right
    const cumulativeFromRight: number[] = [];
    let cumSum = 0;
    for (let i = histogram.length - 1; i >= 0; i--) {
        cumSum += histogram[i].percentage;
        cumulativeFromRight[i] = cumSum;
    }

    const chartData = histogram.map((bin, i) => {
        const delta = Math.round(bin.bin_start - currentProb);
        const upperTail = Math.round(cumulativeFromRight[i] * 100) / 100;
        return { delta, upperTail };
    });

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>
                Upper Tail Probability — {playerName} (relative to current P)
            </h3>
            <p style={{ fontSize: 13, color: "#888", margin: "0 0 8px 0" }}>
                P(future win prob &ge; current + &Delta;) — how likely is an upswing of at least &Delta;%?
            </p>
            <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="delta"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        label={{ value: "Δ from current P(win) (%)", position: "insideBottom", offset: -15 }}
                    />
                    <YAxis
                        domain={[0, 100]}
                        label={{ value: "P(≥ current + Δ) %", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(1)}%`, "Upper tail prob"]}
                        labelFormatter={(label) => `Δ = ${label >= 0 ? "+" : ""}${label}%`}
                    />
                    <ReferenceLine x={0} stroke="#e67e22" strokeWidth={2} strokeDasharray="4 4" label={{ value: "Now", position: "top", fontSize: 11, fill: "#e67e22" }} />
                    <Area
                        type="monotone"
                        dataKey="upperTail"
                        stroke="#8e44ad"
                        fill="#8e44ad"
                        fillOpacity={0.15}
                        strokeWidth={2}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}
