import { Link, useLocation } from "react-router-dom";

export default function NavBar() {
    const location = useLocation();

    const linkStyle = (path: string) => ({
        padding: "8px 16px",
        textDecoration: "none",
        fontWeight: location.pathname === path ? 700 : 400,
        color: location.pathname === path ? "#3498db" : "#333",
        borderBottom: location.pathname === path ? "2px solid #3498db" : "2px solid transparent",
    });

    return (
        <nav style={{ display: "flex", gap: 8, borderBottom: "1px solid #ddd", marginBottom: 20 }}>
            <Link to="/" style={linkStyle("/")}>Query Tool</Link>
            <Link to="/simulate" style={linkStyle("/simulate")}>Match Simulator</Link>
        </nav>
    );
}
