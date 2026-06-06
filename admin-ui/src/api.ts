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

  download: async (path: string, filename: string) => {
    const key = localStorage.getItem("admin_key") || "";
    const res = await fetch(`${API}${path}`, {
      headers: { "X-Admin-Key": key },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

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
  match_key?: string | null;
  slug: string | null;
  team_home: string;
  team_away: string;
  sport: string | null;
  competition: string | null;
  round?: string | null;
  venue_name?: string | null;
  venue_city?: string | null;
  match_date: string | null;
  status?: string | null;
  score?: string | null;
  predictions_count: number;
  has_ai: boolean;
  ai_confidence?: string | null;
  has_api_football?: boolean;
  has_odds_api?: boolean;
  odds_count?: number;
  has_match_stats?: boolean;
};

export type MatchExternalId = {
  provider: string;
  external_id: string;
  link_method?: string | null;
  confidence?: number | null;
  linked_at?: string | null;
};

export type MatchStatsRow = {
  side: string;
  half: string;
  shots_on_goal?: number | null;
  shots_total?: number | null;
  corners?: number | null;
  fouls?: number | null;
  yellow_cards?: number | null;
  red_cards?: number | null;
  possession?: number | null;
  fetched_at?: string | null;
};

export type MatchOddsRow = {
  provider?: string;
  bookmaker: string;
  market: string;
  outcome: string;
  odds: string | number;
  point?: string | number | null;
  is_live: boolean;
  recorded_at?: string | null;
};

export type OddsHistoryRow = {
  bookmaker: string;
  market: string;
  outcome: string;
  odds_prev?: string | number | null;
  odds_curr: string | number;
  movement_pct?: string | number | null;
  direction?: string | null;
  is_significant: boolean;
  recorded_at?: string | null;
};

export type TeamFormRow = {
  match_date?: string | null;
  opponent_name?: string | null;
  is_home?: boolean | null;
  result?: string | null;
  goals_scored?: number | null;
  goals_conceded?: number | null;
  competition_name?: string | null;
};

export type OddsMarketSummary = {
  market: string;
  count: number;
  provider: string;
};

export type MatchOddsList = {
  match_id: number;
  market?: string | null;
  total: number;
  market_count: number;
  items: MatchOddsRow[];
};

export type MatchApiData = {
  status?: string | null;
  venue_name?: string | null;
  venue_city?: string | null;
  season?: string | null;
  round?: string | null;
  score?: string | null;
  score_ht?: string | null;
  stats_fetched_at?: string | null;
  odds_fetched_at?: string | null;
  external_ids: MatchExternalId[];
  match_stats: MatchStatsRow[];
  odds_total: number;
  odds_markets: OddsMarketSummary[];
  odds_market?: string | null;
  odds: MatchOddsRow[];
  odds_history: OddsHistoryRow[];
  lineups: { side?: string; formation?: string; coach_name?: string; players_count: number }[];
  team_form_home: TeamFormRow[];
  team_form_away: TeamFormRow[];
};

export type ApiCoverageMatch = {
  id: number;
  sport?: string | null;
  team_home: string;
  team_away: string;
  competition?: string | null;
  match_date?: string | null;
  status?: string | null;
  has_api_football: boolean;
  has_the_odds_api: boolean;
  odds_count: number;
  odds_fetched_at?: string | null;
  sport_keys: string[];
};

export type ApiCoverageSportKey = {
  sport_key: string;
  label: string;
  sport?: string | null;
  match_count: number;
  matches: ApiCoverageMatch[];
};

export type ApiSyncCoverage = {
  odds_sync_mode: string;
  upcoming_total: number;
  upcoming_by_sport?: Record<string, number>;
  window: {
    since?: string;
    until?: string;
    days_ahead?: number;
    skip_finished_hours?: number;
  };
  the_odds_api: {
    bulk_sport_keys?: ApiCoverageSportKey[];
    bulk_sport_key_count?: number;
    bulk_credits_per_run?: number;
    bulk_markets?: string;
    event_markets?: string;
    event_match_count?: number;
    event_credits_per_run?: number;
    unmapped_match_count?: number;
    unmapped_matches?: ApiCoverageMatch[];
  };
  api_football_odds: {
    enabled?: boolean;
    batch_size?: number;
    queue_count?: number;
    matches?: ApiCoverageMatch[];
  };
  odds_in_db: { api_football?: number; the_odds_api?: number };
};

export type ApiSyncStatus = {
  api_sync_enabled: boolean;
  api_football: {
    configured: boolean;
    requests_today?: number | null;
    limit_day?: number | null;
    subscription?: string | null;
    error?: string | null;
  };
  the_odds_api: {
    configured: boolean;
    remaining?: number | null;
    used?: number | null;
    error?: string | null;
  };
  db_counts: Record<string, number>;
  coverage?: ApiSyncCoverage | null;
};

export type PredictionBet = {
  bet_pick: string | null;
  odds: string | number | null;
  bet_type: string | null;
  is_main: boolean;
};

export type PredictionDetail = {
  id: number;
  source: string;
  language: string;
  author: string | null;
  source_url: string;
  title: string | null;
  full_text: string | null;
  scraped_at: string | null;
  bets: PredictionBet[];
};

export type MatchDetail = {
  match: MatchBrief;
  predictions: PredictionDetail[];
  ai_summary: string | null;
  ai_top_pick: string | null;
  ai_confidence: string | null;
  ai_generated_at: string | null;
  ai_model: string | null;
  api_data?: MatchApiData | null;
};

export type TeamBriefInGroup = {
  id: number;
  normalized_key: string;
  display_name: string;
  sport: string | null;
  logo_url: string | null;
};

export type TeamDuplicateGroup = {
  canonical_key: string;
  canonical_display: string;
  teams: TeamBriefInGroup[];
};

export type TeamDuplicatesOut = {
  groups: TeamDuplicateGroup[];
  total_groups: number;
};

export type Team = {
  id: number;
  normalized_key: string;
  display_name: string;
  sport: string | null;
  logo_url: string | null;
  aliases: string | null;
};

export type SourceStats = {
  runs: number;
  items_saved: number;
  errors: number;
  empty_runs: number;
  error_rate: number;
  save_rate: number;
  health: "ok" | "warn" | "error" | "idle";
  last_run_at: string | null;
  last_error_at: string | null;
  stats_days: number;
};

export type Source = {
  id: number;
  name: string;
  scraper_module: string | null;
  geo: string | null;
  is_active: boolean;
  last_success_at?: string | null;
  tier?: "high" | "medium" | "low" | null;
  stats?: SourceStats | null;
};

export type Settings = {
  config_sections: { name: string; values: Record<string, string> }[];
  prompt_template_path: string;
  prompt_template_preview: string;
  sources: Source[];
  admin_configured: boolean;
  anthropic_configured: boolean;
};

export type ApiQuotaStatus = {
  the_odds_api_remaining?: number | null;
  the_odds_api_used?: number | null;
  api_football_remaining?: number | null;
  api_football_limit?: number | null;
  checked_at: string;
};

export type CompetitionItem = {
  id: number;
  name: string;
  sport: string;
  country?: string | null;
  country_code?: string | null;
  matches_upcoming: number;
  is_tracked: boolean;
  sync_odds: boolean;
  sync_stats: boolean;
  sync_lineups: boolean;
  odds_markets?: string[] | null;
  odds_days_ahead?: number | null;
};

export type CompetitionsList = {
  items: CompetitionItem[];
  total: number;
  page: number;
  limit: number;
  quota: ApiQuotaStatus;
};
