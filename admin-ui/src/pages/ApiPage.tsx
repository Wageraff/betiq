import { useEffect, useState } from "react";
import { api, ApiSyncStatus } from "../api";

const SYNC_ACTIONS: { id: string; label: string; hint: string }[] = [
  { id: "link", label: "Link matches", hint: "API-Football + Odds API" },
  { id: "leagues", label: "Sync leagues", hint: "competitions" },
  { id: "odds", label: "Fetch odds", hint: "football bulk" },
  { id: "form", label: "Team form", hint: "48h window" },
  { id: "lineups", label: "Lineups", hint: "< 2h to kickoff" },
  { id: "stats", label: "Post-match stats", hint: "FT only" },
  { id: "logos", label: "Team logos", hint: "API-Football CDN" },
  { id: "cleanup", label: "Cleanup AI cache", hint: "expired rows" },
];

function QuotaBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const color = pct > 85 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="quota-bar">
      <div className="quota-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="quota-label">
        {used} / {limit} ({pct}%)
      </span>
    </div>
  );
}

export default function ApiPage() {
  const [status, setStatus] = useState<ApiSyncStatus | null>(null);
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.get<ApiSyncStatus>("/api-sync/status");
      setStatus(data);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const run = async (action: string) => {
    setError("");
    setLog([]);
    try {
      const res = await api.post<{ job_id: string }>("/api-sync/run", { action });
      setJobId(res.job_id);
      const poll = async () => {
        const data = await api.get<{ lines: string[] }>(
          `/api-sync/jobs/${res.job_id}/log`
        );
        setLog(data.lines);
        if (!data.lines.some((l) => l.startsWith("[exit ")))
          setTimeout(poll, 1500);
        else load();
      };
      poll();
    } catch (e) {
      setError(String(e));
    }
  };

  const counts = status?.db_counts;

  return (
    <>
      <h2>Sport API</h2>
      <p style={{ color: "var(--muted)" }}>
        API-Football + The Odds API — синхронизация, лимиты, данные в БД
      </p>
      {error && <p className="error">{error}</p>}
      <div style={{ marginBottom: "1rem" }}>
        <button onClick={load} disabled={loading}>
          {loading ? "Обновление…" : "Обновить статус"}
        </button>
        {status && (
          <span style={{ marginLeft: 12, color: "var(--muted)" }}>
            api_sync: {status.api_sync_enabled ? "включён" : "выключен"}
          </span>
        )}
      </div>

      {status && (
        <div className="api-grid">
          <section className="panel">
            <h3>API-Football</h3>
            {!status.api_football.configured ? (
              <p className="muted">Ключ не задан (API_FOOTBALL_KEY)</p>
            ) : status.api_football.error ? (
              <p className="error">{status.api_football.error}</p>
            ) : (
              <>
                {status.api_football.subscription && (
                  <p>План: {status.api_football.subscription}</p>
                )}
                {status.api_football.limit_day != null &&
                  status.api_football.requests_today != null && (
                    <QuotaBar
                      used={status.api_football.requests_today}
                      limit={status.api_football.limit_day}
                    />
                  )}
                <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                  Запросов сегодня: {status.api_football.requests_today ?? "—"} /{" "}
                  {status.api_football.limit_day ?? "—"}
                </p>
              </>
            )}
          </section>

          <section className="panel">
            <h3>The Odds API</h3>
            {!status.the_odds_api.configured ? (
              <p className="muted">Ключ не задан (THE_ODDS_API_KEY)</p>
            ) : status.the_odds_api.error ? (
              <p className="error">{status.the_odds_api.error}</p>
            ) : (
              <>
                <p>
                  <strong>Осталось кредитов:</strong>{" "}
                  {status.the_odds_api.remaining?.toLocaleString() ?? "—"}
                </p>
                <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                  Использовано (период): {status.the_odds_api.used?.toLocaleString() ?? "—"}
                </p>
              </>
            )}
          </section>
        </div>
      )}

      {counts && (
        <section className="panel">
          <h3>Данные в БД</h3>
          <table className="compact-table">
            <tbody>
              {Object.entries(counts).map(([k, v]) => (
                <tr key={k}>
                  <td>{k}</td>
                  <td>{v.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel">
        <h3>Ручной запуск</h3>
        <div className="sync-actions">
          {SYNC_ACTIONS.map((a) => (
            <button key={a.id} className="secondary" onClick={() => run(a.id)} title={a.hint}>
              {a.label}
            </button>
          ))}
        </div>
        {jobId && (
          <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>job: {jobId}</p>
        )}
        {log.length > 0 && (
          <pre className="job-log">{log.join("\n")}</pre>
        )}
      </section>
    </>
  );
}
