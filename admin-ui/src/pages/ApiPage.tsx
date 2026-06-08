import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  api,
  ApiCoverageMatch,
  ApiSyncConfig,
  ApiSyncStatus,
} from "../api";

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
      {m.has_api_prediction && (
        <span className="badge ok" title="API-Football prediction">P</span>
      )}
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
  confirm?: string;
}[] = [
  { id: "link", label: "Link matches", hint: "API-Football + Odds API" },
  { id: "leagues", label: "Sync leagues", hint: "competitions" },
  { id: "odds", label: "Fetch odds", hint: "Odds API + API-Football odds + /predictions" },
  { id: "predictions", label: "Fetch predictions", hint: "API-Football /predictions backfill" },
  { id: "form", label: "Team form", hint: "48h window" },
  { id: "lineups", label: "Lineups", hint: "< 2h to kickoff" },
  { id: "stats", label: "Post-match stats", hint: "FT only" },
  { id: "logos", label: "Team logos", hint: "API-Football CDN" },
  { id: "cleanup", label: "Cleanup AI cache", hint: "expired rows" },
  { id: "cleanup_data", label: "Cleanup old data", hint: "odds history, finished odds" },
  {
    id: "prune_odds",
    label: "Prune odds",
    hint: "Удалить строки вне разрешённых рынков (config)",
    confirm:
      "Удалить из БД коэффициенты с рынками, которых нет в текущих настройках?\n\nПолный reset не выполняется.",
  },
  {
    id: "reset_odds",
    label: "Reset odds & refetch",
    hint: "Удалить ВСЕ match_odds + history, загрузить заново",
    dangerous: true,
    confirm:
      "Удалить ВСЕ коэффициенты (match_odds + odds_history) и загрузить заново по текущему config.ini?\n\nЛинковка матчей (AF/O) не затрагивается.",
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

function ConfigField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="config-field">
      <span className="config-label">{label}</span>
      {children}
      {hint && <span className="config-hint">{hint}</span>}
    </label>
  );
}

export default function ApiPage() {
  const [status, setStatus] = useState<ApiSyncStatus | null>(null);
  const [config, setConfig] = useState<ApiSyncConfig | null>(null);
  const [error, setError] = useState("");
  const [configMsg, setConfigMsg] = useState("");
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const [data, cfg] = await Promise.all([
        api.get<ApiSyncStatus>("/api-sync/status"),
        api.get<ApiSyncConfig>("/api-sync/config"),
      ]);
      setStatus(data);
      setConfig(cfg);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const run = async (action: string, dangerous?: boolean, confirm?: string) => {
    const text =
      confirm ||
      (dangerous
        ? "Подтвердите опасное действие."
        : undefined);
    if (text && !window.confirm(text)) return;
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

  const saveConfig = async () => {
    if (!config) return;
    setSavingConfig(true);
    setConfigMsg("");
    setError("");
    try {
      const res = await api.patch<{
        changed: string[];
        config: ApiSyncConfig;
        message: string;
      }>("/api-sync/config", {
        enabled: config.enabled,
        link_batch_size: config.link_batch_size,
        fixture_refresh_limit: config.fixture_refresh_limit,
        odds_sync_mode: config.odds_sync_mode,
        odds_upcoming_days_ahead: config.odds_upcoming_days_ahead,
        odds_skip_finished_hours: config.odds_skip_finished_hours,
        odds_min_interval_minutes: config.odds_min_interval_minutes,
        api_quota_alert_threshold: config.api_quota_alert_threshold,
        admin_match_odds_limit: config.admin_match_odds_limit,
        the_odds_api: config.the_odds_api,
        api_football: config.api_football,
      });
      setConfig(res.config);
      setConfigMsg(res.message);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setSavingConfig(false);
    }
  };

  const setToa = (patch: Partial<ApiSyncConfig["the_odds_api"]>) => {
    setConfig((c) =>
      c ? { ...c, the_odds_api: { ...c.the_odds_api, ...patch } } : c
    );
  };

  const setAf = (patch: Partial<ApiSyncConfig["api_football"]>) => {
    setConfig((c) =>
      c ? { ...c, api_football: { ...c.api_football, ...patch } } : c
    );
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
      {configMsg && <p style={{ color: "var(--ok)" }}>{configMsg}</p>}
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

      {config && (
        <section className="panel">
          <h3>Настройки сбора данных</h3>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Сохранение записывает в{" "}
            <code>{config.config_path}</code> (секция <code>[api_sync]</code>).
            Scheduler подхватит при следующем cron-запуске.
          </p>

          <div className="config-grid">
            <div>
              <h4>Общие</h4>
              <ConfigField label="api_sync.enabled">
                <select
                  value={config.enabled ? "true" : "false"}
                  onChange={(e) =>
                    setConfig({ ...config, enabled: e.target.value === "true" })
                  }
                >
                  <option value="true">включён</option>
                  <option value="false">выключен</option>
                </select>
              </ConfigField>
              <ConfigField label="odds_sync_mode" hint="db_matches — только лиги из матчей БД">
                <select
                  value={config.odds_sync_mode}
                  onChange={(e) =>
                    setConfig({ ...config, odds_sync_mode: e.target.value })
                  }
                >
                  <option value="db_matches">db_matches</option>
                  <option value="all_leagues">all_leagues</option>
                </select>
              </ConfigField>
              <ConfigField label="odds_upcoming_days_ahead" hint="Окно предстоящих матчей (дней)">
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={config.odds_upcoming_days_ahead}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      odds_upcoming_days_ahead: parseInt(e.target.value, 10) || 7,
                    })
                  }
                />
              </ConfigField>
              <ConfigField label="odds_min_interval_minutes" hint="Троттлинг bulk TOA по sport_key">
                <input
                  type="number"
                  min={0}
                  value={config.odds_min_interval_minutes}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      odds_min_interval_minutes: parseInt(e.target.value, 10) || 0,
                    })
                  }
                />
              </ConfigField>
              <ConfigField label="link_batch_size">
                <input
                  type="number"
                  min={1}
                  value={config.link_batch_size}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      link_batch_size: parseInt(e.target.value, 10) || 20,
                    })
                  }
                />
              </ConfigField>
            </div>

            <div>
              <h4>The Odds API</h4>
              <ConfigField
                label="odds_markets"
                hint="Bulk /sports/{key}/odds — через запятую: h2h,spreads,totals"
              >
                <input
                  type="text"
                  value={config.the_odds_api.odds_markets}
                  onChange={(e) => setToa({ odds_markets: e.target.value })}
                />
              </ConfigField>
              <ConfigField
                label="odds_event_markets"
                hint="Per-event (кредит на матч): btts, draw_no_bet, …"
              >
                <input
                  type="text"
                  value={config.the_odds_api.odds_event_markets}
                  onChange={(e) => setToa({ odds_event_markets: e.target.value })}
                />
              </ConfigField>
              <ConfigField label="odds_event_batch_size">
                <input
                  type="number"
                  min={1}
                  value={config.the_odds_api.odds_event_batch_size}
                  onChange={(e) =>
                    setToa({
                      odds_event_batch_size: parseInt(e.target.value, 10) || 40,
                    })
                  }
                />
              </ConfigField>
            </div>

            <div>
              <h4>API-Football</h4>
              <ConfigField label="api_football_odds_enabled">
                <select
                  value={config.api_football.odds_enabled ? "true" : "false"}
                  onChange={(e) =>
                    setAf({ odds_enabled: e.target.value === "true" })
                  }
                >
                  <option value="true">да</option>
                  <option value="false">нет</option>
                </select>
              </ConfigField>
              <ConfigField
                label="api_football_odds_markets"
                hint="Пусто = из Odds API (Match Winner, Goals Over/Under, …)"
              >
                <input
                  type="text"
                  placeholder="Match Winner,Goals Over/Under,Both Teams Score"
                  value={config.api_football.odds_markets}
                  onChange={(e) => setAf({ odds_markets: e.target.value })}
                />
              </ConfigField>
              <ConfigField label="api_football_odds_days_ahead">
                <input
                  type="number"
                  min={1}
                  value={config.api_football.odds_days_ahead}
                  onChange={(e) =>
                    setAf({
                      odds_days_ahead: parseInt(e.target.value, 10) || 7,
                    })
                  }
                />
              </ConfigField>
              <ConfigField label="api_football_odds_batch_size">
                <input
                  type="number"
                  min={1}
                  value={config.api_football.odds_batch_size}
                  onChange={(e) =>
                    setAf({
                      odds_batch_size: parseInt(e.target.value, 10) || 50,
                    })
                  }
                />
              </ConfigField>
              <ConfigField label="fixture_refresh_limit" hint="Обновление EN competition за link">
                <input
                  type="number"
                  min={1}
                  value={config.fixture_refresh_limit}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      fixture_refresh_limit: parseInt(e.target.value, 10) || 20,
                    })
                  }
                />
              </ConfigField>
            </div>
          </div>

          <button
            type="button"
            onClick={saveConfig}
            disabled={savingConfig}
            style={{ marginTop: "1rem" }}
          >
            {savingConfig ? "Сохранение…" : "Сохранить в config.ini"}
          </button>
        </section>
      )}

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
              {cov.api_football_predictions && (
                <>
                  <h4 style={{ marginTop: "1rem" }}>API-Football /predictions</h4>
                  <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                    С коэффициентами (Fetch odds) · в БД:{" "}
                    {cov.api_football_predictions.stored_count ?? 0}
                    {" · "}
                    ожидают: {cov.api_football_predictions.pending_count ?? 0}
                  </p>
                  {(cov.api_football_predictions.matches ?? []).length === 0 ? (
                    <p style={{ color: "var(--muted)" }}>Все в очереди уже с прогнозом</p>
                  ) : (
                    <table className="compact-table">
                      <tbody>
                        {(cov.api_football_predictions.matches ?? []).map((m) => (
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
                        : k === "match_api_predictions"
                          ? "API-Football predictions"
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
              onClick={() => run(a.id, a.dangerous, a.confirm)}
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
