import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useState } from "react";
import NavBar from "./components/NavBar";
import QueryForm from "./components/QueryForm";
import Histogram from "./components/Histogram";
import SimulatorPage from "./pages/SimulatorPage";
import { fetchQueryResults } from "./api";
import type { QueryFilters, QueryResponse } from "./types";

function QueryPage() {
    const [data, setData] = useState<QueryResponse | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async (filters: QueryFilters) => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchQueryResults(filters);
            setData(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Query failed");
        } finally {
            setLoading(false);
        }
    };

    return (
        <>
            <QueryForm onSearch={handleSearch} loading={loading} />
            {error && (
                <div style={{ marginTop: 16, padding: 12, background: "#fee", borderRadius: 6, color: "#c00" }}>{error}</div>
            )}
            <div style={{ marginTop: 20 }}>
                <Histogram data={data} />
            </div>
        </>
    );
}

function App() {
    return (
        <BrowserRouter>
            <div style={{ maxWidth: 900, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
                <h1>Tennis Odds Tool</h1>
                <NavBar />
                <Routes>
                    <Route path="/" element={<QueryPage />} />
                    <Route path="/simulate" element={<SimulatorPage />} />
                </Routes>
            </div>
        </BrowserRouter>
    );
}

export default App;
