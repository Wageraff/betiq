import { useEffect, useState } from "react";
import { api, Settings } from "../api";

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [source, setSource] = useState("beturi");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      const data = await api.get<Settings>("/settings");
      setSettings(data);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

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
        <pre
          className="log-box"
          style={{ maxHeight: 160 }}
        >
          {settings.prompt_template_preview}
        </pre>
      </div>

      <div className="panel">
        <h3>Источники</h3>
        <table>
          <thead>
            <tr>
              <th>Название</th>
              <th>Модуль</th>
              <th>GEO</th>
              <th>Активен</th>
            </tr>
          </thead>
          <tbody>
            {settings.sources.map((s) => (
              <tr key={s.id}>
                <td>{s.name}</td>
                <td>{s.scraper_module}</td>
                <td>{s.geo}</td>
                <td>
                  <input
                    type="checkbox"
                    checked={s.is_active}
                    onChange={(e) => toggleSource(s.id, e.target.checked)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
