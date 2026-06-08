import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, AiUsage } from "../api";

type AiRow = {
  id: number;
  match_title: string;
  sport: string | null;
  predictions_count: number;
  has_ai: boolean;
  ai_summary: string | null;
  ai_top_pick: string | null;
  ai_confidence: string | null;
};

function preview(text: string | null, max = 80): string {
  if (!text) return "—";
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return `${oneLine.slice(0, max)}…`;
}

function formatUsd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return `$${v.toFixed(2)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function QuotaBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const color = pct > 85 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="quota-bar">
      <div className="quota-fill" style={{ width: `${pct}%`, background: color }} />
      <span className="quota-label">
        {formatUsd(used)} / {formatUsd(limit)} ({pct}%)
      </span>
    </div>
  );
}

function DayUsageCard({
  title,
  day,
  showOfficial,
}: {
  title: string;
  day: AiUsage["today"];
  showOfficial: boolean;
}) {
  const spend = showOfficial && day.official_cost_usd != null
    ? day.official_cost_usd
    : day.estimated_cost_usd;
  return (
    <div className="panel ai-day-card">
      <h4>{title}</h4>
      <p style={{ color: "var(--muted)", fontSize: "0.85rem", margin: "0 0 0.5rem" }}>
        {day.date} ({showOfficial && day.official_cost_usd != null ? "Admin API" : "оценка"})
      </p>
      <table className="compact-table">
        <tbody>
          <tr>
            <td>Запросов</td>
            <td><strong>{day.requests}</strong></td>
          </tr>
          <tr>
            <td>Токены in / out</td>
            <td>
              {formatTokens(day.input_tokens)} / {formatTokens(day.output_tokens)}
            </td>
          </tr>
          <tr>
            <td>Расход</td>
            <td>
              <strong>{formatUsd(spend)}</strong>
              {showOfficial && day.official_cost_usd != null && (
                <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: "0.85rem" }}>
                  (официально)
                </span>
              )}
              {(!showOfficial || day.official_cost_usd == null) && day.estimated_cost_usd > 0 && (
                <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: "0.85rem" }}>
                  (оценка)
                </span>
              )}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default function AiPage() {
  const [rows, setRows] = useState<AiRow[]>([]);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editSummary, setEditSummary] = useState("");
  const [editTopPick, setEditTopPick] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const [data, usageData] = await Promise.all([
        api.get<AiRow[]>("/ai/matches?min_predictions=2"),
        api.get<AiUsage>("/ai/usage"),
      ]);
      setRows(data);
      setUsage(usageData);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const runAi = async (matchId: number) => {
    setError("");
    setLog([]);
    try {
      const res = await api.post<{ job_id: string }>("/actions/ai-summary", {
        match_id: matchId,
        force: true,
      });
      setJobId(res.job_id);
      pollLog(res.job_id);
    } catch (e) {
      setError(String(e));
    }
  };

  const pollLog = async (id: string) => {
    const tick = async () => {
      try {
        const data = await api.get<{ lines: string[] }>(`/actions/jobs/${id}/log`);
        setLog(data.lines);
        const done = data.lines.some((l) => l.startsWith("[exit "));
        if (!done) setTimeout(tick, 1500);
        else load();
      } catch {
        /* ignore */
      }
    };
    tick();
  };

  const startEdit = (row: AiRow) => {
    setEditingId(row.id);
    setEditSummary(row.ai_summary || "");
    setEditTopPick(row.ai_top_pick || "");
    setError("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditSummary("");
    setEditTopPick("");
  };

  const saveEdit = async (matchId: number) => {
    setSaving(true);
    setError("");
    try {
      const updated = await api.patch<AiRow>(`/ai/matches/${matchId}`, {
        ai_summary: editSummary,
        ai_top_pick: editTopPick,
      });
      setRows((prev) => prev.map((r) => (r.id === matchId ? { ...r, ...updated } : r)));
      cancelEdit();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const todaySpend =
    usage?.admin_api_configured && usage.today.official_cost_usd != null
      ? usage.today.official_cost_usd
      : usage?.today.estimated_cost_usd ?? 0;

  return (
    <>
      <h2>AI summaries</h2>
      <p style={{ color: "var(--muted)" }}>
        Матчи с 2+ прогнозами. Промпт — в{" "}
        <Link to="/settings">Настройках</Link>.
      </p>

      {usage && (
        <section className="panel">
          <h3>Claude API — расход</h3>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Модель: <code>{usage.model}</code>
            {" · "}
            API key: {usage.configured ? "✓" : "✗"}
            {" · "}
            Admin API: {usage.admin_api_configured ? "✓" : "✗"}
            {" · "}
            часовой пояс: {usage.timezone}
          </p>
          {usage.admin_error && (
            <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{usage.admin_error}</p>
          )}
          <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>{usage.pricing_note}</p>

          {usage.daily_budget_usd != null && usage.daily_budget_usd > 0 && (
            <div style={{ margin: "1rem 0" }}>
              <p style={{ margin: "0 0 0.35rem" }}>
                <strong>Бюджет на сегодня</strong> (из config.ini)
              </p>
              <QuotaBar used={todaySpend} limit={usage.daily_budget_usd} />
              {usage.remaining_budget_usd != null && (
                <p style={{ fontSize: "0.85rem", marginTop: "0.35rem" }}>
                  Осталось сегодня:{" "}
                  <strong
                    style={{
                      color:
                        usage.remaining_budget_usd < 0 ? "var(--warn)" : "var(--ok)",
                    }}
                  >
                    {formatUsd(usage.remaining_budget_usd)}
                  </strong>
                </p>
              )}
            </div>
          )}

          {usage.max_summaries_per_day != null && usage.max_summaries_per_day > 0 && (
            <p style={{ fontSize: "0.85rem" }}>
              Лимит сводок/день (config): {usage.today.requests} /{" "}
              {usage.max_summaries_per_day}
            </p>
          )}

          <div className="api-grid" style={{ marginTop: "1rem" }}>
            <DayUsageCard
              title="Сегодня"
              day={usage.today}
              showOfficial={usage.admin_api_configured}
            />
            <DayUsageCard
              title="Вчера"
              day={usage.yesterday}
              showOfficial={usage.admin_api_configured}
            />
          </div>
          <p style={{ color: "var(--muted)", fontSize: "0.75rem", marginTop: "0.75rem" }}>
            Обновлено: {new Date(usage.checked_at).toLocaleString("en-US")}
            {usage.admin_api_configured
              ? " · расход USD из Anthropic Admin API (лаг ~1–2 ч)"
              : " · USD оценивается по токенам из ai_usage_log"}
          </p>
        </section>
      )}

      {error && <p className="error">{error}</p>}
      <div className="panel table-wrap">
        <table className="ai-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Матч</th>
              <th>Ставка AI</th>
              <th>Сводка</th>
              <th>AI</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td>{r.id}</td>
                  <td>
                    <Link to={`/matches/${r.id}`}>{r.match_title}</Link>
                    {r.sport && (
                      <span className="sub-stat" style={{ display: "block" }}>
                        {r.sport}
                      </span>
                    )}
                  </td>
                  <td className="ai-pick-cell">
                    {r.ai_top_pick ? (
                      <strong>{r.ai_top_pick}</strong>
                    ) : (
                      <span style={{ color: "var(--muted)" }}>—</span>
                    )}
                  </td>
                  <td className="ai-preview-cell" title={r.ai_summary || undefined}>
                    {r.has_ai ? preview(r.ai_summary) : "—"}
                  </td>
                  <td>
                    {r.has_ai ? (
                      <span className="badge ok">{r.ai_confidence || "ok"}</span>
                    ) : (
                      <span className="badge">нет</span>
                    )}
                  </td>
                  <td className="ai-actions-cell">
                    <button onClick={() => runAi(r.id)}>Generate</button>
                    {r.has_ai && (
                      <button
                        className="secondary"
                        style={{ marginLeft: "0.35rem" }}
                        onClick={() =>
                          editingId === r.id ? cancelEdit() : startEdit(r)
                        }
                      >
                        {editingId === r.id ? "Закрыть" : "Править"}
                      </button>
                    )}
                  </td>
                </tr>
                {editingId === r.id && (
                  <tr className="ai-edit-row">
                    <td colSpan={6}>
                      <div className="ai-edit-form">
                        <label>
                          Ставка AI
                          <input
                            type="text"
                            value={editTopPick}
                            onChange={(e) => setEditTopPick(e.target.value)}
                            placeholder="1 @ 1.85"
                            style={{ width: "100%", marginTop: "0.35rem" }}
                          />
                        </label>
                        <label>
                          Текст сводки
                          <textarea
                            value={editSummary}
                            onChange={(e) => setEditSummary(e.target.value)}
                            rows={8}
                            style={{ width: "100%", marginTop: "0.35rem" }}
                          />
                        </label>
                        <div className="ai-edit-actions">
                          <button disabled={saving} onClick={() => saveEdit(r.id)}>
                            {saving ? "Сохранение…" : "Сохранить"}
                          </button>
                          <button className="secondary" onClick={cancelEdit}>
                            Отмена
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      {jobId && (
        <div className="panel">
          <h3>Job log {jobId}</h3>
          <div className="log-box">{log.join("\n")}</div>
        </div>
      )}
    </>
  );
}
