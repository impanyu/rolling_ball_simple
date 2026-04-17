import { BrowserRouter, useLocation } from "react-router-dom";
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

function AppContent() {
    const location = useLocation();
    const currentPath = location.pathname;

    return (
        <div style={{ maxWidth: 900, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
            <h1>Tennis Odds Tool</h1>
            <NavBar />
            <div style={{ display: currentPath === "/" ? "block" : "none" }}>
                <QueryPage />
            </div>
            <div style={{ display: currentPath === "/simulate" ? "block" : "none" }}>
                <SimulatorPage />
            </div>
        </div>
    );
}

function App() {
    return (
        <BrowserRouter>
            <AppContent />
        </BrowserRouter>
    );
}

export default App;
