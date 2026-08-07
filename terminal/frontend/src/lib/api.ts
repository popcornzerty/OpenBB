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

async function post<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + path, ORIGIN);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  const response = await fetch(url.toString(), { method: "POST" });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* corps non JSON */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

/** Requête avec corps JSON, pour les écritures. */
async function send<T>(
  method: "PUT" | "POST" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(new URL(BASE + path, ORIGIN).toString(), {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const parsed = await response.json();
      if (parsed?.detail) detail = parsed.detail;
    } catch {
      /* corps non JSON */
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
  /** Rendement du dividende, en fraction (0,047 pour 4,7 %). */
  dividend_yield: number | null;
  /** Croissance annualisée sur la dernière période continue. */
  dividend_cagr: number | null;
  /** Période retenue, par exemple « 2020–2025 ». */
  dividend_cagr_window: string;
  payout_ratio: number | null;
  fcf_coverage: number | null;
  dividend_safety: DividendSafety;
  dividend_safety_reason: string;
  dividend_frequency: string;
  /** Prochain détachement **estimé** d'après le rythme passé. */
  next_ex_date: string;
  pea_status: PeaStatus;
  pea_reason: string;
}

export type DividendSafety = "sur" | "tendu" | "non_couvert" | "inconnu" | "aucun";

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

/** Un exercice du tableau : publié, ou estimé par le consensus. */
export interface TableColumn {
  label: string;
  year: number;
  estimate: boolean;
  period_ending: string | null;
  /** Cours de référence : clôture d'exercice, ou cours actuel si estimé. */
  price: number | null;
  analysts: number | null;
  thin: boolean;
}

export interface TableRow {
  key: string;
  label: string;
  unit: "currency" | "percent" | "ratio" | "per_share" | "count";
  values: (number | null)[];
  note: string;
}

export interface ValuationTables {
  columns: TableColumn[];
  income_rows: TableRow[];
  valuation_rows: TableRow[];
  notes: string[];
  price_target: {
    mean?: number | null;
    median?: number | null;
    low?: number | null;
    high?: number | null;
  };
}

/** Évolution d'un multiple et sa moyenne historique. */
export interface MultipleHistory {
  component: string;
  label: string;
  series: { date: string; value: number }[];
  current: number;
  average: number;
  median: number;
  stdev: number | null;
  gap_to_average: number;
  gap_to_median: number;
  band_low: number | null;
  band_high: number | null;
  min: number;
  max: number;
  observations: number;
  coverage: number | null;
  from: string;
  to: string;
  years: number;
  backfilled_until: string | null;
  /** Début de la période réellement adossée à des comptes publiés. */
  reference_from: string;
  reference_years: number;
  reference_observations: number;
  stats_backfilled: boolean;
}

/** Un franchissement de seuil déclaré à l'AMF. */
export interface AmfCrossing {
  id: string;
  symbol: string;
  /** Dénomination de l'univers, absente hors univers plutôt que devinée. */
  name: string | null;
  societe: string | null;
  publie_le: string;
  document: string | null;
  declarant: string | null;
  /** « morale », « physique » ou « inconnue ». */
  declarant_nature: string;
  sens: "hausse" | "baisse" | null;
  seuil: number | null;
  seuil_nature: string | null;
  franchi_le: string | null;
  /** Actions **détenues** après franchissement, pas achetées. */
  actions: number | null;
  part_capital: number | null;
  /** Clôture du jour de franchissement : référence calculée, pas un prix payé. */
  cours: number | null;
  valeur_participation: number | null;
  lisible: boolean;
}

/** Une déclaration de dirigeant (initié). */
export interface AmfInsider {
  id: number;
  numero: string | null;
  symbol: string;
  name: string | null;
  societe: string | null;
  publie_le: string;
  document: string | null;
  declarant: string | null;
  fonction: string | null;
  emetteur: string | null;
  nature: string | null;
  sens: "achat" | "vente" | null;
  instrument: string | null;
  isin: string | null;
  lieu: string | null;
  transaction_le: string | null;
  prix: number | null;
  devise: string | null;
  volume: number | null;
  montant: number | null;
  lisible: boolean;
}

export interface AmfMovements {
  scope: string;
  name: string;
  days: number;
  symbols: string[];
  /** Valeurs que la source peut couvrir : émetteurs cotés en France. */
  in_scope: string[];
  out_of_scope: string[];
  crossings: AmfCrossing[];
  crossings_scanned: number;
  insiders: AmfInsider[];
  since: string;
}

/** Une ligne détenue par un gérant américain déclarant à la SEC. */
export interface ManagerHolding {
  holder: string;
  categorie: string;
  symbol: string;
  date: string;
  shares: number | null;
  value: number | null;
  pct_held: number | null;
  /** Variation depuis le dépôt précédent : le mouvement du gérant. */
  pct_change: number | null;
}

export interface Manager {
  holder: string;
  categorie: string;
  positions: number;
  value: number;
  last_reported: string;
  achats: number;
  ventes: number;
  holdings: ManagerHolding[];
}

export interface Managers {
  scope: string;
  name: string;
  managers: Manager[];
  candidates: number;
  /** Lignes de fonds indiciels écartées du classement. */
  index_lines_excluded: number;
  as_of: string;
  symbols: string[];
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
  dividend: {
    yield: number | null;
    growth: number | null;
    growth_window: string;
    payout_ratio: number | null;
    fcf_coverage: number | null;
    safety: DividendSafety;
    safety_reason: string;
    next_ex_date: string | null;
  } | null;
  tables: ValuationTables | null;
  per_history: MultipleHistory | null;
}

export interface RankingStatus {
  state: "idle" | "running" | "done" | "error";
  total: number;
  done: number;
  progress: number;
  elapsed_seconds: number | null;
  computed: number;
  skipped: number;
  error: string | null;
  as_of: number | null;
}

export interface RankingRow {
  symbol: string;
  name: string;
  sector: string;
  country: string;
  index: string;
  /** Capitalisation en euros, comparable d'une place à l'autre. */
  market_cap_eur: number | null;
  last_price: number;
  fair_value: number | null;
  /** Écart cours / juste valeur. Négatif = sous-coté. */
  gap: number | null;
  /** Facteur de fiabilité dans [0, 1]. */
  reliability: number;
  reliability_parts: {
    periods: number;
    breadth: number;
    stability: number;
    weighted_dispersion: number | null;
  };
  /** Écart pondéré par la fiabilité. Positif = sous-coté. */
  adjusted_discount: number | null;
  verdict: string;
  confidence: string;
  periods_used: number;
  components: number;
  currency: string | null;
}

export interface RankingResult extends RankingStatus {
  rows: RankingRow[];
  failures: { symbol: string; reason: string }[];
  method: string;
}

export interface PositionInput {
  symbol: string;
  quantity: number;
  average_cost: number;
  currency: string;
  /** Date d'entrée : elle décide des dividendes comptabilisés. */
  opened_at: string;
  label: string;
}

export interface PortfolioRow extends PositionInput {
  cost_basis: number;
  name: string | null;
  price: number | null;
  /** `last` = dernier cours ; `prev_close` = clôture précédente, faute de mieux. */
  price_source?: "last" | "prev_close" | "none";
  market_value: number | null;
  gain: number | null;
  gain_percent: number | null;
  pea_status: PeaStatus;
  pea_reason: string;
  sector: string | null;
  country_label: string | null;
  dividend?: {
    accrued: {
      amount: number | null;
      per_share: number | null;
      payments: number;
      last: string | null;
    };
    next_ex_date: string | null;
    next_estimated_amount: number | null;
  };
}

export interface PortfolioSummary {
  positions: number;
  total_value: number;
  total_cost: number;
  total_gain: number | null;
  total_gain_percent: number | null;
  confirmed_pea_value: number;
  confirmed_pea_share: number | null;
  /** Cumul des dividendes détachés depuis l'entrée en position. */
  dividends_collected: number;
  dividend_yield_on_cost: number | null;
  realized: RealizedTotals;
  /** Latent + réalisé + dividendes : ce que le portefeuille a rapporté. */
  overall_gain: number;
  /** Rapporté au capital engagé, lignes vendues comprises. */
  overall_gain_percent: number | null;
  upcoming: {
    symbol: string;
    date: string;
    amount: number | null;
    /** Somme des détachements attendus jusqu'à cette date incluse. */
    cumulative: number;
  }[];
  upcoming_total: number;
  /** Lignes dont le montant reste inconnu, donc absentes du cumul. */
  upcoming_unknown: number;
}

/** Une cession, totale ou partielle. */
export interface Sale {
  id: string;
  symbol: string;
  label: string;
  quantity: number;
  average_cost: number;
  sale_price: number;
  currency: string;
  opened_at: string;
  closed_at: string;
  cost_basis: number;
  proceeds: number;
  /** Produit net de frais : ce qui rentre réellement sur le compte. */
  net_proceeds: number;
  fees: number;
  gain: number;
  gain_percent: number | null;
  holding_days: number | null;
  dividends: number;
  total_return: number;
  note: string;
}

export interface RealizedTotals {
  count: number;
  cost_basis: number;
  proceeds: number;
  /** Produit net de frais : ce qui rentre réellement sur le compte. */
  net_proceeds: number;
  fees: number;
  gain: number;
  gain_percent: number | null;
  dividends: number;
  total_return: number;
  win_rate: number | null;
}

export interface AllocationSlice {
  label: string;
  value: number;
  share: number;
  contributors: string[];
}

export interface AllocationComparison {
  label: string;
  share: number;
  value: number;
  target: number | null;
  gap: number | null;
}

export interface Allocation {
  total: number;
  sectors: AllocationSlice[];
  regions: AllocationSlice[];
  look_through_value: number;
  look_through_share: number;
  classified_share: number;
  note: string;
  targets: { sectors: Record<string, number>; regions: Record<string, number> };
  sector_comparison: AllocationComparison[];
  region_comparison: AllocationComparison[];
  targets_total: { sectors: number; regions: number };
}

export const api = {
  health: () => get<Health>("/health"),

  portfolioStatus: () =>
    get<{
      positions: number;
      updated_at: string;
      today: string;
      wealthfolio: { available: boolean; database: string; positions: number };
    }>("/portfolio/status"),

  portfolio: () =>
    get<{
      rows: PortfolioRow[];
      summary: PortfolioSummary | null;
      updated_at: string;
      empty: boolean;
    }>("/portfolio/holdings"),

  savePosition: (symbol: string, position: PositionInput) =>
    send<{ count: number }>("PUT", `/portfolio/positions/${encodeURIComponent(symbol)}`, position),

  /** Retire une ligne sans rien enregistrer — pour une saisie erronée. */
  deletePosition: (symbol: string) =>
    send<{ count: number }>("DELETE", `/portfolio/positions/${encodeURIComponent(symbol)}`),

  /** Vend tout ou partie d'une ligne et enregistre la plus-value réalisée. */
  sellPosition: (
    symbol: string,
    sale: {
      quantity: number | null;
      price: number;
      date: string;
      fees: number;
      note: string;
    },
  ) =>
    send<{ sale: Sale; remaining: number }>(
      "POST",
      `/portfolio/positions/${encodeURIComponent(symbol)}/sell`,
      sale,
    ),

  realized: () => get<{ sales: Sale[]; totals: RealizedTotals }>("/portfolio/realized"),

  /** Corrige une cession enregistrée. La quantité n'y est pas modifiable :
   *  elle est liée au portefeuille, dont les titres ont été retirés. */
  editSale: (
    id: string,
    changes: {
      sale_price?: number;
      fees?: number;
      average_cost?: number;
      closed_at?: string;
      opened_at?: string;
      note?: string;
    },
  ) => send<Sale>("PUT", `/portfolio/realized/${encodeURIComponent(id)}`, changes),

  cancelSale: (id: string) =>
    send<{ cancelled: Sale; restored: boolean }>(
      "DELETE",
      `/portfolio/realized/${encodeURIComponent(id)}`,
    ),

  importCsv: (content: string, replace = true) =>
    send<{ count: number; imported: number; warnings: string[] }>(
      "POST",
      "/portfolio/positions/import-csv",
      { content, replace },
    ),

  importWealthfolio: () =>
    post<{ count: number; imported: number }>("/portfolio/positions/import-wealthfolio", {
      replace: true,
    }),

  allocation: () => get<Allocation>("/portfolio/allocation"),

  saveTargets: (sectors: Record<string, number>, regions: Record<string, number>) =>
    send<Allocation["targets"]>("PUT", "/portfolio/targets", { sectors, regions }),

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

  startRanking: (peaOnly = true) =>
    post<RankingStatus>("/screener/ranking/start", { pea_only: peaOnly }),

  ranking: () => get<RankingResult>("/screener/ranking"),

  valuation: (symbol: string) => get<Valuation>(`/valuation/${encodeURIComponent(symbol)}`),

  watchlists: () => get<{ watchlists: Record<string, string[]> }>("/watchlists"),

  /** Mouvements déclarés à l'AMF sur un portefeuille ou une liste de suivi. */
  amfMovements: (scope: "portefeuille" | "liste", name = "", days = 180) =>
    get<AmfMovements>("/alerts/amf", { scope, name, days }),

  /** Gérants américains les plus présents sur ces valeurs européennes. */
  managers: (scope: "portefeuille" | "liste", name = "", top = 4) =>
    get<Managers>("/alerts/managers", { scope, name, top }),

  /** Crée ou remplace une liste de suivi. */
  saveWatchlist: (name: string, symbols: string[]) =>
    send<{ name: string; symbols: string[] }>(
      "PUT",
      `/watchlists/${encodeURIComponent(name)}`,
      { symbols },
    ),

  deleteWatchlist: (name: string) =>
    send<{ watchlists: Record<string, string[]> }>(
      "DELETE",
      `/watchlists/${encodeURIComponent(name)}`,
    ),
};
