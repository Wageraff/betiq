import { useEffect, useState } from "react";
import { api, CompetitionItem, CompetitionsList } from "../api";

const DATE_LOCALE = "en-US";
const PAGE_SIZE = 30;

export default function CompetitionsPage() {
  const [data, setData] = useState<CompetitionsList | null>(null);
  const [sport, setSport] = useState("football");
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [trackedOnly, setTrackedOnly] = useState(false);
  const [withMatches, setWithMatches] = useState(true);
  const [order, setOrder] = useState<"matches" | "name">("matches");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncingId, setSyncingId] = useState<number | null>(null);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  const load = async (targetPage = page) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        page: String(targetPage),
        limit: String(PAGE_SIZE),
        order,
      });
      if (sport) params.set("sport", sport);
      if (qApplied) params.set("q", qApplied);
      if (trackedOnly) params.set("is_tracked", "true");
      if (withMatches) params.set("with_matches", "true");
      const res = await api.get<CompetitionsList>(`/competitions?${params}`);
      setData(res);
      setPage(targetPage);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(1);
  }, [sport, trackedOnly, withMatches, order, qApplied]);

  const applySearch = () => {
    setQApplied(q.trim());
    setPage(1);
  };

  const patch = async (
    id: number,
    patchBody: Partial<CompetitionItem> & { clear_odds_days_ahead?: boolean }
  ) => {
    setMsg("");
    try {
      await api.patch<CompetitionItem>(`/competitions/${id}`, {
        is_tracked: patchBody.is_tracked,
        sync_odds: patchBody.sync_odds,
        sync_stats: patchBody.sync_stats,
        sync_lineups: patchBody.sync_lineups,
        odds_days_ahead: patchBody.odds_days_ahead,
        clear_odds_days_ahead: patchBody.clear_odds_days_ahead,
      });
      setMsg(`Сохранено: ${id}`);
      load(page);
    } catch (e) {
      setError(String(e));
    }
  };

  const syncNow = async (id: number) => {
    setSyncingId(id);
    setMsg("");
    try {
      const res = await api.post<{
        the_odds_api_lines: number;
        api_football_lines: number;
        matches: number;
      }>(`/competitions/${id}/sync-now`);
      setMsg(
        `Синк #${id}: ${res.matches} матчей, TOA ${res.the_odds_api_lines}, AF ${res.api_football_lines} строк`
      );
      load(page);
    } catch (e) {
      setError(String(e));
    } finally {
      setSyncingId(null);
    }
  };

  const quota = data?.quota;

  return (
    <>
      <h2>Лиги и синхронизация</h2>
      <p style={{ color: "var(--muted)" }}>
        Поиск по названию лиги, стране или тексту турнира в матчах (World Cup, ЧМ,
        Russia…). «С матчами в БД» — лиги с предстоящими матчами (по{" "}
        <code>competition_id</code> или полю <code>competition</code>).
      </p>

      {quota && (
        <div className="panel quota-cards">
          <div>
            <strong>The Odds API</strong>
            <p style={{ margin: "0.25rem 0" }}>
              {quota.the_odds_api_remaining ?? "—"} осталось
              {quota.the_odds_api_used != null && ` · ${quota.the_odds_api_used} used`}
            </p>
          </div>
          <div>
            <strong>API-Football</strong>
            <p style={{ margin: "0.25rem 0" }}>
              {quota.api_football_remaining ?? "—"} осталось
              {quota.api_football_limit != null && ` / ${quota.api_football_limit}`}
            </p>
          </div>
          <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
            {quota.checked_at &&
              new Date(quota.checked_at).toLocaleString(DATE_LOCALE)}
          </div>
        </div>
      )}

      <div className="filters panel">
        <input
          placeholder="Поиск: World Cup, Russia, Premier…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && applySearch()}
          style={{ minWidth: 220, flex: "1 1 220px" }}
        />
        <button type="button" onClick={applySearch} disabled={loading}>
          Найти
        </button>
        {qApplied && (
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setQ("");
              setQApplied("");
            }}
          >
            Сбросить поиск
          </button>
        )}
        <select value={sport} onChange={(e) => setSport(e.target.value)}>
          <option value="">Все виды спорта</option>
          <option value="football">football</option>
          <option value="tennis">tennis</option>
          <option value="basketball">basketball</option>
          <option value="hockey">hockey</option>
          <option value="mma">mma</option>
        </select>
        <select
          value={order}
          onChange={(e) => setOrder(e.target.value as "matches" | "name")}
        >
          <option value="matches">Сортировка: по матчам</option>
          <option value="name">Сортировка: по названию</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={withMatches}
            onChange={(e) => setWithMatches(e.target.checked)}
          />{" "}
          С матчами в БД
        </label>
        <label>
          <input
            type="checkbox"
            checked={trackedOnly}
            onChange={(e) => setTrackedOnly(e.target.checked)}
          />{" "}
          Только отслеживаемые
        </label>
        <button type="button" onClick={() => load(page)} disabled={loading}>
          Обновить
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}
      {loading && !data && <p style={{ color: "var(--muted)" }}>Loading…</p>}

      {data && (
        <div className="panel" style={{ overflowX: "auto" }}>
          <table className="compact-table">
            <thead>
              <tr>
                <th>Лига</th>
                <th>Sport</th>
                <th>Матчей</th>
                <th>Track</th>
                <th>Odds</th>
                <th>Stats</th>
                <th>Lineups</th>
                <th>Days</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ color: "var(--muted)" }}>
                    Ничего не найдено. Попробуйте другой запрос или снимите фильтр
                    «С матчами в БД».
                  </td>
                </tr>
              ) : (
                data.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      {c.country && (
                        <span style={{ color: "var(--muted)", marginLeft: 6 }}>
                          {c.country}
                        </span>
                      )}
                    </td>
                    <td>{c.sport}</td>
                    <td>{c.matches_upcoming}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={c.is_tracked}
                        onChange={(e) =>
                          patch(c.id, {
                            is_tracked: e.target.checked,
                            sync_odds: e.target.checked ? true : c.sync_odds,
                          })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={c.sync_odds}
                        onChange={(e) =>
                          patch(c.id, { sync_odds: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={c.sync_stats}
                        onChange={(e) =>
                          patch(c.id, { sync_stats: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={c.sync_lineups}
                        onChange={(e) =>
                          patch(c.id, { sync_lineups: e.target.checked })
                        }
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min={1}
                        max={30}
                        style={{ width: 52 }}
                        placeholder="7"
                        defaultValue={c.odds_days_ahead ?? ""}
                        onBlur={(e) => {
                          const v = e.target.value;
                          if (!v) {
                            patch(c.id, { clear_odds_days_ahead: true });
                          } else {
                            patch(c.id, {
                              odds_days_ahead: parseInt(v, 10),
                            });
                          }
                        }}
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        disabled={syncingId === c.id}
                        onClick={() => syncNow(c.id)}
                      >
                        {syncingId === c.id ? "…" : "Синк"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>

          <div className="pagination-bar">
            <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
              {data.total} лиг · стр. {page} / {totalPages}
              {loading ? " · загрузка…" : ""}
            </span>
            <div className="pagination-controls">
              <button
                type="button"
                className="secondary"
                disabled={page <= 1 || loading}
                onClick={() => load(page - 1)}
              >
                ← Назад
              </button>
              <button
                type="button"
                className="secondary"
                disabled={page >= totalPages || loading}
                onClick={() => load(page + 1)}
              >
                Вперёд →
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
