import { useEffect, useState } from "react";
import { api } from "../api";

type AiRow = {
  id: number;
  match_title: string;
  sport: string | null;
  predictions_count: number;
  has_ai: boolean;
  ai_confidence: string | null;
};

export default function AiPage() {
  const [rows, setRows] = useState<AiRow[]>([]);
  const [jobId, setJobId] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");

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

  return (
    <>
      <h2>AI-сводки</h2>
      <p style={{ color: "var(--muted)" }}>
        Матчи с 2+ прогнозами. Шаблон промпта — в разделе «Настройки».
      </p>
      {error && <p className="error">{error}</p>}
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Матч</th>
              <th>Прогнозов</th>
              <th>AI</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.match_title}</td>
                <td>{r.predictions_count}</td>
                <td>
                  {r.has_ai ? (
                    <span className="badge ok">{r.ai_confidence || "ok"}</span>
                  ) : (
                    <span className="badge">нет</span>
                  )}
                </td>
                <td>
                  <button onClick={() => runAi(r.id)}>Сгенерировать</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {jobId && (
        <div className="panel">
          <h3>Лог задачи {jobId}</h3>
          <div className="log-box">{log.join("\n")}</div>
        </div>
      )}
    </>
  );
}
