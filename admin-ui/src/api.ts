const API = "/api/admin/v1";

function headers(): HeadersInit {
  const key = localStorage.getItem("admin_key") || "";
  return {
    "Content-Type": "application/json",
    "X-Admin-Key": key,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...headers(), ...init?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),

  uploadLogo: async (teamId: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const key = localStorage.getItem("admin_key") || "";
    const res = await fetch(`${API}/teams/${teamId}/logo`, {
      method: "POST",
      headers: { "X-Admin-Key": key },
      body: fd,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};

export type MatchBrief = {
  id: number;
  slug: string | null;
  team_home: string;
  team_away: string;
  sport: string | null;
  competition: string | null;
  match_date: string | null;
  predictions_count: number;
  has_ai: boolean;
};

export type Team = {
  id: number;
  normalized_key: string;
  display_name: string;
  sport: string | null;
  logo_url: string | null;
  aliases: string | null;
};

export type Settings = {
  config_sections: { name: string; values: Record<string, string> }[];
  prompt_template_path: string;
  prompt_template_preview: string;
  sources: {
    id: number;
    name: string;
    scraper_module: string | null;
    geo: string | null;
    is_active: boolean;
  }[];
  admin_configured: boolean;
  anthropic_configured: boolean;
};
