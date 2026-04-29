import { useState } from "react";
import type { QueryFilters } from "../types";

interface Props {
    onSearch: (filters: QueryFilters) => void;
    loading: boolean;
}

interface RangeInputProps {
    label: string;
    minKey: keyof QueryFilters;
    maxKey: keyof QueryFilters;
    filters: QueryFilters;
    onChange: (key: keyof QueryFilters, value: string) => void;
    step?: number;
    placeholder?: [string, string];
}

function RangeInput({
    label,
    minKey,
    maxKey,
    filters,
    onChange,
    step = 1,
    placeholder = ["Min", "Max"],
}: RangeInputProps) {
    return (
        <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>
                {label}
            </label>
            <div style={{ display: "flex", gap: 8 }}>
                <input
                    type="number"
                    step={step}
                    placeholder={placeholder[0]}
                    value={filters[minKey] ?? ""}
                    onChange={(e) => onChange(minKey, e.target.value)}
                    style={{ width: 100, padding: "4px 8px" }}
                />
                <span style={{ alignSelf: "center" }}>to</span>
                <input
                    type="number"
                    step={step}
                    placeholder={placeholder[1]}
                    value={filters[maxKey] ?? ""}
                    onChange={(e) => onChange(maxKey, e.target.value)}
                    style={{ width: 100, padding: "4px 8px" }}
                />
            </div>
        </div>
    );
}

export default function QueryForm({ onSearch, loading }: Props) {
    const [filters, setFilters] = useState<QueryFilters>({});

    const handleChange = (key: keyof QueryFilters, value: string) => {
        setFilters((prev) => ({
            ...prev,
            [key]: value === "" ? undefined : Number(value),
        }));
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSearch(filters);
    };

    return (
        <form onSubmit={handleSubmit} style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>Query Filters</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                <RangeInput
                    label="Initial Price (cents)"
                    minKey="initial_price_min"
                    maxKey="initial_price_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["0", "99"]}
                />
                <RangeInput
                    label="Current Price (cents)"
                    minKey="current_price_min"
                    maxKey="current_price_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["0", "99"]}
                />
                <RangeInput
                    label="Player Ranking"
                    minKey="player_ranking_min"
                    maxKey="player_ranking_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["1", "500"]}
                />
                <RangeInput
                    label="Opponent Ranking"
                    minKey="opponent_ranking_min"
                    maxKey="opponent_ranking_max"
                    filters={filters}
                    onChange={handleChange}
                    placeholder={["1", "500"]}
                />
                <RangeInput
                    label="Player Win Rate (3 months)"
                    minKey="player_win_rate_3m_min"
                    maxKey="player_win_rate_3m_max"
                    filters={filters}
                    onChange={handleChange}
                    step={0.01}
                    placeholder={["0.0", "1.0"]}
                />
                <RangeInput
                    label="Opponent Win Rate (3 months)"
                    minKey="opponent_win_rate_3m_min"
                    maxKey="opponent_win_rate_3m_max"
                    filters={filters}
                    onChange={handleChange}
                    step={0.01}
                    placeholder={["0.0", "1.0"]}
                />
                <div style={{ marginBottom: 12 }}>
                    <label style={{ display: "block", fontWeight: 600, marginBottom: 4 }}>
                        Ranking Comparison
                    </label>
                    <select
                        value={filters.ranking_compare ?? ""}
                        onChange={(e) => setFilters(prev => ({ ...prev, ranking_compare: e.target.value || undefined }))}
                        style={{ padding: "4px 8px", width: 210 }}
                    >
                        <option value="">Any</option>
                        <option value="higher">Player ranked higher</option>
                        <option value="lower">Player ranked lower</option>
                    </select>
                </div>
            </div>
            <button
                type="submit"
                disabled={loading}
                style={{
                    marginTop: 16,
                    padding: "8px 24px",
                    fontSize: 16,
                    cursor: loading ? "not-allowed" : "pointer",
                }}
            >
                {loading ? "Searching..." : "Search"}
            </button>
        </form>
    );
}
