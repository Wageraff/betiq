import { useEffect, useState } from "react";
import { api, ApiQuotaStatus, CompetitionItem, CompetitionsList } from "../api";

const DATE_LOCALE = "en-US";

export default function CompetitionsPage() {
  const [data, setData] = useState<CompetitionsList | null>(null);
  const [sport, setSport] = useState("");
  const [trackedOnly, setTrackedOnly] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [syncingId, setSyncingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ page: "1", limit: "100" });
      if (sport) params.set("sport", sport);
      if (trackedOnly) params.set("is_tracked", "true");
      const res = await api.get<CompetitionsList>(`/competitions?${params}`);
      setData(res);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [sport, trackedOnly]);

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
      load();
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
      load();
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
        Включите трекинг лиги, чтобы odds/stats/lineups синхронизировались только для
        выбранных соревнований. Матчи без <code>competition_id</code> синхронизируются
        по умолчанию.
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
        <select value={sport} onChange={(e) => setSport(e.target.value)}>
          <option value="">Все виды спорта</option>
          <option value="football">football</option>
          <option value="tennis">tennis</option>
          <option value="basketball">basketball</option>
          <option value="hockey">hockey</option>
          <option value="mma">mma</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={trackedOnly}
            onChange={(e) => setTrackedOnly(e.target.checked)}
          />{" "}
          Только отслеживаемые
        </label>
        <button type="button" onClick={load} disabled={loading}>
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
              {data.items.map((c) => (
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
                      onChange={(e) => patch(c.id, { sync_odds: e.target.checked })}
                    />
                  </td>
                  <td>
                    <input
                      type="checkbox"
                      checked={c.sync_stats}
                      onChange={(e) => patch(c.id, { sync_stats: e.target.checked })}
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
                      value={c.odds_days_ahead ?? ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        if (!v) {
                          patch(c.id, { clear_odds_days_ahead: true });
                        } else {
                          patch(c.id, { odds_days_ahead: parseInt(v, 10) });
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
              ))}
            </tbody>
          </table>
          <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            Всего {data.total} лиг
          </p>
        </div>
      )}
    </>
  );
}
