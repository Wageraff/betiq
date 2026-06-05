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
  const [dupError, setDupError] = useState("");
  const [keepers, setKeepers] = useState<Record<string, number>>({});
  const [mergeIds, setMergeIds] = useState<number[]>([]);
  const [manualKeeperId, setManualKeeperId] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Team | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [sport, setSport] = useState("");
  const [aliases, setAliases] = useState("");
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [merging, setMerging] = useState(false);

  const loadDuplicates = async () => {
    setDupError("");
    try {
      const dups = await api.get<TeamDuplicatesOut>("/teams/duplicates");
      setDupGroups(dups.groups);
      const next: Record<string, number> = {};
      for (const g of dups.groups) {
        const preferred =
          g.teams.find((t) => t.normalized_key === g.canonical_key) || g.teams[0];
        next[g.canonical_key] = preferred.id;
      }
      setKeepers(next);
    } catch (e) {
      setDupGroups([]);
      setDupError(
        String(e).includes("404")
          ? "Endpoint /teams/duplicates not found — run git pull and restart betiq-api"
          : String(e)
      );
    }
  };

  const load = async () => {
    setError("");
    const params = new URLSearchParams({ limit: "200" });
    if (q) params.set("q", q);
    try {
      const teamList = await api.get<Team[]>(`/teams?${params}`);
      setTeams(teamList);
    } catch (e) {
      setError(String(e));
    }
    await loadDuplicates();
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

  const toggleMergeId = (id: number) => {
    setMergeIds((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
      if (next.length > 0 && (!manualKeeperId || !next.includes(manualKeeperId))) {
        setManualKeeperId(next[0]);
      }
      if (next.length === 0) setManualKeeperId(null);
      return next;
    });
  };

  const save = async () => {
    if (!selected) return;
    try {
      const updated = await api.patch<Team>(`/teams/${selected.id}`, {
        display_name: displayName,
        sport: sport || null,
        aliases: aliases || null,
      });
      setMsg("Saved");
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
      setMsg("Logo uploaded");
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
      if (selected && duplicateIds.includes(selected.id)) setSelected(null);
      setMergeIds([]);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setMerging(false);
    }
  };

  const mergeManual = async () => {
    if (!manualKeeperId || mergeIds.length < 2) return;
    const duplicateIds = mergeIds.filter((id) => id !== manualKeeperId);
    setMerging(true);
    setError("");
    try {
      const res = await api.post<{ message: string }>("/teams/merge", {
        keeper_id: manualKeeperId,
        duplicate_ids: duplicateIds,
      });
      setMsg(res.message);
      setMergeIds([]);
      setManualKeeperId(null);
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
      setMergeIds([]);
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setMerging(false);
    }
  };

  const mergeTeamsForManual = teams.filter((t) => mergeIds.includes(t.id));

  return (
    <>
      <h2>Teams catalog</h2>
      <p style={{ color: "var(--muted)" }}>
        English display names and keys (match_key). Local spellings from sources go in aliases.
      </p>

      <section className="panel dup-groups">
        <div className="dup-groups-head">
          <h3>Merge duplicates</h3>
          <button
            className="secondary"
            disabled={merging}
            onClick={mergeAllAuto}
          >
            Scan and merge all
          </button>
        </div>

        {dupError && <p className="error">{dupError}</p>}

        {!dupError && dupGroups.length === 0 && (
          <p style={{ color: "var(--muted)", marginBottom: "1rem" }}>
            No duplicate groups found automatically. If you still see pairs like
            &quot;Franta&quot; and &quot;France&quot;, select them manually below or
            click &quot;Scan and merge all&quot;.
          </p>
        )}

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
            <button disabled={merging} onClick={() => mergeGroup(g)}>
              Merge group
            </button>
          </div>
        ))}

        <div className="dup-manual" style={{ marginTop: "1rem" }}>
          <h4 style={{ margin: "0 0 0.5rem" }}>Manual merge</h4>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem", margin: "0 0 0.75rem" }}>
            Check &quot;Merge&quot; for 2+ teams that are the same entity.
          </p>
          {mergeIds.length >= 2 ? (
            <>
              <p>Selected: {mergeIds.length}</p>
              <ul style={{ listStyle: "none", padding: 0 }}>
                {mergeTeamsForManual.map((t) => (
                  <li key={t.id} style={{ marginBottom: 4 }}>
                    <label>
                      <input
                        type="radio"
                        name="manual-keeper"
                        checked={manualKeeperId === t.id}
                        onChange={() => setManualKeeperId(t.id)}
                      />
                      Keep #{t.id} {t.display_name} ({t.normalized_key})
                    </label>
                  </li>
                ))}
              </ul>
              <button disabled={merging || !manualKeeperId} onClick={mergeManual}>
                Merge selected
              </button>
            </>
          ) : (
            <p style={{ color: "var(--muted)" }}>Select at least two teams in the table.</p>
          )}
        </div>
      </section>

      <div className="filters panel">
        <input
          placeholder="Search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button onClick={load}>Search</button>
      </div>
      {error && <p className="error">{error}</p>}
      {msg && <p style={{ color: "var(--ok)" }}>{msg}</p>}

      <div className="grid-2">
        <div className="panel" style={{ maxHeight: 480, overflow: "auto" }}>
          <table>
            <thead>
              <tr>
                <th title="For manual merge">Merge</th>
                <th></th>
                <th>Name (EN)</th>
                <th>Key (normalized)</th>
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
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={mergeIds.includes(t.id)}
                      onChange={() => toggleMergeId(t.id)}
                    />
                  </td>
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
              <h3>Edit #{selected.id}</h3>
              {selected.logo_url && (
                <img
                  src={selected.logo_url}
                  alt=""
                  className="team-logo"
                  style={{ width: 80, height: 80, marginBottom: "1rem" }}
                />
              )}
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Display name (English)
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Sport
                <input
                  value={sport}
                  onChange={(e) => setSport(e.target.value)}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "0.5rem" }}>
                Aliases (local spellings from sources)
                <textarea
                  value={aliases}
                  onChange={(e) => setAliases(e.target.value)}
                  rows={3}
                  style={{ width: "100%", marginTop: 4 }}
                />
              </label>
              <label style={{ display: "block", marginBottom: "1rem" }}>
                Logo (png/jpg/webp)
                <input type="file" accept="image/*" onChange={onLogo} />
              </label>
              <button onClick={save}>Save</button>
            </>
          ) : (
            <p style={{ color: "var(--muted)" }}>Select a team in the table</p>
          )}
        </div>
      </div>
    </>
  );
}
