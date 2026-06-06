import { useEffect, useMemo, useState } from "react";
import { api, Settings, Source } from "../api";

function fmtDt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function pct(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

function tierLabel(tier: Source["tier"]): string {
  if (tier === "high") return "high";
  if (tier === "low") return "low (full)";
  return "medium";
}

function healthTitle(s: Source): string {
  const st = s.stats;
  if (!st || st.runs === 0) return "Нет запусков за период";
  const parts = [
    `Запусков: ${st.runs}`,
    `Сохранено: ${st.items_saved}`,
    `Ошибок: ${st.errors}`,
    `Пустых: ${st.empty_runs}`,
  ];
  if (st.last_error_at) parts.push(`Посл. ошибка: ${fmtDt(st.last_error_at)}`);
  return parts.join(" · ");
}

type AppLogInfo = {
  path: string;
  exists: boolean;
  size_bytes: number;
  size_human: string;
  modified_at: string | null;
};

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [appLog, setAppLog] = useState<AppLogInfo | null>(null);
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [source, setSource] = useState("beturi");
  const [error, setError] = useState("");
  const [logBusy, setLogBusy] = useState(false);

  const loadLogInfo = async () => {
    try {
      const data = await api.get<AppLogInfo>("/settings/logs");
      setAppLog(data);
    } catch (e) {
      setError(String(e));
    }
  };

  const load = async () => {
    try {
      const data = await api.get<Settings>("/settings");
      setSettings(data);
      await loadLogInfo();
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const statsDays = settings?.sources[0]?.stats?.stats_days ?? 7;

  const sortedSources = useMemo(() => {
    if (!settings) return [];
    const order = { error: 0, warn: 1, idle: 2, ok: 3 };
    return [...settings.sources].sort((a, b) => {
      const ha = a.stats?.health ?? "idle";
      const hb = b.stats?.health ?? "idle";
      if (order[ha] !== order[hb]) return order[ha] - order[hb];
      const ea = a.stats?.error_rate ?? 0;
      const eb = b.stats?.error_rate ?? 0;
      if (eb !== ea) return eb - ea;
      return (b.stats?.items_saved ?? 0) - (a.stats?.items_saved ?? 0);
    });
  }, [settings]);

  const runAction = async (
    path: string,
    body: Record<string, unknown> = {}
  ) => {
    setError("");
    setLog([]);
    try {
      const res = await api.post<{ job_id: string }>(path, body);
      setJobId(res.job_id);
      const poll = async () => {
        const data = await api.get<{ lines: string[] }>(
          `/actions/jobs/${res.job_id}/log`
        );
        setLog(data.lines);
        if (!data.lines.some((l) => l.startsWith("[exit ")))
          setTimeout(poll, 1500);
      };
      poll();
    } catch (e) {
      setError(String(e));
    }
  };

  const toggleSource = async (id: number, active: boolean) => {
    await api.patch(`/settings/sources/${id}`, { is_active: active });
    load();
  };

  const downloadLogs = async () => {
    setLogBusy(true);
    setError("");
    try {
      await api.download("/settings/logs/download", "app.log");
    } catch (e) {
      setError(String(e));
    } finally {
      setLogBusy(false);
    }
  };

  const clearLogs = async () => {
    if (
      !window.confirm(
        "Очистить app.log? Текущее содержимое будет удалено без возможности восстановления."
      )
    ) {
      return;
    }
    setLogBusy(true);
    setError("");
    try {
      await api.post("/settings/logs/clear");
      await loadLogInfo();
    } catch (e) {
      setError(String(e));
    } finally {
      setLogBusy(false);
    }
  };

  if (!settings) return <p>Загрузка…</p>;

  return (
    <>
      <h2>Настройки и парсеры</h2>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <p>
          API key: {settings.admin_configured ? "✓" : "✗"} | Anthropic:{" "}
          {settings.anthropic_configured ? "✓" : "✗"}
        </p>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
          Промпт: {settings.prompt_template_path}
        </p>
        <pre className="log-box" style={{ maxHeight: 160 }}>
          {settings.prompt_template_preview}
        </pre>
      </div>

      <div className="panel">
        <h3>Источники</h3>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
          Статистика за {statsDays} дн. · сортировка: проблемные сверху ·{" "}
          <span className="health-dot error" /> ошибки ·{" "}
          <span className="health-dot warn" /> внимание ·{" "}
          <span className="health-dot ok" /> норма
        </p>
        <div className="table-wrap">
          <table className="sources-table">
            <thead>
              <tr>
                <th>Статус</th>
                <th>Название</th>
                <th>Модуль</th>
                <th>Tier</th>
                <th>GEO</th>
                <th>Запусков</th>
                <th>Сохранено</th>
                <th>Ошибок</th>
                <th>Пустых</th>
                <th>Посл. запуск</th>
                <th>Активен</th>
              </tr>
            </thead>
            <tbody>
              {sortedSources.map((s) => {
                const st = s.stats;
                const health = st?.health ?? "idle";
                return (
                  <tr key={s.id} className={`source-row health-${health}`}>
                    <td title={healthTitle(s)}>
                      <span className={`health-dot ${health}`} />
                    </td>
                    <td>{s.name}</td>
                    <td>
                      <code>{s.scraper_module}</code>
                    </td>
                    <td>
                      <span className={`badge tier-${s.tier ?? "medium"}`}>
                        {tierLabel(s.tier)}
                      </span>
                    </td>
                    <td>{s.geo}</td>
                    <td>{st?.runs ?? 0}</td>
                    <td className={st && st.items_saved === 0 ? "muted-num" : ""}>
                      {st?.items_saved ?? 0}
                      {st && st.runs > 0 && (
                        <span className="sub-stat"> ({pct(st.save_rate)}/run)</span>
                      )}
                    </td>
                    <td className={st && st.errors > 0 ? "error-num" : ""}>
                      {st?.errors ?? 0}
                      {st && st.runs > 0 && st.errors > 0 && (
                        <span className="sub-stat"> ({pct(st.error_rate)})</span>
                      )}
                    </td>
                    <td>{st?.empty_runs ?? 0}</td>
                    <td className="dt-cell">{fmtDt(st?.last_run_at)}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={s.is_active}
                        onChange={(e) => toggleSource(s.id, e.target.checked)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3>Действия</h3>
        <div className="filters">
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            {settings.sources.map((s) => (
              <option key={s.id} value={s.scraper_module || ""}>
                {s.scraper_module}
              </option>
            ))}
          </select>
          <button onClick={() => runAction("/actions/scrape", { source, limit: 5 })}>
            Парсинг (limit 5)
          </button>
          <button
            className="secondary"
            onClick={() => runAction("/actions/health-check", { source })}
          >
            Health check
          </button>
          <button
            className="secondary"
            onClick={() => runAction("/actions/diagnose", { source })}
          >
            Diagnose
          </button>
        </div>
        <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
          Перед парсингом остановите scheduler на сервере, чтобы не было конфликта.
        </p>
      </div>

      <div className="panel">
        <h3>Логи приложения</h3>
        {appLog ? (
          <>
            <p style={{ marginTop: 0 }}>
              <code>{appLog.path}</code>
            </p>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
              Размер:{" "}
              <strong style={{ color: "var(--text)" }}>
                {appLog.exists ? appLog.size_human : "файл не найден"}
              </strong>
              {appLog.exists && appLog.size_bytes > 0 && (
                <span> ({appLog.size_bytes.toLocaleString("ru-RU")} байт)</span>
              )}
              {appLog.modified_at && (
                <span> · изменён {fmtDt(appLog.modified_at)}</span>
              )}
            </p>
            <div className="filters">
              <button disabled={logBusy || !appLog.exists} onClick={downloadLogs}>
                Скачать логи
              </button>
              <button
                className="secondary"
                disabled={logBusy || !appLog.exists || appLog.size_bytes === 0}
                onClick={clearLogs}
              >
                Очистить файл
              </button>
              <button className="secondary" disabled={logBusy} onClick={loadLogInfo}>
                Обновить
              </button>
            </div>
            <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              Путь из <code>config.ini</code> → [logging] file. Scheduler и API пишут в
              один файл; после очистки новые записи продолжат писаться.
            </p>
          </>
        ) : (
          <p style={{ color: "var(--muted)" }}>Загрузка информации о логах…</p>
        )}
      </div>

      <div className="panel">
        <h3>config.ini (только чтение)</h3>
        {settings.config_sections.map((sec) => (
          <div key={sec.name} style={{ marginBottom: "1rem" }}>
            <strong>[{sec.name}]</strong>
            <ul style={{ margin: "0.25rem 0", paddingLeft: "1.2rem" }}>
              {Object.entries(sec.values).map(([k, v]) => (
                <li key={k}>
                  <code>{k}</code> = {v}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <p style={{ color: "var(--muted)" }}>
          Редактирование .env и proxies.txt — на сервере вручную (безопаснее).
        </p>
      </div>

      {jobId && (
        <div className="panel">
          <h3>Лог {jobId}</h3>
          <div className="log-box">{log.join("\n")}</div>
        </div>
      )}
    </>
  );
}
