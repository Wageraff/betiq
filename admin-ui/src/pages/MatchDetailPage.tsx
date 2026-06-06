import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  MatchApiData,
  MatchApiPrediction,
  MatchDetail,
  MatchOddsList,
  PredictionDetail,
} from "../api";

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

type ProviderFilter = "all" | "api_football" | "the_odds_api";

function OddsPanel({ matchId, ad }: { matchId: number; ad: MatchApiData }) {
  const markets = ad.odds_markets ?? [];
  const initialMarket = ad.odds_market || markets[0]?.market || "";
  const [market, setMarket] = useState(initialMarket);
  const [rows, setRows] = useState(ad.odds ?? []);
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<ProviderFilter>("all");

  useEffect(() => {
    if (!market) {
      setRows([]);
      return;
    }
    setLoading(true);
    api
      .get<MatchOddsList>(
        `/matches/${matchId}/odds?market=${encodeURIComponent(market)}`
      )
      .then((r) => setRows(r.items))
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [matchId, market]);

  const activeMarket = markets.find((m) => m.market === market);
  const marketTotal = activeMarket?.count ?? 0;
  const filtered =
    provider === "all"
      ? rows
      : rows.filter((o) => o.provider === provider);

  if (ad.odds_total === 0 && markets.length === 0) {
    return (
      <p style={{ color: "var(--muted)" }}>
        Коэффициентов в БД нет. Запустите{" "}
        <Link to="/api">Fetch odds</Link> в разделе Sport API.
      </p>
    );
  }

  return (
    <div className="odds-panel">
      <div className="odds-panel-head">
        <h4 style={{ margin: 0 }}>
          Odds — {ad.odds_total.toLocaleString()} в БД
          {market && marketTotal > 0 && (
            <span style={{ color: "var(--muted)", fontWeight: 400 }}>
              {" "}
              · рынок «{market}»: {marketTotal.toLocaleString()}
            </span>
          )}
        </h4>
        {ad.odds_fetched_at && (
          <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
            обновлено{" "}
            {new Date(ad.odds_fetched_at).toLocaleString(DATE_LOCALE)}
          </span>
        )}
      </div>

      {markets.length > 0 && (
        <div className="market-pills">
          {markets.map((m) => (
            <button
              key={m.market}
              type="button"
              className={`market-pill${market === m.market ? " active" : ""}`}
              onClick={() => setMarket(m.market)}
              title={`${m.provider} · ${m.count} строк`}
            >
              {m.market}
              <span className="market-pill-count">{m.count}</span>
              {m.provider === "api_football" && (
                <span className="badge ok" style={{ marginLeft: 4 }}>
                  AF
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <div className="provider-tabs">
        {(["all", "the_odds_api", "api_football"] as const).map((p) => (
          <button
            key={p}
            type="button"
            className={provider === p ? "active" : ""}
            onClick={() => setProvider(p)}
          >
            {p === "all"
              ? "Все"
              : p === "api_football"
                ? "API-Football"
                : "The Odds API"}
          </button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: "var(--muted)" }}>Загрузка коэффициентов…</p>
      ) : filtered.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>
          Нет строк для выбранного рынка и фильтра.
        </p>
      ) : (
        <>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem", margin: "0.5rem 0" }}>
            Показано {filtered.length.toLocaleString()}
            {marketTotal > filtered.length
              ? ` из ${marketTotal.toLocaleString()} по рынку`
              : ""}
            {rows.length >= 500 ? " (лимит 500 на запрос)" : ""}
          </p>
          <div className="odds-table-wrap">
            <table className="compact-table">
              <thead>
                <tr>
                  <th>Bookmaker</th>
                  <th>Outcome</th>
                  <th>Odds</th>
                  <th>Live</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o, i) => (
                  <tr key={i}>
                    <td>
                      {o.bookmaker}
                      {o.provider === "api_football" && (
                        <span className="badge ok" style={{ marginLeft: 4 }}>
                          AF
                        </span>
                      )}
                    </td>
                    <td>
                      {o.outcome}
                      {o.point != null ? ` (${o.point})` : ""}
                    </td>
                    <td>{o.odds}</td>
                    <td>{o.is_live ? "yes" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function ApiDataSection({
  matchId,
  api: ad,
  home,
  away,
}: {
  matchId: number;
  api: MatchApiData;
  home: string;
  away: string;
}) {
  const hasAfLink = ad.external_ids.some((e) => e.provider === "api_football");

  return (
    <section className="panel">
      <h3>Sport API data</h3>

      <OddsPanel matchId={matchId} ad={ad} />

      {hasAfLink && (ad.odds_total ?? 0) > 0 && (
        <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
          API-Football и The Odds API могут дублировать рынки — переключайте рынки
          кнопками выше.
        </p>
      )}

      <div className="match-meta" style={{ margin: "1rem 0" }}>
        {ad.status && <span>Status: {ad.status}</span>}
        {ad.score && <span>Score: {ad.score}</span>}
        {ad.score_ht && <span>HT: {ad.score_ht}</span>}
        {ad.venue_name && (
          <span>
            {ad.venue_name}
            {ad.venue_city ? `, ${ad.venue_city}` : ""}
          </span>
        )}
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
                  <td>
                    <code>{e.external_id}</code>
                  </td>
                  <td>
                    {e.link_method}
                    {e.confidence != null ? ` (${e.confidence})` : ""}
                  </td>
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
                  <td>
                    {s.shots_on_goal ?? "—"}/{s.shots_total ?? "—"}
                  </td>
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
                      <td>
                        {f.is_home ? "H" : "A"} vs {f.opponent_name}
                      </td>
                      <td>
                        <span
                          className={`badge ${f.result === "W" ? "ok" : f.result === "L" ? "warn" : ""}`}
                        >
                          {f.result}
                        </span>{" "}
                        {f.goals_scored}-{f.goals_conceded}
                      </td>
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
                      <td>
                        {f.is_home ? "H" : "A"} vs {f.opponent_name}
                      </td>
                      <td>
                        <span
                          className={`badge ${f.result === "W" ? "ok" : f.result === "L" ? "warn" : ""}`}
                        >
                          {f.result}
                        </span>{" "}
                        {f.goals_scored}-{f.goals_conceded}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
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
                  <td>
                    {h.bookmaker} / {h.market}
                  </td>
                  <td>{h.outcome}</td>
                  <td>{h.odds_prev ?? "—"}</td>
                  <td>{h.odds_curr}</td>
                  <td>
                    {h.direction} {h.movement_pct}%
                  </td>
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
        (ad.odds_total ?? 0) === 0 &&
        ad.match_stats.length === 0 && (
          <p style={{ color: "var(--muted)" }}>
            Нет данных API. Запустите{" "}
            <Link to="/api">link / sync</Link> в разделе Sport API.
          </p>
        )}
    </section>
  );
}

function ApiPredictionPanel({
  pred,
  fetchedAt,
  hasAfLink,
  home,
  away,
}: {
  pred?: MatchApiPrediction | null;
  fetchedAt?: string | null;
  hasAfLink: boolean;
  home: string;
  away: string;
}) {
  if (!pred && !fetchedAt && !hasAfLink) return null;

  return (
    <section className="panel prediction-api-panel">
      <h3>API-Football prediction</h3>
      <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
        Встроенный прогноз API-Football (/predictions) — отдельно от нашей AI-сводки.
      </p>
      {!pred ? (
        <p style={{ color: "var(--muted)" }}>
          {fetchedAt
            ? "API ответил, но прогноз пустой."
            : hasAfLink
              ? "Прогноз ещё не загружен — дождитесь job_fetch_api_predictions или Sport API → sync."
              : "Нет привязки API-Football (fixture_id)."}
        </p>
      ) : (
        <>
          {(pred.winner_team || pred.winner_comment) && (
            <p>
              <strong>Winner:</strong> {pred.winner_team ?? "—"}
              {pred.winner_comment ? ` — ${pred.winner_comment}` : ""}
            </p>
          )}
          {(pred.percent_home != null ||
            pred.percent_draw != null ||
            pred.percent_away != null) && (
            <div className="api-pred-percents">
              <span title={home}>
                {home}: <strong>{pred.percent_home ?? "—"}%</strong>
              </span>
              <span>Draw: <strong>{pred.percent_draw ?? "—"}%</strong></span>
              <span title={away}>
                {away}: <strong>{pred.percent_away ?? "—"}%</strong>
              </span>
            </div>
          )}
          {(pred.goals_home || pred.goals_away) && (
            <p>
              <strong>Goals:</strong> {pred.goals_home ?? "—"} — {pred.goals_away ?? "—"}
            </p>
          )}
          {(pred.form_home || pred.form_away) && (
            <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
              Form: {home} {pred.form_home ?? "—"} · {away} {pred.form_away ?? "—"}
            </p>
          )}
          {pred.advice && (
            <pre className="prediction-text" style={{ whiteSpace: "pre-wrap" }}>
              {pred.advice}
            </pre>
          )}
          {pred.fetched_at && (
            <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              API-Football · {new Date(pred.fetched_at).toLocaleString(DATE_LOCALE)}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function AiSummaryPanel({ data }: { data: MatchDetail }) {
  if (!data.ai_summary) return null;
  return (
    <section className="panel prediction-ai-panel">
      <h3>AI summary</h3>
      <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 0 }}>
        Наша сводка по прогнозам источников (Claude).
      </p>
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
  const showApi =
    data.api_data ||
    m.odds_count > 0 ||
    m.has_api_football ||
    m.has_odds_api;

  return (
    <>
      <p>
        <Link to="/">← Matches</Link>
      </p>
      <h2>
        {m.team_home} — {m.team_away}
        {m.score && (
          <span style={{ color: "var(--muted)", fontWeight: 400 }}>
            {" "}
            {m.score}
          </span>
        )}
      </h2>
      <div className="match-meta panel">
        <span>ID {m.id}</span>
        {m.sport && <span>{m.sport}</span>}
        {m.competition && <span>{m.competition}</span>}
        {m.round && <span>{m.round}</span>}
        {(m.venue_name || m.venue_city) && (
          <span>
            {[m.venue_name, m.venue_city].filter(Boolean).join(", ")}
          </span>
        )}
        {m.status && <span>{m.status}</span>}
        {m.match_date && (
          <span>{new Date(m.match_date).toLocaleString(DATE_LOCALE)} UTC</span>
        )}
        <span>
          {m.predictions_count} prediction{m.predictions_count === 1 ? "" : "s"}
        </span>
        {m.has_api_football && <span className="badge ok">AF</span>}
        {m.has_odds_api && <span className="badge ok">Odds</span>}
        {m.odds_count ? (
          <span>{m.odds_count.toLocaleString()} odds</span>
        ) : null}
        {m.match_key && (
          <code style={{ fontSize: "0.75rem" }}>{m.match_key}</code>
        )}
      </div>

      {showApi && data.api_data && (
        <ApiDataSection
          matchId={m.id}
          api={data.api_data}
          home={m.team_home}
          away={m.team_away}
        />
      )}

      {(data.ai_summary ||
        data.api_prediction ||
        data.api_prediction_fetched_at ||
        m.has_api_football) && (
        <div className="predictions-compare-row">
          <AiSummaryPanel data={data} />
          <ApiPredictionPanel
            pred={data.api_prediction}
            fetchedAt={data.api_prediction_fetched_at}
            hasAfLink={m.has_api_football}
            home={m.team_home}
            away={m.team_away}
          />
        </div>
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
