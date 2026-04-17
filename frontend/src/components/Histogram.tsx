import { useState, useEffect } from "react";
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
    xLabel?: string;
    unit?: string;
    title?: string;
    compact?: boolean;
    currentProb?: number;
}

export default function Histogram({
    data,
    xLabel = "Max Price After (cents)",
    unit = "cents",
    title = "Max Price After Distribution",
    compact = false,
    currentProb,
}: Props) {
    const [selectedBin, setSelectedBin] = useState<HistogramBin | null>(null);
    const [cumulativePercent, setCumulativePercent] = useState<number | null>(null);

    // Reset selection when data changes
    useEffect(() => {
        setSelectedBin(null);
        setCumulativePercent(null);
    }, [data]);

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

    const chartHeight = compact ? 200 : 400;

    return (
        <div style={{ padding: compact ? 10 : 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0, fontSize: compact ? 14 : 18 }}>
                {title}
            </h3>

            <ResponsiveContainer width="100%" height={chartHeight}>
                <BarChart data={chartData} margin={{ top: 5, right: compact ? 5 : 30, left: compact ? 0 : 20, bottom: compact ? 5 : 25 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="name"
                        tick={{ fontSize: compact ? 9 : 12 }}
                        label={compact ? undefined : { value: xLabel, position: "insideBottom", offset: -15 }}
                    />
                    <YAxis tick={{ fontSize: compact ? 9 : 12 }} />
                    <Tooltip
                        formatter={(value, name) => [
                            name === "percentage" ? `${value}%` : value,
                            name === "percentage" ? "Percentage" : "Count",
                        ]}
                        labelFormatter={(label) => `Bin: ${label}-${Number(label) + 5} ${unit}`}
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
                        marginTop: compact ? 4 : 12,
                        padding: compact ? 6 : 12,
                        background: "#fef3f3",
                        borderRadius: 6,
                        border: "1px solid #e74c3c",
                        fontSize: compact ? 12 : 14,
                    }}
                >
                    <strong>
                        P(&ge;{selectedBin.bin_start}{unit}) = {cumulativePercent}%
                    </strong>
                </div>
            )}

            <div style={{ marginTop: 8, fontSize: compact ? 11 : 14, display: "flex", gap: compact ? 8 : 32, flexWrap: "wrap" }}>
                <div><strong>E[P]:</strong> {data.stats.mean}{unit}</div>
                {currentProb !== undefined && (
                    <div style={{ color: data.stats.mean - currentProb >= 0 ? "#27ae60" : "#e74c3c" }}>
                        <strong>&Delta;:</strong> {(data.stats.mean - currentProb) >= 0 ? "+" : ""}{(data.stats.mean - currentProb).toFixed(2)}{unit}
                    </div>
                )}
                {!compact && <div><strong>Median:</strong> {data.stats.median}{unit}</div>}
                {!compact && <div><strong>Std:</strong> {data.stats.std}{unit}</div>}
            </div>
        </div>
    );
}
