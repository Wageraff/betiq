import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, MatchApiData, MatchDetail, PredictionDetail } from "../api";

const DATE_LOCALE = "en-US";

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
          Open source
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
        <p style={{ color: "var(--muted)" }}>Prediction text not saved</p>
      )}
      <footer style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: 8 }}>
        {p.scraped_at
          ? `Scraped: ${new Date(p.scraped_at).toLocaleString(DATE_LOCALE)}`
          : null}
        {" · "}
        {p.language}
      </footer>
    </article>
  );
}

function ApiDataSection({ api: ad, home, away }: { api: MatchApiData; home: string; away: string }) {
  return (
    <section className="panel">
      <h3>Sport API data</h3>
      <div className="match-meta" style={{ marginBottom: "1rem" }}>
        {ad.status && <span>Status: {ad.status}</span>}
        {ad.score && <span>Score: {ad.score}</span>}
        {ad.score_ht && <span>HT: {ad.score_ht}</span>}
        {ad.venue_name && <span>{ad.venue_name}{ad.venue_city ? `, ${ad.venue_city}` : ""}</span>}
        {ad.season && <span>Season {ad.season}</span>}
        {ad.round && <span>{ad.round}</span>}
      </div>

      {ad.external_ids.length > 0 && (
        <>
          <h4>External IDs</h4>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>ID</th>
                <th>Method</th>
              </tr>
            </thead>
            <tbody>
              {ad.external_ids.map((e) => (
                <tr key={e.provider}>
                  <td>{e.provider}</td>
                  <td><code>{e.external_id}</code></td>
                  <td>{e.link_method}{e.confidence != null ? ` (${e.confidence})` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {ad.match_stats.length > 0 && (
        <>
          <h4>Match statistics</h4>
          <table>
            <thead>
              <tr>
                <th>Side</th>
                <th>Shots</th>
                <th>Corners</th>
                <th>Poss %</th>
                <th>YC</th>
              </tr>
            </thead>
            <tbody>
              {ad.match_stats.map((s) => (
                <tr key={s.side}>
                  <td>{s.side}</td>
                  <td>{s.shots_on_goal ?? "—"}/{s.shots_total ?? "—"}</td>
                  <td>{s.corners ?? "—"}</td>
                  <td>{s.possession != null ? `${s.possession}%` : "—"}</td>
                  <td>{s.yellow_cards ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {(ad.team_form_home.length > 0 || ad.team_form_away.length > 0) && (
        <div className="form-grid">
          {ad.team_form_home.length > 0 && (
            <div>
              <h4>Form: {home}</h4>
              <table className="compact-table">
                <tbody>
                  {ad.team_form_home.map((f, i) => (
                    <tr key={i}>
                      <td>{f.match_date}</td>
                      <td>{f.is_home ? "H" : "A"} vs {f.opponent_name}</td>
                      <td><span className={`badge ${f.result === "W" ? "ok" : f.result === "L" ? "warn" : ""}`}>{f.result}</span> {f.goals_scored}-{f.goals_conceded}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {ad.team_form_away.length > 0 && (
            <div>
              <h4>Form: {away}</h4>
              <table className="compact-table">
                <tbody>
                  {ad.team_form_away.map((f, i) => (
                    <tr key={i}>
                      <td>{f.match_date}</td>
                      <td>{f.is_home ? "H" : "A"} vs {f.opponent_name}</td>
                      <td><span className={`badge ${f.result === "W" ? "ok" : f.result === "L" ? "warn" : ""}`}>{f.result}</span> {f.goals_scored}-{f.goals_conceded}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {ad.odds.length > 0 && (
        <>
          <h4>Odds ({ad.odds.length})</h4>
          <div style={{ overflowX: "auto", maxHeight: 280, overflowY: "auto" }}>
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Bookmaker</th>
                  <th>Market</th>
                  <th>Outcome</th>
                  <th>Odds</th>
                </tr>
              </thead>
              <tbody>
                {ad.odds.slice(0, 80).map((o, i) => (
                  <tr key={i}>
                    <td>{o.bookmaker}</td>
                    <td>{o.market}</td>
                    <td>{o.outcome}{o.point != null ? ` (${o.point})` : ""}</td>
                    <td>{o.odds}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {ad.odds_history.length > 0 && (
        <>
          <h4>Line movement</h4>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Market</th>
                <th>Outcome</th>
                <th>Was</th>
                <th>Now</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {ad.odds_history.map((h, i) => (
                <tr key={i} className={h.is_significant ? "row-significant" : ""}>
                  <td>{h.bookmaker} / {h.market}</td>
                  <td>{h.outcome}</td>
                  <td>{h.odds_prev ?? "—"}</td>
                  <td>{h.odds_curr}</td>
                  <td>{h.direction} {h.movement_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {ad.lineups.length > 0 && (
        <>
          <h4>Lineups</h4>
          <ul>
            {ad.lineups.map((ln, i) => (
              <li key={i}>
                {ln.side}: {ln.formation ?? "—"} — {ln.players_count} players
                {ln.coach_name ? ` (${ln.coach_name})` : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      {ad.external_ids.length === 0 &&
        ad.odds.length === 0 &&
        ad.match_stats.length === 0 && (
          <p style={{ color: "var(--muted)" }}>
            Нет данных API. Запустите <Link to="/api">link / sync</Link> в разделе Sport API.
          </p>
        )}
    </section>
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

  if (loading) return <p style={{ color: "var(--muted)" }}>Loading…</p>;
  if (error) return <p className="error">{error}</p>;
  if (!data) return null;

  const m = data.match;

  return (
    <>
      <p>
        <Link to="/">← Matches</Link>
      </p>
      <h2>
        {m.team_home} — {m.team_away}
        {m.score && <span style={{ color: "var(--muted)", fontWeight: 400 }}> {m.score}</span>}
      </h2>
      <div className="match-meta panel">
        <span>ID {m.id}</span>
        {m.sport && <span>{m.sport}</span>}
        {m.competition && <span>{m.competition}</span>}
        {m.status && <span>{m.status}</span>}
        {m.match_date && (
          <span>{new Date(m.match_date).toLocaleString(DATE_LOCALE)} UTC</span>
        )}
        <span>
          {m.predictions_count} prediction{m.predictions_count === 1 ? "" : "s"}
        </span>
        {m.has_api_football && <span className="badge ok">AF</span>}
        {m.has_odds_api && <span className="badge ok">Odds</span>}
        {m.odds_count ? <span>{m.odds_count} odds</span> : null}
        {m.match_key && (
          <code style={{ fontSize: "0.75rem" }}>{m.match_key}</code>
        )}
      </div>

      {data.api_data && (
        <ApiDataSection api={data.api_data} home={m.team_home} away={m.team_away} />
      )}

      {data.ai_summary && (
        <section className="panel">
          <h3>AI summary</h3>
          {data.ai_top_pick && (
            <p>
              <strong>Top pick:</strong> {data.ai_top_pick}
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
                ` · ${new Date(data.ai_generated_at).toLocaleString(DATE_LOCALE)}`}
            </p>
          )}
        </section>
      )}

      <h3>Predictions by source</h3>
      {data.predictions.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>No predictions</p>
      ) : (
        data.predictions.map((p) => <PredictionCard key={p.id} p={p} />)
      )}
    </>
  );
}
