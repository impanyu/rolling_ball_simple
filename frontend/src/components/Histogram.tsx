import { useState } from "react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
} from "recharts";
import type { QueryResponse, HistogramBin } from "../types";

interface Props {
    data: QueryResponse | null;
}

export default function Histogram({ data }: Props) {
    const [selectedBin, setSelectedBin] = useState<HistogramBin | null>(null);
    const [cumulativePercent, setCumulativePercent] = useState<number | null>(null);

    if (!data) {
        return <p style={{ textAlign: "center", color: "#888" }}>Run a query to see results.</p>;
    }

    if (data.total_count === 0) {
        return <p style={{ textAlign: "center", color: "#888" }}>No data points match your filters.</p>;
    }

    const chartData = data.histogram.map((bin) => ({
        name: `${bin.bin_start}`,
        percentage: bin.percentage,
        count: bin.count,
        bin_start: bin.bin_start,
        bin_end: bin.bin_end,
    }));

    const handleBarClick = (entry: any) => {
        const clickedStart = entry.bin_start;
        setSelectedBin(entry);
        const cumPct = data.histogram
            .filter((b) => b.bin_start >= clickedStart)
            .reduce((sum, b) => sum + b.percentage, 0);
        setCumulativePercent(Math.round(cumPct * 100) / 100);
    };

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>
                Max Price After Distribution ({data.total_count.toLocaleString()} data points)
            </h2>

            <ResponsiveContainer width="100%" height={400}>
                <BarChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="name"
                        label={{ value: "Max Price After (cents)", position: "insideBottom", offset: -15 }}
                    />
                    <YAxis
                        label={{ value: "Percentage (%)", angle: -90, position: "insideLeft" }}
                    />
                    <Tooltip
                        formatter={(value, name) => [
                            name === "percentage" ? `${value}%` : value,
                            name === "percentage" ? "Percentage" : "Count",
                        ]}
                        labelFormatter={(label) => `Bin: ${label}-${Number(label) + 5} cents`}
                    />
                    <Bar
                        dataKey="percentage"
                        cursor="pointer"
                        onClick={(_, index) => handleBarClick(chartData[index])}
                    >
                        {chartData.map((entry, index) => (
                            <Cell
                                key={index}
                                fill={
                                    selectedBin && entry.bin_start >= selectedBin.bin_start
                                        ? "#e74c3c"
                                        : "#3498db"
                                }
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>

            {selectedBin && cumulativePercent !== null && (
                <div
                    style={{
                        marginTop: 12,
                        padding: 12,
                        background: "#fef3f3",
                        borderRadius: 6,
                        border: "1px solid #e74c3c",
                    }}
                >
                    <strong>
                        Cumulative: {cumulativePercent}% of data points have max_price_after
                        &ge; {selectedBin.bin_start} cents
                    </strong>
                </div>
            )}

            <div style={{ marginTop: 16, display: "flex", gap: 32 }}>
                <div><strong>Mean:</strong> {data.stats.mean} cents</div>
                <div><strong>Median:</strong> {data.stats.median} cents</div>
                <div><strong>Std Dev:</strong> {data.stats.std} cents</div>
            </div>
        </div>
    );
}
