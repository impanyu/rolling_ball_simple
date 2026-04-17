import { useState } from "react";

interface Props {
    onLookup: (input: string) => void;
    loading: boolean;
}

export default function MatchInput({ onLookup, loading }: Props) {
    const [input, setInput] = useState("");

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (input.trim()) onLookup(input.trim());
    };

    return (
        <form onSubmit={handleSubmit} style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h2 style={{ marginTop: 0 }}>Match Lookup</h2>
            <div style={{ display: "flex", gap: 8 }}>
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Enter player names (e.g. Rybakina vs Fernandez)"
                    style={{ flex: 1, padding: "8px 12px", fontSize: 16 }}
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    style={{ padding: "8px 20px", fontSize: 16, cursor: loading ? "not-allowed" : "pointer" }}
                >
                    {loading ? "Looking up..." : "Look Up Match"}
                </button>
            </div>
        </form>
    );
}
