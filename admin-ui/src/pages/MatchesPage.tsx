import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, MatchBrief } from "../api";

const DATE_LOCALE = "en-US";

export default function MatchesPage() {
  const [items, setItems] = useState<MatchBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [sport, setSport] = useState("");
  const [q, setQ] = useState("");
  const [hasAi, setHasAi] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: "1", limit: "50" });
      if (sport) params.set("sport", sport);
      if (q) params.set("q", q);
      if (hasAi) params.set("has_ai", hasAi);
      const data = await api.get<{
        items: MatchBrief[];
        total: number;
      }>(`/matches?${params}`);
      setItems(data.items);
      setTotal(data.total);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <>
      <h2>Matches</h2>
      <div className="filters panel">
        <input
          placeholder="Search teams"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={sport} onChange={(e) => setSport(e.target.value)}>
          <option value="">All sports</option>
          <option value="football">football</option>
          <option value="tennis">tennis</option>
          <option value="volleyball">volleyball</option>
          <option value="hockey">hockey</option>
          <option value="basketball">basketball</option>
        </select>
        <select value={hasAi} onChange={(e) => setHasAi(e.target.value)}>
          <option value="">AI: all</option>
          <option value="true">With AI</option>
          <option value="false">Without AI</option>
        </select>
        <button onClick={load} disabled={loading}>
          Apply
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <p style={{ color: "var(--muted)" }}>Total: {total}</p>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Match</th>
              <th>Sport</th>
              <th>Date (UTC)</th>
              <th>Predictions</th>
              <th>AI</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => (
              <tr key={m.id}>
                <td>
                  <Link to={`/matches/${m.id}`}>{m.id}</Link>
                </td>
                <td>
                  <Link to={`/matches/${m.id}`}>
                    {m.team_home} — {m.team_away}
                  </Link>
                </td>
                <td>{m.sport || "—"}</td>
                <td>
                  {m.match_date
                    ? new Date(m.match_date).toLocaleString(DATE_LOCALE)
                    : "—"}
                </td>
                <td>{m.predictions_count}</td>
                <td>
                  {m.has_ai ? (
                    <span className="badge ok">yes</span>
                  ) : (
                    <span className="badge">no</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        <Link to="/ai">→ AI section</Link> to regenerate summaries
      </p>
    </>
  );
}
