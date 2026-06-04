import { useEffect, useState } from "react";
import { api, Team } from "../api";

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Team | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [sport, setSport] = useState("");
  const [aliases, setAliases] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = async () => {
    setError("");
    const params = new URLSearchParams({ limit: "100" });
    if (q) params.set("q", q);
    try {
      const data = await api.get<Team[]>(`/teams?${params}`);
      setTeams(data);
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

  return (
    <>
      <h2>Справочник команд / соперников</h2>
      <p style={{ color: "var(--muted)" }}>
        Справочник ведётся на английском (как ключи match_key). При парсинге варианты
        с сайтов (RO/RU) попадают в алиасы. Названия на карточках матчей — как на источнике.
      </p>
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
                      <img
                        src={t.logo_url}
                        alt=""
                        className="team-logo"
                      />
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
