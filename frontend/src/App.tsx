import { BrowserRouter, useLocation } from "react-router-dom";
import { useState, useEffect, useRef, useCallback } from "react";
import NavBar from "./components/NavBar";
import QueryForm from "./components/QueryForm";
import Histogram from "./components/Histogram";
import SimulatorPage from "./pages/SimulatorPage";
import { fetchQueryResults, fetchGridSearch, fetchPlayerWinRates, refreshWinRates, fetchActiveMatches, monitorStart, monitorStop, fetchMonitorStatus, fetchComebackAnalysis, fetchCloseoutAnalysis, fetchMatchSignal, fetchPathQuery, fetchLiveSignal, fetchLiveMatches, pollLiveMatch, backfillLiveMatch, autoTradingStart, autoTradingStop, autoTradingStatus, autoTradingBalance, autoTradingMatchDetail, autoTradingPrepare } from "./api";
import type { GridSearchResult, PlayerWinRate } from "./api";
import type { QueryFilters, QueryResponse } from "./types";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from "recharts";

function GridSearchTable() {
    const [allResults, setAllResults] = useState<GridSearchResult[]>([]);
    const [loading, setLoading] = useState(true);
    const [minN, setMinN] = useState(10);
    const [minExcess, setMinExcess] = useState(5);
    const [minRoi, setMinRoi] = useState(0);

    useEffect(() => {
        fetchGridSearch(0, 1).then(data => {
            setAllResults(data.results);
            setLoading(false);
        }).catch(() => setLoading(false));
    }, []);

    if (loading) return <p style={{ color: "#888" }}>Loading grid search...</p>;

    const filtered = allResults.filter(r => r.n >= minN && r.excess >= minExcess && r.roi >= minRoi);

    const inputStyle = { width: 60, padding: "2px 6px", marginLeft: 4 };

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Alpha Grid Search</h3>
            <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 13, flexWrap: "wrap" }}>
                <label>Min N: <input type="number" value={minN} onChange={e => setMinN(Number(e.target.value))} style={inputStyle} /></label>
                <label>Min Excess %: <input type="number" step={0.5} value={minExcess} onChange={e => setMinExcess(Number(e.target.value))} style={inputStyle} /></label>
                <label>Min ROI %: <input type="number" step={1} value={minRoi} onChange={e => setMinRoi(Number(e.target.value))} style={inputStyle} /></label>
                <span style={{ color: "#888", lineHeight: "28px" }}>{filtered.length} results</span>
            </div>
            {filtered.length === 0 ? (
                <p style={{ color: "#888" }}>No combinations match filters.</p>
            ) : (
                <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                    <thead>
                        <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                            <th style={{ textAlign: "left", padding: "4px 8px" }}>#</th>
                            <th style={{ padding: "4px 8px" }}>Initial</th>
                            <th style={{ padding: "4px 8px" }}>Current</th>
                            <th style={{ padding: "4px 8px" }}>N</th>
                            <th style={{ padding: "4px 8px" }}>P(win)</th>
                            <th style={{ padding: "4px 8px" }}>Implied</th>
                            <th style={{ padding: "4px 8px" }}>Excess</th>
                            <th style={{ padding: "4px 8px" }}>ROI</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map((r, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                <td style={{ padding: "4px 8px" }}>{i + 1}</td>
                                <td style={{ padding: "4px 8px", textAlign: "right" }}>{r.initial}</td>
                                <td style={{ padding: "4px 8px", textAlign: "right" }}>{r.current}</td>
                                <td style={{ padding: "4px 8px", textAlign: "right" }}>{r.n}</td>
                                <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 600 }}>{r.p_win}%</td>
                                <td style={{ padding: "4px 8px", textAlign: "right", color: "#888" }}>{r.implied}%</td>
                                <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 600, color: "#27ae60" }}>+{r.excess}%</td>
                                <td style={{ padding: "4px 8px", textAlign: "right", color: r.roi >= 20 ? "#27ae60" : "#666" }}>+{r.roi}%</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            <div style={{ marginTop: 8, fontSize: 12, color: "#888" }}>
                P(win) = P(max price &ge; 99). Implied = current price upper bound. Excess = P(win) - Implied.
            </div>
        </div>
    );
}

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
            <div style={{ marginTop: 20 }}>
                <GridSearchTable />
            </div>
        </>
    );
}

function WinRatesPage() {
    const [players, setPlayers] = useState<PlayerWinRate[]>([]);
    const [loading, setLoading] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [totalMatches, setTotalMatches] = useState(0);

    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchPlayerWinRates(80, 5, 30);
            setPlayers(data.players);
            setTotalMatches(data.total_matches);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load");
        } finally {
            setLoading(false);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        setError(null);
        try {
            await refreshWinRates();
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Refresh failed");
        } finally {
            setRefreshing(false);
        }
    };

    useEffect(() => { loadData(); }, []);

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Player Win Rates (Last 30 Days, FlashScore)</h3>
            <div style={{ marginBottom: 16, display: "flex", gap: 8 }}>
                <button onClick={handleRefresh} disabled={refreshing}
                    style={{ padding: "8px 20px", cursor: "pointer", background: "#e67e22", color: "white", border: "none", borderRadius: 4 }}>
                    {refreshing ? "Scraping FlashScore..." : "Refresh from FlashScore"}
                </button>
                {loading && <span style={{ color: "#888", lineHeight: "36px" }}>Loading...</span>}
            </div>
            {error && <div style={{ padding: 12, background: "#fee", borderRadius: 6, color: "#c00", marginBottom: 12 }}>{error}</div>}
            {players.length > 0 ? (
                <>
                    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                        <thead>
                            <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>#</th>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Player</th>
                                <th style={{ padding: "4px 8px" }}>Tour</th>
                                <th style={{ padding: "4px 8px" }}>Rank</th>
                                <th style={{ padding: "4px 8px" }}>W</th>
                                <th style={{ padding: "4px 8px" }}>L</th>
                                <th style={{ padding: "4px 8px" }}>Total</th>
                                <th style={{ padding: "4px 8px" }}>Win Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {players.map((p, i) => (
                                <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                    <td style={{ padding: "4px 8px" }}>{i + 1}</td>
                                    <td style={{ padding: "4px 8px", fontWeight: 600 }}>
                                        {p.href ? (
                                            <a href={`https://www.flashscoreusa.com${p.href}`} target="_blank" rel="noopener noreferrer" style={{ color: "#3498db", textDecoration: "none" }}>{p.player}</a>
                                        ) : p.player}
                                    </td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", color: p.tour === "ATP" ? "#3498db" : "#e74c3c" }}>{p.tour}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", color: "#888" }}>{p.ranking ?? "—"}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{p.wins}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{p.losses}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{p.total}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 600, color: "#27ae60" }}>{p.win_rate}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div style={{ marginTop: 8, fontSize: 12, color: "#888" }}>
                        {totalMatches} match results in DB. Showing players with win rate &ge; 80% and &ge; 5 matches in last 30 days.
                        Auto-refreshes daily at 04:00.
                    </div>
                </>
            ) : !loading && (
                <p style={{ color: "#888" }}>No data yet. Click "Refresh from FlashScore" to scrape results.</p>
            )}
        </div>
    );
}

function PathQueryPage() {
    const [params, setParams] = useState({
        init_min: 0, init_max: 70,
        current_min: 87, current_max: 91,
        path_min_min: "" as number | "", path_min_max: "" as number | "",
        path_max_min: "" as number | "", path_max_max: "" as number | "",
        path_range_min: "" as number | "", path_range_max: "" as number | "",
        ranked_higher: true,
    });
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const handleSearch = async () => {
        setLoading(true);
        try {
            const q: any = {
                init_min: params.init_min, init_max: params.init_max,
                current_min: params.current_min, current_max: params.current_max,
                ranked_higher: params.ranked_higher,
            };
            if (params.path_min_min !== "") q.path_min_min = params.path_min_min;
            if (params.path_min_max !== "") q.path_min_max = params.path_min_max;
            if (params.path_max_min !== "") q.path_max_min = params.path_max_min;
            if (params.path_max_max !== "") q.path_max_max = params.path_max_max;
            if (params.path_range_min !== "") q.path_range_min = params.path_range_min;
            if (params.path_range_max !== "") q.path_range_max = params.path_range_max;
            const result = await fetchPathQuery(q);
            setData(result);
        } catch {}
        setLoading(false);
    };

    const inputStyle = { width: 55, padding: "2px 6px" };

    return (
        <div style={{ padding: 20 }}>
            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                <h3 style={{ marginTop: 0 }}>Path Query Tool</h3>
                <div style={{ fontSize: 12, color: "#888", marginBottom: 12 }}>
                    One data point per visit (each time price enters the range counts once). Path Range filters on running min/max at entry moment.
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
                    <div>
                        <label style={{ fontWeight: 600 }}>Init Price</label>
                        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                            <input type="number" value={params.init_min} onChange={e => setParams(p => ({...p, init_min: Number(e.target.value)}))} style={inputStyle} />
                            <span>to</span>
                            <input type="number" value={params.init_max} onChange={e => setParams(p => ({...p, init_max: Number(e.target.value)}))} style={inputStyle} />
                        </div>
                    </div>
                    <div>
                        <label style={{ fontWeight: 600 }}>Current Price</label>
                        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                            <input type="number" value={params.current_min} onChange={e => setParams(p => ({...p, current_min: Number(e.target.value)}))} style={inputStyle} />
                            <span>to</span>
                            <input type="number" value={params.current_max} onChange={e => setParams(p => ({...p, current_max: Number(e.target.value)}))} style={inputStyle} />
                        </div>
                    </div>
                    <div>
                        <label style={{ fontWeight: 600 }}>Path Range (lowest ~ highest seen)</label>
                        <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                            <input type="number" placeholder="min" value={params.path_range_min} onChange={e => setParams(p => ({...p, path_range_min: e.target.value === "" ? "" : Number(e.target.value)}))} style={inputStyle} />
                            <span>to</span>
                            <input type="number" placeholder="max" value={params.path_range_max} onChange={e => setParams(p => ({...p, path_range_max: e.target.value === "" ? "" : Number(e.target.value)}))} style={inputStyle} />
                        </div>
                    </div>
                </div>
                <div style={{ marginTop: 12, display: "flex", gap: 12, alignItems: "center" }}>
                    <label><input type="checkbox" checked={params.ranked_higher} onChange={e => setParams(p => ({...p, ranked_higher: e.target.checked}))} /> Player ranked higher only</label>
                    <button onClick={handleSearch} disabled={loading} style={{ padding: "6px 20px", cursor: "pointer" }}>
                        {loading ? "Loading..." : "Search"}
                    </button>
                </div>
            </div>

            {data && (
                <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20 }}>
                    <div style={{ display: "flex", gap: 32, fontSize: 14, marginBottom: 16, flexWrap: "wrap" }}>
                        <div><strong>N:</strong> {data.total_count.toLocaleString()}</div>
                        <div style={{ color: "#27ae60", fontWeight: 600 }}><strong>P(win):</strong> {data.win_count}/{data.total_count} ({data.win_pct}%)</div>
                        <div><strong>E[max]:</strong> {data.stats.mean}</div>
                        <div><strong>Median:</strong> {data.stats.median}</div>
                        <div><strong>Std:</strong> {data.stats.std}</div>
                    </div>
                    <Histogram data={data} title="Max Price After Distribution (per trade)" />
                </div>
            )}
        </div>
    );
}

function SignalPage() {
    const [input, setInput] = useState("");
    const [initPrice, setInitPrice] = useState(65);
    const [data, setData] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = async () => {
        const parts = input.split(/\s+vs\.?\s+/i);
        if (parts.length !== 2) { setError("Format: Player A vs Player B"); return; }
        setLoading(true); setError(null);
        try {
            const result = await fetchMatchSignal(parts[0].trim(), parts[1].trim(), initPrice);
            setData(result);
        } catch (e) { setError(e instanceof Error ? e.message : "Failed"); }
        setLoading(false);
    };

    return (
        <div style={{ padding: 20 }}>
            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                <h3 style={{ marginTop: 0 }}>Match Signal Analysis</h3>
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                    <input type="text" value={input} onChange={e => setInput(e.target.value)}
                        placeholder="Player A vs Player B" style={{ padding: "6px 12px", width: 300 }}
                        onKeyDown={e => e.key === "Enter" && handleSearch()} />
                    <label>Init price: <input type="number" value={initPrice} onChange={e => setInitPrice(Number(e.target.value))}
                        style={{ width: 60, padding: "4px 6px", marginLeft: 4 }} /></label>
                    <button onClick={handleSearch} disabled={loading} style={{ padding: "6px 20px", cursor: "pointer" }}>
                        {loading ? "Loading..." : "Analyze"}
                    </button>
                </div>
                {error && <div style={{ marginTop: 8, color: "#c00" }}>{error}</div>}
            </div>

            {data && (
                <>
                    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                        <h3 style={{ marginTop: 0 }}>
                            {data.favorite} (#{data.fav_rank || "?"}) vs {data.underdog} (#{data.dog_rank || "?"})
                            <span style={{ fontSize: 14, color: "#888", marginLeft: 12 }}>init ≤ {data.init_price}</span>
                        </h3>
                        <div style={{ fontSize: 13, marginBottom: 12 }}>Alpha = P(win) - current_price - 2 (ranked higher player)</div>
                        <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 200 }}>
                            {data.alpha_curve.map((d: any, i: number) => {
                                const maxAlpha = Math.max(...data.alpha_curve.map((x: any) => Math.abs(x.alpha)), 1);
                                const barHeight = Math.abs(d.alpha) / maxAlpha * 150;
                                const isPositive = d.alpha >= 0;
                                return (
                                    <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: 1 }}>
                                        <div style={{ fontSize: 10, color: isPositive ? "#27ae60" : "#e74c3c", fontWeight: 700 }}>
                                            {d.alpha > 0 ? "+" : ""}{d.alpha}%
                                        </div>
                                        <div style={{ fontSize: 9, color: "#888" }}>N={d.n}</div>
                                        <div style={{
                                            width: "100%", maxWidth: 40,
                                            height: barHeight,
                                            background: isPositive ? "#27ae60" : "#e74c3c",
                                            borderRadius: 2, marginTop: 4,
                                        }} />
                                        <div style={{ fontSize: 10, marginTop: 4 }}>{d.current_price}</div>
                                        <div style={{ fontSize: 9, color: "#888" }}>{d.p_win}%</div>
                                    </div>
                                );
                            })}
                        </div>
                        <div style={{ textAlign: "center", fontSize: 11, color: "#888", marginTop: 4 }}>Current Price → P(win)</div>
                    </div>

                    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
                        <h4 style={{ marginTop: 0 }}>Closeout vs Comeback</h4>
                        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                            <thead><tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                                <th style={{ padding: "4px 8px", textAlign: "left" }}>Level</th>
                                <th style={{ padding: "4px 8px" }} colSpan={3}>{data.favorite} Closeout</th>
                                <th style={{ padding: "4px 8px", borderLeft: "2px solid #ddd" }} colSpan={3}>{data.underdog} Comeback</th>
                                <th style={{ padding: "4px 8px", borderLeft: "2px solid #ddd" }}>Signal</th>
                            </tr>
                            <tr style={{ borderBottom: "1px solid #ddd", textAlign: "right", fontSize: 11, color: "#888" }}>
                                <th style={{ padding: "2px 8px" }}></th>
                                <th style={{ padding: "2px 8px" }}>N</th>
                                <th style={{ padding: "2px 8px" }}>Won</th>
                                <th style={{ padding: "2px 8px" }}>Rate</th>
                                <th style={{ padding: "2px 8px", borderLeft: "2px solid #ddd" }}>N</th>
                                <th style={{ padding: "2px 8px" }}>Won</th>
                                <th style={{ padding: "2px 8px" }}>Rate</th>
                                <th style={{ padding: "2px 8px", borderLeft: "2px solid #ddd" }}></th>
                            </tr></thead>
                            <tbody>
                                {[{fav: 70, dog: 30}, {fav: 80, dog: 20}, {fav: 90, dog: 10}].map(({fav: ft, dog: dt}) => {
                                    const fc = data.fav_closeout[ft];
                                    const dc = data.dog_comeback[dt];
                                    const good = fc.rate > dc.rate;
                                    return (
                                        <tr key={ft} style={{ borderBottom: "1px solid #eee" }}>
                                            <td style={{ padding: "4px 8px", fontWeight: 600 }}>≥{ft} / ≤{dt}</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right" }}>{fc.n}</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right" }}>{fc.wins}</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 700 }}>{fc.rate}%</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right", borderLeft: "2px solid #ddd" }}>{dc.n}</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right" }}>{dc.wins}</td>
                                            <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 700 }}>{dc.rate}%</td>
                                            <td style={{ padding: "4px 8px", textAlign: "center", borderLeft: "2px solid #ddd", fontWeight: 700, fontSize: 16,
                                                color: good ? "#27ae60" : "#e74c3c" }}>
                                                {good ? "+" : "-"}
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
        </div>
    );
}

function ComebackPage() {
    const [players, setPlayers] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [minMatches, setMinMatches] = useState(3);
    const [maxRank, setMaxRank] = useState(1000);
    const [search, setSearch] = useState("");
    const [sortBy, setSortBy] = useState<"rate30" | "rate20" | "rate15" | "rate10">("rate30");

    const handleLoad = async () => {
        setLoading(true);
        try {
            const data = await fetchComebackAnalysis(minMatches, maxRank);
            setPlayers(data.players);
        } catch {}
        setLoading(false);
    };

    useEffect(() => { handleLoad(); }, []);

    const filtered = (search
        ? players.filter(p => p.player.toLowerCase().includes(search.toLowerCase()))
        : players
    ).sort((a, b) => b[sortBy] - a[sortBy]);

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Comeback Analysis (Kalshi Price Data)</h3>
            <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 13, flexWrap: "wrap", alignItems: "center" }}>
                <label>Min matches at ≤30: <input type="number" value={minMatches} onChange={e => setMinMatches(Number(e.target.value))} style={{ width: 50, padding: "2px 6px", marginLeft: 4 }} /></label>
                <label>Max rank: <input type="number" value={maxRank} onChange={e => setMaxRank(Number(e.target.value))} style={{ width: 60, padding: "2px 6px", marginLeft: 4 }} /></label>
                <button onClick={handleLoad} disabled={loading} style={{ padding: "4px 16px", cursor: "pointer" }}>{loading ? "Loading..." : "Search"}</button>
                <input type="text" placeholder="Filter by name..." value={search} onChange={e => setSearch(e.target.value)} style={{ padding: "4px 8px", width: 150 }} />
                <label>Sort by:
                    <select value={sortBy} onChange={e => setSortBy(e.target.value as any)} style={{ marginLeft: 4 }}>
                        <option value="rate30">≤30 rate</option>
                        <option value="rate20">≤20 rate</option>
                        <option value="rate15">≤15 rate</option>
                        <option value="rate10">≤10 rate</option>
                    </select>
                </label>
                <span style={{ color: "#888" }}>{filtered.length} players</span>
            </div>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>
                Shows players whose price was ≤30 during a match. Rate = won the match.
            </div>
            {filtered.length > 0 && (
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                    <thead>
                        <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                            <th style={{ textAlign: "left", padding: "4px 6px" }}>#</th>
                            <th style={{ textAlign: "left", padding: "4px 6px" }}>Player</th>
                            <th style={{ padding: "4px 6px" }}>Rank</th>
                            <th style={{ padding: "4px 6px" }}>Total</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≤30</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≤20</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≤15</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≤10</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map((p, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                <td style={{ padding: "4px 6px" }}>{i + 1}</td>
                                <td style={{ padding: "4px 6px", fontWeight: 600 }}>
                                    {p.href ? <a href={`https://www.flashscoreusa.com${p.href}`} target="_blank" rel="noopener noreferrer" style={{ color: "#3498db", textDecoration: "none" }}>{p.player}</a> : p.player}
                                </td>
                                <td style={{ padding: "4px 6px", textAlign: "right", color: "#888" }}>{p.ranking ?? "—"}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.total_matches}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n30}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w30}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.rate30 >= 60 ? "#27ae60" : p.rate30 >= 40 ? "#e67e22" : "#e74c3c" }}>{p.rate30}%</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n20}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w20}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.n20 > 0 ? (p.rate20 >= 50 ? "#27ae60" : p.rate20 >= 30 ? "#e67e22" : "#e74c3c") : "#888" }}>{p.n20 > 0 ? `${p.rate20}%` : "—"}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n15}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w15}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.n15 > 0 ? (p.rate15 >= 50 ? "#27ae60" : p.rate15 >= 30 ? "#e67e22" : "#e74c3c") : "#888" }}>{p.n15 > 0 ? `${p.rate15}%` : "—"}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n10}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w10}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.n10 > 0 ? (p.rate10 >= 40 ? "#27ae60" : p.rate10 >= 20 ? "#e67e22" : "#e74c3c") : "#888" }}>{p.n10 > 0 ? `${p.rate10}%` : "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function CloseoutPage() {
    const [players, setPlayers] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);
    const [minMatches, setMinMatches] = useState(3);
    const [maxRank, setMaxRank] = useState(1000);
    const [search, setSearch] = useState("");
    const [sortBy, setSortBy] = useState<"rate90" | "rate80" | "rate70">("rate90");

    const handleLoad = async () => {
        setLoading(true);
        try {
            const data = await fetchCloseoutAnalysis(minMatches, maxRank);
            setPlayers(data.players);
        } catch {}
        setLoading(false);
    };

    useEffect(() => { handleLoad(); }, []);

    const filtered = (search
        ? players.filter(p => p.player.toLowerCase().includes(search.toLowerCase()))
        : players
    ).sort((a, b) => b[sortBy] - a[sortBy]);

    return (
        <div style={{ padding: 20, border: "1px solid #ddd", borderRadius: 8 }}>
            <h3 style={{ marginTop: 0 }}>Closeout Analysis — Win Rate After Reaching Price</h3>
            <div style={{ display: "flex", gap: 16, marginBottom: 12, fontSize: 13, flexWrap: "wrap", alignItems: "center" }}>
                <label>Min matches at ≥70: <input type="number" value={minMatches} onChange={e => setMinMatches(Number(e.target.value))} style={{ width: 50, padding: "2px 6px", marginLeft: 4 }} /></label>
                <label>Max rank: <input type="number" value={maxRank} onChange={e => setMaxRank(Number(e.target.value))} style={{ width: 60, padding: "2px 6px", marginLeft: 4 }} /></label>
                <button onClick={handleLoad} disabled={loading} style={{ padding: "4px 16px", cursor: "pointer" }}>{loading ? "Loading..." : "Search"}</button>
                <input type="text" placeholder="Filter by name..." value={search} onChange={e => setSearch(e.target.value)} style={{ padding: "4px 8px", width: 150 }} />
                <label>Sort by:
                    <select value={sortBy} onChange={e => setSortBy(e.target.value as any)} style={{ marginLeft: 4 }}>
                        <option value="rate90">≥90 rate</option>
                        <option value="rate80">≥80 rate</option>
                        <option value="rate70">≥70 rate</option>
                    </select>
                </label>
                <span style={{ color: "#888" }}>{filtered.length} players</span>
            </div>
            <div style={{ fontSize: 11, color: "#888", marginBottom: 8 }}>
                When a player's price first reaches ≥70/80/90, what % of the time do they win the match?
            </div>
            {filtered.length > 0 && (
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                    <thead>
                        <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                            <th style={{ textAlign: "left", padding: "4px 6px" }}>#</th>
                            <th style={{ textAlign: "left", padding: "4px 6px" }}>Player</th>
                            <th style={{ padding: "4px 6px" }}>Rank</th>
                            <th style={{ padding: "4px 6px" }}>Total</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≥70</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≥80</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                            <th style={{ padding: "4px 6px", borderLeft: "1px solid #ddd" }}>≥90</th>
                            <th style={{ padding: "4px 6px" }}>Won</th>
                            <th style={{ padding: "4px 6px", fontWeight: 700 }}>Rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filtered.map((p, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                <td style={{ padding: "4px 6px" }}>{i + 1}</td>
                                <td style={{ padding: "4px 6px", fontWeight: 600 }}>
                                    {p.href ? <a href={`https://www.flashscoreusa.com${p.href}`} target="_blank" rel="noopener noreferrer" style={{ color: "#3498db", textDecoration: "none" }}>{p.player}</a> : p.player}
                                </td>
                                <td style={{ padding: "4px 6px", textAlign: "right", color: "#888" }}>{p.ranking ?? "—"}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.total_matches}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n70}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w70}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.rate70 >= 90 ? "#27ae60" : p.rate70 >= 75 ? "#e67e22" : "#e74c3c" }}>{p.rate70}%</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n80}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w80}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.n80 > 0 ? (p.rate80 >= 95 ? "#27ae60" : p.rate80 >= 85 ? "#e67e22" : "#e74c3c") : "#888" }}>{p.n80 > 0 ? `${p.rate80}%` : "—"}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", borderLeft: "1px solid #eee" }}>{p.n90}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right" }}>{p.w90}</td>
                                <td style={{ padding: "4px 6px", textAlign: "right", fontWeight: 700, color: p.n90 > 0 ? (p.rate90 >= 98 ? "#27ae60" : p.rate90 >= 90 ? "#e67e22" : "#e74c3c") : "#888" }}>{p.n90 > 0 ? `${p.rate90}%` : "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}

function LiveSignalPage() {
    const [searchQuery, setSearchQuery] = useState("");
    const [matches, setMatches] = useState<any[]>([]);
    const [searchLoading, setSearchLoading] = useState(false);

    const [trackedMatch, setTrackedMatch] = useState<any>(null);
    const [signal, setSignal] = useState<any>(null);
    const [history, setHistory] = useState<any[]>([]);
    const [polling, setPolling] = useState(false);
    const [pollInterval, setPollInterval] = useState(15);

    const initPriceRef = useRef<number | null>(null);
    const runningMinRef = useRef<number | null>(null);
    const runningMaxRef = useRef<number | null>(null);
    const matchStartRef = useRef<string | null>(null);
    const prevPriceRef = useRef<number | null>(null);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const handleSearch = async () => {
        setSearchLoading(true);
        try {
            const data = await fetchLiveMatches(searchQuery);
            setMatches(data.matches);
        } catch {}
        setSearchLoading(false);
    };

    const handleSelectMatch = (match: any) => {
        setTrackedMatch(match);
        setHistory([]);
        setSignal(null);
        initPriceRef.current = null;
        runningMinRef.current = null;
        runningMaxRef.current = null;
        matchStartRef.current = null;
        prevPriceRef.current = null;
        setPolling(true);
    };

    const doPoll = useCallback(async () => {
        if (!trackedMatch) return;
        try {
            const result = await pollLiveMatch({
                event_ticker: trackedMatch.event_ticker,
                ticker_a: trackedMatch.ticker_a,
                init_price: initPriceRef.current ?? undefined,
                running_min: runningMinRef.current ?? undefined,
                running_max: runningMaxRef.current ?? undefined,
                match_start: matchStartRef.current ?? undefined,
                prev_price: prevPriceRef.current ?? undefined,
            });
            if (result.status === "closed") {
                setPolling(false);
                return;
            }
            if (result.error) return;

            const rawPrice = result.raw_price;
            if (initPriceRef.current === null) initPriceRef.current = rawPrice;
            runningMinRef.current = result.running_min;
            runningMaxRef.current = result.running_max;
            prevPriceRef.current = rawPrice;

            // On first poll with match_start, backfill history from match start
            if (result.match_start && !matchStartRef.current) {
                matchStartRef.current = result.match_start;
                try {
                    const bf = await backfillLiveMatch({
                        event_ticker: trackedMatch.event_ticker,
                        ticker_a: trackedMatch.ticker_a,
                        match_start: result.match_start,
                    });
                    if (bf.history?.length > 0) {
                        if (bf.raw_init_price != null) initPriceRef.current = bf.raw_init_price;
                        setHistory(bf.history.map((h: any) => ({
                            ...h,
                            time: new Date(h.time).toLocaleTimeString(),
                            rec: (() => {
                                const bp = h.diff > 0 ? h.price_a : h.price_b;
                                const ad = Math.abs(h.diff);
                                const ev = Math.max(0, ad/500) * (100-bp-2) - Math.max(0, 1-ad/500) * (bp+2);
                                const pen = Math.max(0, 1 - ((bp-50)/25)**2);
                                const c = ev > 0 ? Math.min(5, Math.max(0, Math.round(ev*pen/5))) : 0;
                                if (c <= 0) return "";
                                return `BUY ${h.diff > 0 ? bf.player_a : bf.player_b} x${c}`;
                            })(),
                            strength: (() => {
                                const bp = h.diff > 0 ? h.price_a : h.price_b;
                                const ad = Math.abs(h.diff);
                                const ev = Math.max(0, ad/500) * (100-bp-2) - Math.max(0, 1-ad/500) * (bp+2);
                                const pen = Math.max(0, 1 - ((bp-50)/25)**2);
                                const c = ev > 0 ? Math.min(5, Math.max(0, Math.round(ev*pen/5))) : 0;
                                return c >= 4 ? "STRONG" : c >= 2 ? "MODERATE" : c >= 1 ? "WEAK" : "";
                            })(),
                        })));
                    }
                } catch (e) {
                    console.error("Backfill failed:", e);
                }
            }

            setSignal(result);
            setHistory(prev => {
                const next = [...prev, {
                time: new Date().toLocaleTimeString(),
                minutes: result.minutes_played || 0,
                price_a: result.current_price_a,
                price_b: 100 - result.current_price_a,
                score_a: result.score_a,
                score_b: result.score_b,
                diff: result.score_diff,
                rec: result.recommendation,
                strength: result.strength,
            }];
                return next.length > 500 ? next.slice(-500) : next;
            });
        } catch (e) {
            console.error("Poll failed:", e);
        }
    }, [trackedMatch]);

    useEffect(() => {
        if (polling && trackedMatch) {
            doPoll();
            intervalRef.current = setInterval(doPoll, pollInterval * 1000);
            return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
        }
        return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }, [polling, trackedMatch, pollInterval, doPoll]);

    const handleStop = () => {
        setPolling(false);
        setTrackedMatch(null);
        setSignal(null);
        setHistory([]);
        if (intervalRef.current) clearInterval(intervalRef.current);
    };

    const sigColor = signal?.strength === "STRONG" ? "#27ae60" : signal?.strength === "MODERATE" ? "#e67e22" : signal?.strength === "WEAK" ? "#888" : "#ccc";

    return (
        <div style={{ padding: 20 }}>
            {/* Search Section */}
            {!trackedMatch && (
                <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                    <h3 style={{ marginTop: 0 }}>Live Signal - Find Match</h3>
                    <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
                        <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                            placeholder="Search player name (or leave empty for all)"
                            style={{ padding: "6px 12px", width: 350 }}
                            onKeyDown={e => e.key === "Enter" && handleSearch()} />
                        <button onClick={handleSearch} disabled={searchLoading}
                            style={{ padding: "6px 20px", cursor: "pointer", background: "#3498db", color: "white", border: "none", borderRadius: 4 }}>
                            {searchLoading ? "Searching..." : "Search Active Matches"}
                        </button>
                    </div>
                    {matches.length > 0 && (
                        <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                            <thead><tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                                <th style={{ padding: 6 }}>Player A</th><th style={{ padding: 6 }}>Player B</th>
                                <th style={{ padding: 6 }}>Price</th><th style={{ padding: 6 }}>Vol</th>
                                <th style={{ padding: 6 }}></th>
                            </tr></thead>
                            <tbody>
                                {matches.map((m, i) => (
                                    <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                        <td style={{ padding: 6 }}>{m.player_a} {m.rank_a ? `(#${m.rank_a})` : ""}</td>
                                        <td style={{ padding: 6 }}>{m.player_b} {m.rank_b ? `(#${m.rank_b})` : ""}</td>
                                        <td style={{ padding: 6 }}>{m.price_a}-{m.price_b}</td>
                                        <td style={{ padding: 6 }}>{m.volume}</td>
                                        <td style={{ padding: 6 }}>
                                            <button onClick={() => handleSelectMatch(m)}
                                                style={{ padding: "3px 12px", cursor: "pointer", background: "#27ae60", color: "white", border: "none", borderRadius: 3, fontSize: 12 }}>
                                                Track
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                    {matches.length === 0 && searchLoading === false && searchQuery && (
                        <div style={{ color: "#888", fontSize: 13 }}>No active matches found.</div>
                    )}
                </div>
            )}

            {/* Tracking Section */}
            {trackedMatch && (
                <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                        <div>
                            <h3 style={{ margin: 0 }}>
                                {signal?.player_a || trackedMatch.player_a} {signal?.rank_a ? `(#${signal.rank_a})` : ""}
                                {" vs "}
                                {signal?.player_b || trackedMatch.player_b} {signal?.rank_b ? `(#${signal.rank_b})` : ""}
                            </h3>
                            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                                Match start: <strong>{signal?.match_start ? new Date(signal.match_start).toLocaleString() : "detecting..."}</strong>
                                {signal?.minutes_played != null && <> | Minutes played: <strong>{signal.minutes_played}</strong></>}
                            </div>
                        </div>
                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                            <span style={{ fontSize: 12, color: polling ? "#27ae60" : "#e74c3c" }}>
                                {polling ? `Polling every ${pollInterval}s` : "Stopped"}
                            </span>
                            <select value={pollInterval} onChange={e => setPollInterval(Number(e.target.value))} style={{ fontSize: 12, padding: 2 }}>
                                <option value={10}>10s</option><option value={15}>15s</option>
                                <option value={30}>30s</option><option value={60}>60s</option>
                            </select>
                            <button onClick={() => setPolling(!polling)}
                                style={{ padding: "3px 10px", fontSize: 12, cursor: "pointer", background: polling ? "#e74c3c" : "#27ae60", color: "white", border: "none", borderRadius: 3 }}>
                                {polling ? "Pause" : "Resume"}
                            </button>
                            <button onClick={handleStop} style={{ padding: "3px 10px", fontSize: 12, cursor: "pointer" }}>Back</button>
                        </div>
                    </div>

                    {/* Signal Box */}
                    {signal && (
                        <div style={{ padding: 16, border: `3px solid ${sigColor}`, borderRadius: 8, marginBottom: 16 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontSize: 28, fontWeight: 700, color: sigColor }}>{signal.recommendation}</div>
                                <div style={{ textAlign: "right", fontSize: 13 }}>
                                    <div>Price: <strong>{signal.current_price_a}</strong> - <strong>{100 - signal.current_price_a}</strong></div>
                                    {signal.buy_price != null && <div>Buy at: <strong>{signal.buy_price}c x{signal.contracts}</strong></div>}
                                </div>
                            </div>
                            <div style={{ fontSize: 13, marginTop: 8, display: "flex", gap: 24 }}>
                                <span>{signal.player_a}: <strong>{signal.score_a}</strong> (p:{signal.player_score_a} g:{signal.global_score_a})</span>
                                <span>{signal.player_b}: <strong>{signal.score_b}</strong> (p:{signal.player_score_b} g:{signal.global_score_b})</span>
                                <span>Diff: <strong>{signal.score_diff}</strong></span>
                            </div>
                        </div>
                    )}

                    {/* Charts */}
                    {history.length > 1 && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                            <div>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Price</div>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={history}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="time" fontSize={10} interval="preserveStartEnd" />
                                        <YAxis domain={[0, 100]} fontSize={10} />
                                        <Tooltip contentStyle={{ fontSize: 12 }} />
                                        <ReferenceLine y={50} stroke="#ccc" strokeDasharray="3 3" />
                                        <Line type="monotone" dataKey="price_a" stroke="#3498db" name={signal?.player_a || "A"} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="price_b" stroke="#e74c3c" name={signal?.player_b || "B"} dot={false} strokeWidth={2} />
                                        <Legend fontSize={11} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                            <div>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Score & Signal</div>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={history}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="time" fontSize={10} interval="preserveStartEnd" />
                                        <YAxis fontSize={10} />
                                        <Tooltip contentStyle={{ fontSize: 12 }} />
                                        <ReferenceLine y={0} stroke="#ccc" strokeDasharray="3 3" />
                                        <Line type="monotone" dataKey="score_a" stroke="#3498db" name={`${signal?.player_a || "A"} score`} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="score_b" stroke="#e74c3c" name={`${signal?.player_b || "B"} score`} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="diff" stroke="#2ecc71" name="Diff" dot={false} strokeWidth={2} strokeDasharray="5 5" />
                                        <Legend fontSize={11} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    )}

                    {/* Triggered Rules */}
                    {signal && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 12, marginBottom: 16 }}>
                            <div>
                                <strong>{signal.player_a} player ({signal.triggered_a?.length || 0}):</strong>
                                {signal.triggered_a?.map((r: any, i: number) => (
                                    <div key={i} style={{ color: r.win_rate >= 50 ? "#27ae60" : "#e74c3c" }}>
                                        {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                    </div>
                                ))}
                                {signal.global_triggered_a?.length > 0 && (
                                    <>
                                        <strong style={{ marginTop: 6, display: "block" }}>Global ({signal.global_triggered_a.length}):</strong>
                                        {signal.global_triggered_a.map((r: any, i: number) => (
                                            <div key={`g${i}`} style={{ color: r.win_rate >= 50 ? "#2ecc71" : "#e67e22", fontStyle: "italic" }}>
                                                {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                            <div>
                                <strong>{signal.player_b} player ({signal.triggered_b?.length || 0}):</strong>
                                {signal.triggered_b?.map((r: any, i: number) => (
                                    <div key={i} style={{ color: r.win_rate >= 50 ? "#27ae60" : "#e74c3c" }}>
                                        {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                    </div>
                                ))}
                                {signal.global_triggered_b?.length > 0 && (
                                    <>
                                        <strong style={{ marginTop: 6, display: "block" }}>Global ({signal.global_triggered_b.length}):</strong>
                                        {signal.global_triggered_b.map((r: any, i: number) => (
                                            <div key={`g${i}`} style={{ color: r.win_rate >= 50 ? "#2ecc71" : "#e67e22", fontStyle: "italic" }}>
                                                {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                        </div>
                    )}

                    {/* History Table */}
                    {history.length > 0 && (
                        <div>
                            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>History ({history.length} polls)</div>
                            <div style={{ maxHeight: 200, overflow: "auto" }}>
                                <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse" }}>
                                    <thead><tr style={{ borderBottom: "2px solid #ddd" }}>
                                        <th style={{ padding: 3 }}>Time</th><th style={{ padding: 3 }}>Price</th>
                                        <th style={{ padding: 3 }}>Score A</th><th style={{ padding: 3 }}>Score B</th>
                                        <th style={{ padding: 3 }}>Diff</th><th style={{ padding: 3 }}>Signal</th>
                                    </tr></thead>
                                    <tbody>
                                        {[...history].reverse().map((h, i) => {
                                            const sc = h.strength === "STRONG" ? "#27ae60" : h.strength === "MODERATE" ? "#e67e22" : "#888";
                                            return (
                                                <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                                    <td style={{ padding: 3 }}>{h.time}</td>
                                                    <td style={{ padding: 3, textAlign: "right" }}>{h.price_a}</td>
                                                    <td style={{ padding: 3, textAlign: "right" }}>{h.score_a}</td>
                                                    <td style={{ padding: 3, textAlign: "right" }}>{h.score_b}</td>
                                                    <td style={{ padding: 3, textAlign: "right", fontWeight: 700 }}>{h.diff}</td>
                                                    <td style={{ padding: 3, color: sc, fontWeight: 600 }}>{h.rec}</td>
                                                </tr>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function TradingPage() {
    const [monitorRunning, setMonitorRunning] = useState(false);
    const [matches, setMatches] = useState<any[]>([]);
    const [trades, setTrades] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    const loadStatus = async () => {
        try {
            const data = await fetchMonitorStatus();
            setMonitorRunning(data.running);
            setMatches(data.matches);
            setTrades(data.trades);
        } catch {}
    };

    useEffect(() => {
        loadStatus();
        const interval = setInterval(loadStatus, 10000);
        return () => clearInterval(interval);
    }, []);

    const handleToggle = async () => {
        setLoading(true);
        try {
            if (monitorRunning) {
                await monitorStop();
            } else {
                await monitorStart();
            }
            await loadStatus();
        } catch {}
        setLoading(false);
    };

    return (
        <div style={{ padding: 20 }}>
            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                <h3 style={{ marginTop: 0 }}>Auto Trading Monitor</h3>
                <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 12 }}>
                    <button onClick={handleToggle} disabled={loading}
                        style={{ padding: "8px 20px", cursor: "pointer",
                            background: monitorRunning ? "#e74c3c" : "#27ae60",
                            color: "white", border: "none", borderRadius: 4 }}>
                        {monitorRunning ? "Stop Monitor" : "Start Monitor"}
                    </button>
                    <span style={{ color: monitorRunning ? "#27ae60" : "#888" }}>
                        {monitorRunning ? "Running (polls every 15s)" : "Stopped"}
                    </span>
                </div>
                <div style={{ fontSize: 12, color: "#888" }}>
                    Monitors active Kalshi tennis matches. Buys YES at 87-91 when: init price 0-80, player ranked higher.
                </div>
            </div>

            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20, marginBottom: 20 }}>
                <h3 style={{ marginTop: 0 }}>Monitored Matches ({matches.length})</h3>
                {matches.length === 0 ? (
                    <p style={{ color: "#888" }}>No matches being monitored.</p>
                ) : (
                    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                        <thead>
                            <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Player</th>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Opponent</th>
                                <th style={{ padding: "4px 8px" }}>Rank</th>
                                <th style={{ padding: "4px 8px" }}>Scheduled</th>
                                <th style={{ padding: "4px 8px" }}>Init</th>
                                <th style={{ padding: "4px 8px" }}>Current</th>
                                <th style={{ padding: "4px 8px" }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {matches.map((m, i) => (
                                <tr key={i} style={{ borderBottom: "1px solid #eee",
                                    background: m.status === "traded" ? "#eafaf1" : m.current_price >= 87 && m.current_price <= 91 ? "#fef9e7" : "white" }}>
                                    <td style={{ padding: "4px 8px", fontWeight: 600 }}>{m.player}</td>
                                    <td style={{ padding: "4px 8px" }}>{m.opponent}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>#{m.player_ranking} vs #{m.opponent_ranking}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", fontSize: 11, color: "#888" }}>
                                        {m.scheduled_time ? new Date(m.scheduled_time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                                    </td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{m.initial_price ?? "—"}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 600,
                                        color: m.current_price >= 87 && m.current_price <= 91 ? "#e67e22" : m.current_price >= 92 ? "#27ae60" : "#333" }}>
                                        {m.current_price}
                                    </td>
                                    <td style={{ padding: "4px 8px", textAlign: "right",
                                        color: m.status === "traded" ? "#27ae60" : m.status === "completed" ? "#888" : "#3498db" }}>
                                        {m.status}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20 }}>
                <h3 style={{ marginTop: 0 }}>Trade Log ({trades.length})</h3>
                {trades.length === 0 ? (
                    <p style={{ color: "#888" }}>No trades yet.</p>
                ) : (
                    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                        <thead>
                            <tr style={{ borderBottom: "2px solid #ddd", textAlign: "right" }}>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Time</th>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Player</th>
                                <th style={{ textAlign: "left", padding: "4px 8px" }}>Opponent</th>
                                <th style={{ padding: "4px 8px" }}>Init</th>
                                <th style={{ padding: "4px 8px" }}>Price</th>
                                <th style={{ padding: "4px 8px" }}>Qty</th>
                                <th style={{ padding: "4px 8px" }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {trades.map((t, i) => (
                                <tr key={i} style={{ borderBottom: "1px solid #eee",
                                    background: t.status === "failed" ? "#fdecea" : "white" }}>
                                    <td style={{ padding: "4px 8px", fontSize: 11 }}>{t.created_at?.substring(0, 19)}</td>
                                    <td style={{ padding: "4px 8px", fontWeight: 600 }}>{t.player}</td>
                                    <td style={{ padding: "4px 8px" }}>{t.opponent}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.initial_price}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right", fontWeight: 600 }}>{t.price}c</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right" }}>{t.count}</td>
                                    <td style={{ padding: "4px 8px", textAlign: "right",
                                        color: t.status === "placed" ? "#27ae60" : t.status === "failed" ? "#e74c3c" : "#888" }}>
                                        {t.status}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function AutoTradingPage() {
    const [running, setRunning] = useState(false);
    const [matches, setMatches] = useState<any[]>([]);
    const [trades, setTrades] = useState<any[]>([]);
    const [summary, setSummary] = useState<any>({});
    const [balance, setBalance] = useState<number | null>(null);
    const [balanceHistory, setBalanceHistory] = useState<any[]>([]);
    const [selectedMatch, setSelectedMatch] = useState<string | null>(null);
    const [matchDetail, setMatchDetail] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [completedPage, setCompletedPage] = useState(1);
    const [completedPages, setCompletedPages] = useState(1);
    const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const loadStatus = async (page?: number) => {
        try {
            const data = await autoTradingStatus(page || completedPage);
            setRunning(data.running);
            setMatches(data.matches || []);
            setTrades(data.trades || []);
            setSummary(data.summary || {});
            if (data.summary?.completed_pages) setCompletedPages(data.summary.completed_pages);
        } catch {}
    };

    const loadBalance = async () => {
        try {
            const data = await autoTradingBalance();
            if (data.balance != null) setBalance(data.balance);
            if (data.history?.length > 0) setBalanceHistory(data.history);
        } catch {}
    };

    useEffect(() => {
        loadStatus();
        loadBalance();
        intervalRef.current = setInterval(() => { loadStatus(); loadBalance(); }, 15000);
        return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    }, []);

    const handleToggle = async () => {
        setLoading(true);
        if (running) {
            await autoTradingStop();
        } else {
            await autoTradingStart();
        }
        await loadStatus();
        setLoading(false);
    };

    const handleDiscover = async () => {
        setLoading(true);
        await autoTradingDiscover();
        await loadStatus();
        setLoading(false);
    };

    const [selectedMatchData, setSelectedMatchData] = useState<any>(null);
    const openMatch = async (m: any) => {
        setSelectedMatch(m.event_ticker);
        setSelectedMatchData(m);
        try {
            const data = await autoTradingMatchDetail(m.event_ticker);
            setMatchDetail(data);
        } catch {}
    };

    const statusColor = (s: string) => s === "in_progress" ? "#27ae60" : s === "upcoming" ? "#3498db" : "#888";
    const sigColor = (s: string) => s === "STRONG" ? "#27ae60" : s === "MODERATE" ? "#e67e22" : s === "WEAK" ? "#888" : "#ccc";

    // Live Signal state for detail view
    const [detailSignal, setDetailSignal] = useState<any>(null);
    const [detailHistory, setDetailHistory] = useState<any[]>([]);
    const detailMatchStartRef = useRef<string | null>(null);
    const detailInitPriceRef = useRef<number | null>(null);
    const detailRunningMinRef = useRef<number | null>(null);
    const detailRunningMaxRef = useRef<number | null>(null);
    const detailPrevPriceRef = useRef<number | null>(null);

    const doPollDetail = useCallback(async () => {
        if (!selectedMatch || !selectedMatchData) return;
        const m = selectedMatchData;
        try {
            const result = await pollLiveMatch({
                event_ticker: m.event_ticker,
                ticker_a: m.ticker_a,
                init_price: detailInitPriceRef.current ?? undefined,
                running_min: detailRunningMinRef.current ?? undefined,
                running_max: detailRunningMaxRef.current ?? undefined,
                match_start: detailMatchStartRef.current ?? undefined,
                prev_price: detailPrevPriceRef.current ?? undefined,
            });
            if (result.error || result.status === "closed") return;

            const rawPrice = result.raw_price;
            if (detailInitPriceRef.current === null) detailInitPriceRef.current = rawPrice;
            detailRunningMinRef.current = result.running_min;
            detailRunningMaxRef.current = result.running_max;
            detailPrevPriceRef.current = rawPrice;

            if (result.match_start && !detailMatchStartRef.current) {
                detailMatchStartRef.current = result.match_start;
                try {
                    const bf = await backfillLiveMatch({
                        event_ticker: m.event_ticker,
                        ticker_a: m.ticker_a,
                        match_start: result.match_start,
                    });
                    if (bf.history?.length > 0) {
                        if (bf.raw_init_price != null) detailInitPriceRef.current = bf.raw_init_price;
                        setDetailHistory(bf.history.map((h: any) => ({
                            ...h,
                            time: new Date(h.time).toLocaleTimeString(),
                            rec: "",
                            strength: "",
                        })));
                    }
                } catch {}
            }

            setDetailSignal(result);
            setDetailHistory(prev => {
                const next = [...prev, {
                    time: new Date().toLocaleTimeString(),
                    minutes: result.minutes_played || 0,
                    price_a: result.current_price_a,
                    price_b: 100 - result.current_price_a,
                    score_a: result.score_a,
                    score_b: result.score_b,
                    diff: result.score_diff,
                    rec: result.recommendation,
                    strength: result.strength,
                }];
                return next.length > 500 ? next.slice(-500) : next;
            });
        } catch {}
    }, [selectedMatch, selectedMatchData]);

    useEffect(() => {
        if (!selectedMatch || !selectedMatchData) return;
        // Reset state
        detailMatchStartRef.current = null;
        detailInitPriceRef.current = null;
        detailRunningMinRef.current = null;
        detailRunningMaxRef.current = null;
        detailPrevPriceRef.current = null;
        setDetailSignal(null);
        setDetailHistory([]);
        // Load trades
        autoTradingMatchDetail(selectedMatch).then(d => setMatchDetail(d)).catch(() => {});
        // Start polling
        doPollDetail();
        const iv = setInterval(doPollDetail, 15000);
        return () => clearInterval(iv);
    }, [selectedMatch, selectedMatchData]);

    if (selectedMatch) {
        const sig = detailSignal;
        const md = selectedMatchData;
        const mTrades = matchDetail?.trades || [];
        const settled = mTrades.filter((t: any) => t.status === "settled");
        const totalPnl = settled.reduce((s: number, t: any) => s + (t.pnl || 0), 0);
        const sigC = sig?.strength === "STRONG" ? "#27ae60" : sig?.strength === "MODERATE" ? "#e67e22" : sig?.strength === "WEAK" ? "#888" : "#ccc";

        return (
            <div style={{ padding: 20 }}>
                <button onClick={() => { setSelectedMatch(null); setSelectedMatchData(null); setMatchDetail(null); setDetailSignal(null); setDetailHistory([]); }}
                    style={{ marginBottom: 12, cursor: "pointer" }}>Back to List</button>
                <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 20 }}>
                    {/* Header — show from match data immediately, update when signal arrives */}
                    <div>
                        <h3 style={{ margin: 0 }}>
                            {sig?.player_a || md?.player_a || "..."} {(sig?.rank_a || md?.rank_a) ? `(#${sig?.rank_a || md?.rank_a})` : ""}
                            {" vs "}
                            {sig?.player_b || md?.player_b || "..."} {(sig?.rank_b || md?.rank_b) ? `(#${sig?.rank_b || md?.rank_b})` : ""}
                        </h3>
                        <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                            {sig ? (
                                <>Match start: <strong>{sig.match_start ? new Date(sig.match_start).toLocaleString() : "detecting..."}</strong>
                                {sig.minutes_played != null && <> | Minutes played: <strong>{sig.minutes_played}</strong></>}</>
                            ) : (
                                <span>Loading signal... (first load may take 10-20s for FlashScore)</span>
                            )}
                        </div>
                    </div>

                    {/* Signal Box */}
                    {sig && (
                        <div style={{ padding: 16, border: `3px solid ${sigC}`, borderRadius: 8, marginTop: 12, marginBottom: 16 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ fontSize: 28, fontWeight: 700, color: sigC }}>{sig.recommendation}</div>
                                <div style={{ textAlign: "right", fontSize: 13 }}>
                                    <div>Price: <strong>{sig.current_price_a}</strong> - <strong>{100 - sig.current_price_a}</strong></div>
                                    {sig.buy_price != null && <div>Buy at: <strong>{sig.buy_price}c x{sig.contracts}</strong></div>}
                                </div>
                            </div>
                            <div style={{ fontSize: 13, marginTop: 8, display: "flex", gap: 24 }}>
                                <span>{sig.player_a}: <strong>{sig.score_a}</strong> (p:{sig.player_score_a} g:{sig.global_score_a})</span>
                                <span>{sig.player_b}: <strong>{sig.score_b}</strong> (p:{sig.player_score_b} g:{sig.global_score_b})</span>
                                <span>Diff: <strong>{sig.score_diff}</strong></span>
                            </div>
                        </div>
                    )}

                    {/* Charts */}
                    {detailHistory.length > 1 && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
                            <div>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Price</div>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={detailHistory}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="time" fontSize={10} interval="preserveStartEnd" />
                                        <YAxis domain={[0, 100]} fontSize={10} />
                                        <Tooltip contentStyle={{ fontSize: 12 }} />
                                        <ReferenceLine y={50} stroke="#ccc" strokeDasharray="3 3" />
                                        <Line type="monotone" dataKey="price_a" stroke="#3498db" name={sig?.player_a || "A"} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="price_b" stroke="#e74c3c" name={sig?.player_b || "B"} dot={false} strokeWidth={2} />
                                        <Legend fontSize={11} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                            <div>
                                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Score & Signal</div>
                                <ResponsiveContainer width="100%" height={200}>
                                    <LineChart data={detailHistory}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="time" fontSize={10} interval="preserveStartEnd" />
                                        <YAxis fontSize={10} />
                                        <Tooltip contentStyle={{ fontSize: 12 }} />
                                        <ReferenceLine y={0} stroke="#ccc" strokeDasharray="3 3" />
                                        <Line type="monotone" dataKey="score_a" stroke="#3498db" name={`${sig?.player_a || "A"} score`} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="score_b" stroke="#e74c3c" name={`${sig?.player_b || "B"} score`} dot={false} strokeWidth={2} />
                                        <Line type="monotone" dataKey="diff" stroke="#2ecc71" name="Diff" dot={false} strokeWidth={2} strokeDasharray="5 5" />
                                        <Legend fontSize={11} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    )}

                    {/* Triggered Rules */}
                    {sig && (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, fontSize: 12, marginBottom: 16 }}>
                            <div>
                                <strong>{sig.player_a} player ({sig.triggered_a?.length || 0}):</strong>
                                {sig.triggered_a?.map((r: any, i: number) => (
                                    <div key={i} style={{ color: r.win_rate >= 50 ? "#27ae60" : "#e74c3c" }}>
                                        {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                    </div>
                                ))}
                                {sig.global_triggered_a?.length > 0 && (
                                    <>
                                        <strong style={{ marginTop: 6, display: "block" }}>Global ({sig.global_triggered_a.length}):</strong>
                                        {sig.global_triggered_a.map((r: any, i: number) => (
                                            <div key={`g${i}`} style={{ color: r.win_rate >= 50 ? "#2ecc71" : "#e67e22", fontStyle: "italic" }}>
                                                {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                            <div>
                                <strong>{sig.player_b} player ({sig.triggered_b?.length || 0}):</strong>
                                {sig.triggered_b?.map((r: any, i: number) => (
                                    <div key={i} style={{ color: r.win_rate >= 50 ? "#27ae60" : "#e74c3c" }}>
                                        {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                    </div>
                                ))}
                                {sig.global_triggered_b?.length > 0 && (
                                    <>
                                        <strong style={{ marginTop: 6, display: "block" }}>Global ({sig.global_triggered_b.length}):</strong>
                                        {sig.global_triggered_b.map((r: any, i: number) => (
                                            <div key={`g${i}`} style={{ color: r.win_rate >= 50 ? "#2ecc71" : "#e67e22", fontStyle: "italic" }}>
                                                {r.category}/{r.condition}: {r.win_rate}% (N={r.sample_size})
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Trade History for this match */}
                    <div style={{ marginTop: 8 }}>
                        <h4 style={{ marginTop: 0 }}>
                            Trades ({mTrades.length})
                            {settled.length > 0 && (
                                <span style={{ fontSize: 13, fontWeight: 400, marginLeft: 12, color: totalPnl >= 0 ? "#27ae60" : "#e74c3c" }}>
                                    P&L: ${(totalPnl / 100).toFixed(2)} | Won: {settled.filter((t: any) => t.won).length}/{settled.length}
                                </span>
                            )}
                        </h4>
                        {mTrades.length === 0 ? (
                            <div style={{ color: "#888", fontSize: 13 }}>No trades placed for this match.</div>
                        ) : (
                            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                                <thead><tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                                    <th style={{ padding: 4 }}>Time</th><th style={{ padding: 4 }}>Player</th>
                                    <th style={{ padding: 4 }}>Side</th><th style={{ padding: 4 }}>Price</th>
                                    <th style={{ padding: 4 }}>Qty</th><th style={{ padding: 4 }}>Diff</th>
                                    <th style={{ padding: 4 }}>Status</th><th style={{ padding: 4 }}>P&L</th>
                                </tr></thead>
                                <tbody>
                                    {mTrades.map((t: any, i: number) => (
                                        <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                            <td style={{ padding: 4 }}>{t.created_at ? new Date(t.created_at).toLocaleTimeString() : ""}</td>
                                            <td style={{ padding: 4 }}>{t.player}</td>
                                            <td style={{ padding: 4 }}>{t.side}</td>
                                            <td style={{ padding: 4 }}>{t.price}c</td>
                                            <td style={{ padding: 4 }}>x{t.contracts}</td>
                                            <td style={{ padding: 4 }}>{t.score_diff}</td>
                                            <td style={{ padding: 4, color: t.status === "placed" ? "#3498db" : t.won ? "#27ae60" : "#e74c3c", fontWeight: 600 }}>
                                                {t.status}{t.won != null ? (t.won ? " (W)" : " (L)") : ""}
                                            </td>
                                            <td style={{ padding: 4, fontWeight: 600, color: (t.pnl || 0) >= 0 ? "#27ae60" : "#e74c3c" }}>
                                                {t.pnl != null ? `$${(t.pnl / 100).toFixed(2)}` : "-"}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={{ padding: 20 }}>
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <div>
                    <span style={{ fontSize: 14 }}>
                        Balance: <strong>${balance != null ? balance.toFixed(2) : "..."}</strong>
                        {" | "}In Progress: <strong>{summary.active || 0}</strong>
                        {" | "}Upcoming: <strong>{summary.upcoming || 0}</strong>
                        {" | "}Trades: <strong>{summary.total_trades || 0}</strong>
                    </span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={async () => { setLoading(true); await autoTradingPrepare(); setLoading(false); }} disabled={loading}
                        style={{ padding: "6px 14px", cursor: "pointer", fontSize: 12, border: "1px solid #ddd", borderRadius: 4 }}>
                        {loading ? "..." : "Prepare Matches"}
                    </button>
                    <button onClick={handleToggle} disabled={loading}
                        style={{ padding: "6px 20px", cursor: "pointer", fontSize: 13, fontWeight: 600,
                                 background: running ? "#e74c3c" : "#27ae60", color: "white", border: "none", borderRadius: 4 }}>
                        {loading ? "..." : running ? "Stop Auto Trading" : "Start Auto Trading"}
                    </button>
                </div>
            </div>

            {/* Balance Chart */}
            {balanceHistory.length > 1 && (
                <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 16 }}>
                    <h4 style={{ marginTop: 0 }}>Balance History</h4>
                    <ResponsiveContainer width="100%" height={150}>
                        <LineChart data={balanceHistory}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="time" fontSize={9} interval="preserveStartEnd"
                                tickFormatter={(t: string) => new Date(t).toLocaleTimeString()} />
                            <YAxis fontSize={10} domain={['auto', 'auto']} />
                            <Tooltip contentStyle={{ fontSize: 12 }}
                                labelFormatter={(t: string) => new Date(t).toLocaleString()} />
                            <Line type="monotone" dataKey="balance" stroke="#3498db" dot={false} strokeWidth={2} name="Balance ($)" />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* P&L Summary */}
            {trades.length > 0 && (() => {
                const settled = trades.filter(t => t.status === 'settled');
                const wins = settled.filter(t => t.won);
                const totalPnl = settled.reduce((s, t) => s + (t.pnl || 0), 0);
                return settled.length > 0 ? (
                    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 16, display: "flex", gap: 24, fontSize: 13 }}>
                        <span>Settled: <strong>{settled.length}</strong></span>
                        <span>Won: <strong style={{ color: "#27ae60" }}>{wins.length}</strong></span>
                        <span>Lost: <strong style={{ color: "#e74c3c" }}>{settled.length - wins.length}</strong></span>
                        <span>WR: <strong>{(wins.length/settled.length*100).toFixed(1)}%</strong></span>
                        <span>P&L: <strong style={{ color: totalPnl >= 0 ? "#27ae60" : "#e74c3c" }}>${(totalPnl/100).toFixed(2)}</strong></span>
                    </div>
                ) : null;
            })()}

            {/* Match List */}
            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 16 }}>
                {(() => {
                    const active = matches.filter(m => m.status === "upcoming" || m.status === "in_progress");
                    return <>
                <h4 style={{ marginTop: 0 }}>Trading Matches ({active.length})</h4>
                {active.length === 0 && <div style={{ color: "#888", fontSize: 13 }}>No active matches.</div>}
                <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                    <thead><tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                        <th style={{ padding: 4 }}>Status</th>
                        <th style={{ padding: 4 }}>Match</th>
                        <th style={{ padding: 4 }}>Ranks</th>
                        <th style={{ padding: 4 }}>Start Time</th>
                        <th style={{ padding: 4 }}>Price</th>
                        <th style={{ padding: 4 }}>Signal</th>
                        <th style={{ padding: 4 }}></th>
                    </tr></thead>
                    <tbody>
                        {active.map((m, i) => (
                            <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                <td style={{ padding: 4 }}>
                                    <span style={{ color: statusColor(m.status), fontWeight: 600 }}>{m.status}</span>
                                </td>
                                <td style={{ padding: 4 }}>{m.player_a} vs {m.player_b}</td>
                                <td style={{ padding: 4 }}>#{m.rank_a} vs #{m.rank_b}</td>
                                <td style={{ padding: 4, fontSize: 11 }}>{m.match_start ? new Date(m.match_start).toLocaleString() : <span style={{ color: "#e74c3c" }}>unknown</span>}</td>
                                <td style={{ padding: 4 }}>{m.current_price || "-"}</td>
                                <td style={{ padding: 4, color: sigColor(m.last_rec?.split(" ")[0] || ""), fontWeight: 600, fontSize: 11 }}>
                                    {m.last_rec || "-"}
                                </td>
                                <td style={{ padding: 4 }}>
                                    <button onClick={() => openMatch(m)}
                                        style={{ padding: "2px 8px", cursor: "pointer", fontSize: 11 }}>
                                        Details
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
                </>;
                })()}
            </div>

            {/* Completed Matches */}
            <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16 }}>
                <h4 style={{ marginTop: 0 }}>Completed Matches</h4>
                {(() => {
                    const matchTrades = (et: string) => trades.filter(t => t.event_ticker === et);
                    const completed = matches.filter(m => m.status === "completed" && matchTrades(m.event_ticker).length > 0);
                    if (completed.length === 0) return <div style={{ color: "#888", fontSize: 13 }}>No completed trades yet.</div>;
                    return (<>
                        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                            <thead><tr style={{ borderBottom: "2px solid #ddd", textAlign: "left" }}>
                                <th style={{ padding: 4 }}>Match</th><th style={{ padding: 4 }}>Time</th>
                                <th style={{ padding: 4 }}>Trades</th><th style={{ padding: 4 }}>Won</th>
                                <th style={{ padding: 4 }}>P&L</th><th style={{ padding: 4 }}></th>
                            </tr></thead>
                            <tbody>
                                {completed.map((m, i) => {
                                    const mt = matchTrades(m.event_ticker);
                                    const settled = mt.filter(t => t.status === "settled");
                                    const wins = settled.filter(t => t.won);
                                    const pnl = settled.reduce((s: number, t: any) => s + (t.pnl || 0), 0);
                                    return (
                                        <tr key={i} style={{ borderBottom: "1px solid #eee" }}>
                                            <td style={{ padding: 4 }}>{m.player_a} vs {m.player_b}</td>
                                            <td style={{ padding: 4, fontSize: 11 }}>{m.match_start ? new Date(m.match_start).toLocaleString() : "-"}</td>
                                            <td style={{ padding: 4 }}>{mt.length}</td>
                                            <td style={{ padding: 4 }}>{wins.length}/{settled.length}</td>
                                            <td style={{ padding: 4, fontWeight: 600, color: pnl >= 0 ? "#27ae60" : "#e74c3c" }}>
                                                {settled.length > 0 ? `$${(pnl/100).toFixed(2)}` : "-"}
                                            </td>
                                            <td style={{ padding: 4 }}>
                                                <button onClick={() => openMatch(m)}
                                                    style={{ padding: "2px 8px", cursor: "pointer", fontSize: 11 }}>Details</button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        {completedPages > 1 && (
                            <div style={{ marginTop: 8, display: "flex", gap: 8, justifyContent: "center" }}>
                                <button disabled={completedPage <= 1} onClick={() => { setCompletedPage(p => p-1); loadStatus(completedPage-1); }}
                                    style={{ cursor: "pointer", padding: "2px 8px" }}>Prev</button>
                                <span style={{ fontSize: 12 }}>Page {completedPage} / {completedPages}</span>
                                <button disabled={completedPage >= completedPages} onClick={() => { setCompletedPage(p => p+1); loadStatus(completedPage+1); }}
                                    style={{ cursor: "pointer", padding: "2px 8px" }}>Next</button>
                            </div>
                        )}
                    </>);
                })()}
            </div>
        </div>
    );
}

function AppContent() {
    const location = useLocation();
    const currentPath = location.pathname;

    return (
        <div style={{ maxWidth: 900, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
            <h1>Tennis Odds Tool</h1>
            <NavBar />
            <div style={{ display: currentPath === "/winrates" || currentPath === "/" ? "block" : "none" }}>
                <WinRatesPage />
            </div>
            <div style={{ display: currentPath === "/comeback" ? "block" : "none" }}>
                <ComebackPage />
            </div>
            <div style={{ display: currentPath === "/closeout" ? "block" : "none" }}>
                <CloseoutPage />
            </div>
            <div style={{ display: currentPath === "/live" ? "block" : "none" }}>
                <LiveSignalPage />
            </div>
            <div style={{ display: currentPath === "/auto" ? "block" : "none" }}>
                <AutoTradingPage />
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
