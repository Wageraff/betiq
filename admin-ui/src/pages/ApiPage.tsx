import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiCoverageMatch, ApiSyncStatus } from "../api";

const DATE_LOCALE = "en-US";

function MatchLinks({ m }: { m: ApiCoverageMatch }) {
  return (
    <Link to={`/matches/${m.id}`}>
      {m.team_home} — {m.team_away}
    </Link>
  );
}

function MatchBadges({ m }: { m: ApiCoverageMatch }) {
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      {m.has_api_football && <span className="badge ok" title="API-Football">AF</span>}
      {m.has_the_odds_api && <span className="badge ok" title="The Odds API">O</span>}
      {m.odds_count > 0 && <span className="badge">{m.odds_count}</span>}
      {!m.has_api_football && !m.has_the_odds_api && (
        <span className="badge tier-low" title="Нет привязки">—</span>
      )}
    </span>
  );
}

const SYNC_ACTIONS: {
  id: string;
  label: string;
  hint: string;
  dangerous?: boolean;
}[] = [
  { id: "link", label: "Link matches", hint: "API-Football + Odds API" },
  { id: "leagues", label: "Sync leagues", hint: "competitions" },
  { id: "odds", label: "Fetch odds", hint: "All sports (Odds API) + API-Football" },
  { id: "form", label: "Team form", hint: "48h window" },
  { id: "lineups", label: "Lineups", hint: "< 2h to kickoff" },
  { id: "stats", label: "Post-match stats", hint: "FT only" },
  { id: "logos", label: "Team logos", hint: "API-Football CDN" },
  { id: "cleanup", label: "Cleanup AI cache", hint: "expired rows" },
  { id: "cleanup_data", label: "Cleanup old data", hint: "odds history, finished odds" },
  {
    id: "reset_odds",
    label: "Reset odds & refetch",
    hint: "Удалить ВСЕ match_odds + history, загрузить заново",
    dangerous: true,
  },
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

  const run = async (action: string, dangerous?: boolean) => {
    if (dangerous) {
      const ok = window.confirm(
        "Удалить ВСЕ коэффициенты (match_odds + odds_history) и загрузить заново по текущему config.ini?\n\nЛинковка матчей (AF/O) не затрагивается."
      );
      if (!ok) return;
    }
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
  const cov = status?.coverage;

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

      {cov && (
        <section className="panel">
          <h3>Очередь синка (сейчас в работе)</h3>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Режим: <strong>{cov.odds_sync_mode}</strong>
            {cov.odds_sync_mode === "db_matches"
              ? " — опрашиваются только лиги из предстоящих матчей в БД"
              : " — опрашиваются все зашитые лиги"}
            {" · "}
            предстоящих матчей: {cov.upcoming_total}
            {cov.upcoming_by_sport && Object.keys(cov.upcoming_by_sport).length > 0 && (
              <>
                {" "}
                (
                {Object.entries(cov.upcoming_by_sport)
                  .map(([s, n]) => `${s}: ${n}`)
                  .join(", ")}
                )
              </>
            )}
            {cov.window?.until && (
              <>
                {" · "}
                окно до{" "}
                {new Date(String(cov.window.until)).toLocaleDateString(DATE_LOCALE)}
              </>
            )}
          </p>

          <div className="api-grid" style={{ marginTop: "1rem" }}>
            <div>
              <h4>The Odds API — bulk</h4>
              <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                Лиг за прогон: {cov.the_odds_api.bulk_sport_key_count ?? 0}
                {" · "}
                ~{cov.the_odds_api.bulk_credits_per_run ?? 0} кредитов
                ({cov.the_odds_api.bulk_markets})
              </p>
              {(cov.the_odds_api.bulk_sport_keys ?? []).length === 0 ? (
                <p style={{ color: "var(--muted)" }}>Нет лиг в очереди</p>
              ) : (
                (cov.the_odds_api.bulk_sport_keys ?? []).map((sk) => (
                  <details key={sk.sport_key} style={{ marginBottom: 8 }}>
                    <summary>
                      {sk.sport && <span className="badge">{sk.sport}</span>}{" "}
                      <code>{sk.sport_key}</code> — {sk.label} ({sk.match_count})
                    </summary>
                    <table className="compact-table">
                      <tbody>
                        {sk.matches.map((m) => (
                          <tr key={m.id}>
                            <td><MatchLinks m={m} /></td>
                            <td>{m.competition ?? "—"}</td>
                            <td>
                              {m.match_date
                                ? new Date(m.match_date).toLocaleString(DATE_LOCALE)
                                : "—"}
                            </td>
                            <td><MatchBadges m={m} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </details>
                ))
              )}
              <p style={{ fontSize: "0.85rem", color: "var(--muted)", marginTop: 8 }}>
                Event-odds ({cov.the_odds_api.event_markets}):{" "}
                {cov.the_odds_api.event_match_count ?? 0} матчей
                {" · "}
                ~{cov.the_odds_api.event_credits_per_run ?? 0} кредитов
              </p>
            </div>

            <div>
              <h4>API-Football /odds</h4>
              {cov.api_football_odds.enabled ? (
                <>
                  <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                    В очереди: {cov.api_football_odds.queue_count ?? 0}
                    {" · "}
                    batch {cov.api_football_odds.batch_size}
                  </p>
                  {(cov.api_football_odds.matches ?? []).length === 0 ? (
                    <p style={{ color: "var(--muted)" }}>Нет связанных fixture</p>
                  ) : (
                    <table className="compact-table">
                      <tbody>
                        {(cov.api_football_odds.matches ?? []).map((m) => (
                          <tr key={m.id}>
                            <td><MatchLinks m={m} /></td>
                            <td>{m.competition ?? "—"}</td>
                            <td><MatchBadges m={m} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              ) : (
                <p style={{ color: "var(--muted)" }}>api_football_odds_enabled = false</p>
              )}
            </div>
          </div>

          {(cov.the_odds_api.unmapped_match_count ?? 0) > 0 && (
            <>
              <h4 style={{ marginTop: "1rem" }}>
                Без sport_key The Odds API ({cov.the_odds_api.unmapped_match_count})
              </h4>
              <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                Нет sport_key в Odds API (волейбол/гандбол и др.) — только API-Football для football
              </p>
              <table className="compact-table">
                <tbody>
                  {(cov.the_odds_api.unmapped_matches ?? []).map((m) => (
                    <tr key={m.id}>
                      <td>
                        {m.sport && <span className="badge">{m.sport}</span>}{" "}
                        <MatchLinks m={m} />
                      </td>
                      <td>{m.competition ?? "—"}</td>
                      <td><MatchBadges m={m} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      )}

      {counts && (
        <section className="panel">
          <h3>Данные в БД</h3>
          <table className="compact-table">
            <tbody>
              {Object.entries(counts).map(([k, v]) => (
                <tr key={k}>
                  <td>
                    {k === "match_odds_api_football"
                      ? "match_odds (API-Football)"
                      : k === "match_odds_the_odds_api"
                        ? "match_odds (The Odds API)"
                        : k}
                  </td>
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
            <button
              key={a.id}
              className={a.dangerous ? "warn-btn" : "secondary"}
              onClick={() => run(a.id, a.dangerous)}
              title={a.hint}
            >
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
