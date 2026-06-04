import { useEffect, useState } from "react";
import {
  api,
  Team,
  TeamDuplicateGroup,
  TeamDuplicatesOut,
} from "../api";

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [dupGroups, setDupGroups] = useState<TeamDuplicateGroup[]>([]);
  const [keepers, setKeepers] = useState<Record<string, number>>({});
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Team | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [sport, setSport] = useState("");
  const [aliases, setAliases] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [merging, setMerging] = useState(false);

  const load = async () => {
    setError("");
    const params = new URLSearchParams({ limit: "100" });
    if (q) params.set("q", q);
    try {
      const [teamList, dups] = await Promise.all([
        api.get<Team[]>(`/teams?${params}`),
        api.get<TeamDuplicatesOut>("/teams/duplicates"),
      ]);
      setTeams(teamList);
      setDupGroups(dups.groups);
      const next: Record<string, number> = {};
      for (const g of dups.groups) {
        const preferred =
          g.teams.find((t) => t.normalized_key === g.canonical_key) || g.teams[0];
        next[g.canonical_key] = preferred.id;
      }
      setKeepers(next);
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    load();
  }, []);

  const select = (t: Team) => {
    setSelected(t);
    setDisplayName(t.display_name);
    setSport(t.sport || "");
    setAliases(t.aliases || "");
    setMsg("");
  };

  const save = async () => {
    if (!selected) return;
    try {
      const updated = await api.patch<Team>(`/teams/${selected.id}`, {
        display_name: displayName,
        sport: sport || null,
        aliases: aliases || null,
      });
      setMsg("Сохранено");
      setSelected(updated);
      load();
    } catch (e) {
      setError(String(e));
    }
  };

  const onLogo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!selected || !e.target.files?.[0]) return;
    try {
      const updated = await api.uploadLogo(selected.id, e.target.files[0]);
      setSelected(updated);
      setMsg("Логотип загружен");
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  const mergeGroup = async (group: TeamDuplicateGroup) => {
    const keeperId = keepers[group.canonical_key];
    const duplicateIds = group.teams
      .map((t) => t.id)
      .filter((id) => id !== keeperId);
    if (!keeperId || duplicateIds.length === 0) return;
    setMerging(true);
    setError("");
    try {
      const res = await api.post<{ message: string }>("/teams/merge", {
        keeper_id: keeperId,
        duplicate_ids: duplicateIds,
      });
      setMsg(res.message);
      if (selected && duplicateIds.includes(selected.id)) {
        setSelected(null);
      }
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setMerging(false);
    }
  };

  const mergeAllAuto = async () => {
    setMerging(true);
    setError("");
    try {
      const res = await api.post<{ message: string }>("/teams/merge-auto", {});
      setMsg(res.message);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setMerging(false);
    }
  };

  return (
    <>
      <h2>Справочник команд / соперников</h2>
      <p style={{ color: "var(--muted)" }}>
        Справочник на английском (ключи как в match_key). Варианты с сайтов — в алиасах.
      </p>

      {dupGroups.length > 0 && (
        <section className="panel dup-groups">
          <div className="dup-groups-head">
            <h3>Дубликаты ({dupGroups.length})</h3>
            <button
              className="secondary"
              disabled={merging}
              onClick={mergeAllAuto}
            >
              Объединить все автоматически
            </button>
          </div>
          {dupGroups.map((g) => (
            <div key={g.canonical_key} className="dup-group">
              <div className="dup-group-title">
                <strong>{g.canonical_display}</strong>
                <code>{g.canonical_key}</code>
              </div>
              <ul>
                {g.teams.map((t) => (
                  <li key={t.id}>
                    <label>
                      <input
                        type="radio"
                        name={`keeper-${g.canonical_key}`}
                        checked={keepers[g.canonical_key] === t.id}
                        onChange={() =>
                          setKeepers((k) => ({
                            ...k,
                            [g.canonical_key]: t.id,
                          }))
                        }
                      />
                      #{t.id} {t.display_name}{" "}
                      <span style={{ color: "var(--muted)" }}>
                        ({t.normalized_key})
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              <button
                disabled={merging}
                onClick={() => mergeGroup(g)}
              >
                Объединить в выбранную
              </button>
            </div>
          ))}
        </section>
      )}

      <div className="filters panel">
        <input
          placeholder="Поиск"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button onClick={load}>Найти</button>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <div className="grid-2">
        <div className="panel" style={{ maxHeight: 480, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                <th></th>
                <th>Название (EN)</th>
                <th>Ключ (normalized)</th>
              </tr>
            </thead>
            <tbody>
              {teams.map((t) => (
                <tr
                  key={t.id}
                  onClick={() => select(t)}
                  style={{
                    cursor: "pointer",
                    background:
                      selected?.id === t.id ? "#1e3a5f" : undefined,
                  }}
                >
                  <td>
                    {t.logo_url ? (
                      <img src={t.logo_url} alt="" className="team-logo" />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>{t.display_name}</td>
                  <td style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                    {t.normalized_key}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          {selected ? (
            <>
              <h3>Редактирование #{selected.id}</h3>
              {selected.logo_url && (
                <img
                  src={selected.logo_url}
                  alt=""
                  className="team-logo"
                  style={{ width: 80, height: 80, marginBottom: "1rem" }}
                />
              )}
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Название (англ., для справочника)
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Спорт
                <input
                  value={sport}
                  onChange={(e) => setSport(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Алиасы (RO/RU/другие написания с сайтов)
                <textarea
                  value={aliases}
                  onChange={(e) => setAliases(e.target.value)}
                  rows={3}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "1rem" }}>
                Логотип (png/jpg/webp)
                <input type="file" accept="image/*" onChange={onLogo} />
              </label>
              <button onClick={save}>Сохранить</button>
            </>
          ) : (
            <p style={{ color: "var(--muted)" }}>Выберите команду в таблице</p>
          )}
        </div>
      </div>
    </>
  );
}
