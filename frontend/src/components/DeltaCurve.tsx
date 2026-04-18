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
    // Compute cumulative from right: P(value >= bin_start)
    const cumulativeFromRight: number[] = [];
    let cumSum = 0;
    for (let i = histogram.length - 1; i >= 0; i--) {
        cumSum += histogram[i].percentage;
        cumulativeFromRight[i] = cumSum;
    }

    // For a given absolute probability, find the upper tail P(value >= prob)
    function getUpperTail(absProb: number): number {
        if (absProb <= 0) return 100;
        if (absProb >= 100) return 0;
        // Find which bin this falls in
        const binIdx = Math.floor(absProb / 5);
        if (binIdx >= histogram.length) return 0;
        return cumulativeFromRight[binIdx] ?? 0;
    }

    // Generate fixed delta steps centered at 0
    // Range: enough to cover from -currentProb to +(100-currentProb)
    const minDelta = -Math.floor(currentProb / 5) * 5;
    const maxDelta = Math.ceil((100 - currentProb) / 5) * 5;

    const chartData: { delta: number; upperTail: number }[] = [];
    for (let d = minDelta; d <= maxDelta; d += 5) {
        const absProb = currentProb + d;
        if (absProb < 0 || absProb > 100) continue;
        chartData.push({
            delta: d,
            upperTail: Math.round(getUpperTail(absProb) * 100) / 100,
        });
    }

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
                        domain={[minDelta, maxDelta]}
                        ticks={chartData.map(d => d.delta)}
                        tick={{ fontSize: 11 }}
                        label={{ value: "Δ from current P(win) (%)", position: "insideBottom", offset: -15 }}
                    />
                    <YAxis
                        domain={[0, 100]}
                        label={{ value: "P(≥ current + Δ) %", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value) => [`${Number(value).toFixed(1)}%`, "Upper tail prob"]}
                        labelFormatter={(label) => `Δ = ${Number(label) >= 0 ? "+" : ""}${label}%`}
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
