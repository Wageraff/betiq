import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, MatchBrief } from "../api";

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
      <h2>Матчи</h2>
      <div className="filters panel">
        <input
          placeholder="Поиск по командам"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={sport} onChange={(e) => setSport(e.target.value)}>
          <option value="">Все виды спорта</option>
          <option value="football">football</option>
          <option value="tennis">tennis</option>
          <option value="volleyball">volleyball</option>
          <option value="hockey">hockey</option>
          <option value="basketball">basketball</option>
        </select>
        <select value={hasAi} onChange={(e) => setHasAi(e.target.value)}>
          <option value="">AI: все</option>
          <option value="true">С AI</option>
          <option value="false">Без AI</option>
        </select>
        <button onClick={load} disabled={loading}>
          Применить
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <p style={{ color: "var(--muted)" }}>Всего: {total}</p>
      <div className="panel" style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Матч</th>
              <th>Спорт</th>
              <th>Дата (UTC)</th>
              <th>Прогнозов</th>
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
                    ? new Date(m.match_date).toLocaleString("ru-RU")
                    : "—"}
                </td>
                <td>{m.predictions_count}</td>
                <td>
                  {m.has_ai ? (
                    <span className="badge ok">да</span>
                  ) : (
                    <span className="badge">нет</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        <Link to="/ai">→ Раздел AI</Link> для перегенерации сводок
      </p>
    </>
  );
}
