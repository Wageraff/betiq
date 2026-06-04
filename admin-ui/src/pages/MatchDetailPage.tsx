import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, MatchDetail, PredictionDetail } from "../api";

function PredictionCard({ p }: { p: PredictionDetail }) {
  const isHtml = Boolean(p.full_text && /<[a-z][\s\S]*>/i.test(p.full_text));

  return (
    <article className="panel prediction-card">
      <header className="prediction-head">
        <div>
          <strong>{p.source}</strong>
          {p.author && (
            <span style={{ color: "var(--muted)", marginLeft: 8 }}>{p.author}</span>
          )}
        </div>
        <a href={p.source_url} target="_blank" rel="noreferrer">
          Открыть на сайте
        </a>
      </header>
      {p.title && <h4 style={{ margin: "0.5rem 0" }}>{p.title}</h4>}
      {p.bets.length > 0 && (
        <ul className="bet-list">
          {p.bets.map((b, i) => (
            <li key={i}>
              {b.bet_pick}
              {b.odds != null && (
                <span style={{ color: "var(--muted)" }}> @ {b.odds}</span>
              )}
              {b.is_main && <span className="badge ok">main</span>}
            </li>
          ))}
        </ul>
      )}
      {p.full_text ? (
        isHtml ? (
          <div
            className="prediction-html"
            dangerouslySetInnerHTML={{ __html: p.full_text }}
          />
        ) : (
          <pre className="prediction-text">{p.full_text}</pre>
        )
      ) : (
        <p style={{ color: "var(--muted)" }}>Текст прогноза не сохранён</p>
      )}
      <footer style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: 8 }}>
        {p.scraped_at
          ? `Скрап: ${new Date(p.scraped_at).toLocaleString("ru-RU")}`
          : null}
        {" · "}
        {p.language}
      </footer>
    </article>
  );
}

export default function MatchDetailPage() {
  const { id } = useParams();
  const [data, setData] = useState<MatchDetail | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError("");
    api
      .get<MatchDetail>(`/matches/${id}`)
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <p style={{ color: "var(--muted)" }}>Загрузка…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!data) return null;

  const m = data.match;

  return (
    <>
      <p>
        <Link to="/">← Матчи</Link>
      </p>
      <h2>
        {m.team_home} — {m.team_away}
      </h2>
      <div className="match-meta panel">
        <span>ID {m.id}</span>
        {m.sport && <span>{m.sport}</span>}
        {m.competition && <span>{m.competition}</span>}
        {m.match_date && (
          <span>{new Date(m.match_date).toLocaleString("ru-RU")} UTC</span>
        )}
        <span>{m.predictions_count} прогноз(ов)</span>
        {m.match_key && (
          <code style={{ fontSize: "0.75rem" }}>{m.match_key}</code>
        )}
      </div>

      {data.ai_summary && (
        <section className="panel">
          <h3>AI-сводка</h3>
          {data.ai_top_pick && (
            <p>
              <strong>Топ:</strong> {data.ai_top_pick}
              {data.ai_confidence && ` (${data.ai_confidence})`}
            </p>
          )}
          <pre className="prediction-text" style={{ whiteSpace: "pre-wrap" }}>
            {data.ai_summary}
          </pre>
          {data.ai_model && (
            <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              {data.ai_model}
              {data.ai_generated_at &&
                ` · ${new Date(data.ai_generated_at).toLocaleString("ru-RU")}`}
            </p>
          )}
        </section>
      )}

      <h3>Прогнозы по источникам</h3>
      {data.predictions.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>Нет прогнозов</p>
      ) : (
        data.predictions.map((p) => <PredictionCard key={p.id} p={p} />)
      )}
    </>
  );
}
