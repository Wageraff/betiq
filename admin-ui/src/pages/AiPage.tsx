import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

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

export default function AiPage() {
  const [rows, setRows] = useState<AiRow[]>([]);
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editSummary, setEditSummary] = useState("");
  const [editTopPick, setEditTopPick] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const data = await api.get<AiRow[]>("/ai/matches?min_predictions=2");
      setRows(data);
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

  return (
    <>
      <h2>AI summaries</h2>
      <p style={{ color: "var(--muted)" }}>
        Матчи с 2+ прогнозами. Промпт — в Настройках.
      </p>
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
