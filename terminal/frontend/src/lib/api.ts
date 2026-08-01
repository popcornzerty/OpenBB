/** Client typé du backend. Les chemins passent par le proxy Vite en
 *  développement et par le sidecar en application empaquetée. */

/** Port du backend local. Doit rester aligné avec ``settings.port``. */
const BACKEND = "http://127.0.0.1:8801";

/** En développement, Vite sert le frontend et relaie ``/api`` vers le backend.
 *  Dans la fenêtre Tauri, la page est servie depuis ``tauri.localhost`` : le
 *  chemin relatif ne mènerait nulle part, il faut viser le backend en clair. */
const IS_TAURI =
  typeof window !== "undefined" && window.location.hostname.endsWith("tauri.localhost");

const ORIGIN = IS_TAURI ? BACKEND : window.location.origin;
const BASE = "/api";

async function get<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + path, ORIGIN);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  const response = await fetch(url.toString());
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* corps non JSON : on garde le code HTTP */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export type PeaStatus = "eligible" | "non_eligible" | "inconnu";

export interface Health {
  status: string;
  universe_size: number;
  valuation_window_years: number;
  data_note: string;
}

export interface SearchResult {
  symbol: string;
  name: string;
  exchange: string | null;
  listing_country: string | null;
  quote_type: string | null;
  pea_status: PeaStatus;
  source: string;
}

export interface Quote {
  symbol: string;
  name: string | null;
  exchange: string | null;
  last_price: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  volume: number | null;
  year_high: number | null;
  year_low: number | null;
  currency: string | null;
  as_of: string;
}

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
}

export interface IndexSnapshot {
  symbol: string;
  name: string;
  country: string;
  date?: string;
  close?: number;
  change_percent?: number | null;
  error?: string;
}

export interface Company {
  symbol: string;
  profile: Record<string, unknown>;
  pea: {
    status: PeaStatus;
    country_iso: string | null;
    country_label: string | null;
    reason: string;
  };
  metrics: Record<string, number | string | null>;
  quote: Quote | null;
}

export interface ScreenerRow {
  symbol: string;
  name: string;
  index: string;
  exchange: string;
  currency: string;
  country_iso: string;
  country_label: string;
  sector: string;
  industry: string;
  market_cap: number | null;
  market_cap_eur: number | null;
  pea_status: PeaStatus;
  pea_reason: string;
}

export interface ValuationComponent {
  key: string;
  label: string;
  median_multiple: number;
  dispersion: number;
  weight: number;
  current_multiple: number | null;
  observations: number;
}

export interface QualityAxis {
  key: string;
  label: string;
  score: number;
  weight: number;
  detail: string;
}

export interface Valuation {
  symbol: string;
  name: string;
  currency: string | null;
  window_years: number;
  quality_factor: number;
  quality: { score: number; axes: QualityAxis[]; method: string } | null;
  last_price: number;
  fair_value: number | null;
  gap: number | null;
  verdict: string;
  confidence: { level: string; periods_used: number; caveats: string[] };
  components: ValuationComponent[];
  excluded_components: { key: string; label: string; reason: string }[];
  backfilled_until: string | null;
  series: {
    dates: string[];
    price: (number | null)[];
    fair_value: (number | null)[];
  };
  projection: { dates: string[]; fair_value: (number | null)[]; note: string };
  method: string;
  periods_used: { period_ending: string; available_from: string }[];
  as_of: string;
}

export const api = {
  health: () => get<Health>("/health"),

  search: (q: string, limit = 12) =>
    get<{ query: string; is_isin: boolean; results: SearchResult[] }>("/search", { q, limit }),

  quotes: (symbols: string[]) =>
    get<{ quotes: Quote[]; errors: { symbol: string; error: string }[] }>("/market/quotes", {
      symbols: symbols.join(","),
    }),

  historical: (symbol: string, params?: { start_date?: string; interval?: string }) =>
    get<{ symbol: string; interval: string; rows: Candle[] }>(
      `/market/historical/${encodeURIComponent(symbol)}`,
      params,
    ),

  indices: () => get<{ indices: IndexSnapshot[] }>("/market/indices"),

  company: (symbol: string) => get<Company>(`/company/${encodeURIComponent(symbol)}`),

  fundamentals: (symbol: string) =>
    get<{
      symbol: string;
      income: Record<string, unknown>[];
      balance: Record<string, unknown>[];
      cash: Record<string, unknown>[];
      note: string;
    }>(`/company/${encodeURIComponent(symbol)}/fundamentals`),

  dividends: (symbol: string) =>
    get<{ symbol: string; rows: { ex_dividend_date: string; amount: number }[] }>(
      `/company/${encodeURIComponent(symbol)}/dividends`,
    ),

  news: (symbol: string, limit = 15) =>
    get<{ symbol: string; rows: Record<string, string>[] }>(
      `/company/${encodeURIComponent(symbol)}/news`,
      { limit },
    ),

  screenerFilters: () =>
    get<{ indices: string[]; countries: { iso: string; label: string }[]; sectors: string[]; total: number }>(
      "/screener/filters",
    ),

  screener: (params: Record<string, unknown>) =>
    get<{ total: number; offset: number; limit: number; rows: ScreenerRow[] }>("/screener", params),

  valuation: (symbol: string) => get<Valuation>(`/valuation/${encodeURIComponent(symbol)}`),

  watchlists: () => get<{ watchlists: Record<string, string[]> }>("/watchlists"),
};
