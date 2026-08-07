import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Candle,
  type Company as CompanyData,
  type SymbolInsiders,
} from "../lib/api";
import { Chart, type ChartSeries } from "../components/Chart";
import { PeaBadge } from "../components/PeaBadge";
import { changeClass, compact, date, money, num, pct, price } from "../lib/format";

const RANGES = [
  { label: "1 M", days: 30 },
  { label: "6 M", days: 182 },
  { label: "1 A", days: 365 },
  { label: "5 A", days: 1826 },
];

type Tab = "fondamentaux" | "dividendes" | "inities" | "actualites";

function isoDaysAgo(days: number): string {
  const when = new Date();
  when.setDate(when.getDate() - days);
  return when.toISOString().slice(0, 10);
}

/** Fiche société : identité, verdict PEA, chiffres clés, cours et comptes. */
export function Company({ symbol }: { symbol: string }) {
  const [data, setData] = useState<CompanyData | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [range, setRange] = useState(365);
  const [tab, setTab] = useState<Tab>("fondamentaux");
  const [error, setError] = useState<string | null>(null);

  const [fundamentals, setFundamentals] = useState<Awaited<ReturnType<typeof api.fundamentals>> | null>(null);
  const [dividends, setDividends] = useState<{ ex_dividend_date: string; amount: number }[]>([]);
  const [news, setNews] = useState<Record<string, string>[]>([]);
  const [insiders, setInsiders] = useState<SymbolInsiders | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.company(symbol).then(setData).catch((err) => setError(err.message));
  }, [symbol]);

  useEffect(() => {
    api
      .historical(symbol, { start_date: isoDaysAgo(range) })
      .then((response) => setCandles(response.rows))
      .catch(() => setCandles([]));
  }, [symbol, range]);

  useEffect(() => {
    setFundamentals(null);
    setDividends([]);
    setNews([]);
    setInsiders(null);
    if (tab === "fondamentaux") {
      api.fundamentals(symbol).then(setFundamentals).catch(() => setFundamentals(null));
    } else if (tab === "dividendes") {
      api.dividends(symbol).then((r) => setDividends(r.rows)).catch(() => setDividends([]));
    } else if (tab === "inities") {
      api.symbolInsiders(symbol).then(setInsiders).catch(() => setInsiders(null));
    } else {
      api.news(symbol).then((r) => setNews(r.rows)).catch(() => setNews([]));
    }
  }, [symbol, tab]);

  const series = useMemo<ChartSeries[]>(
    () => [
      {
        id: "close",
        label: "Cours",
        color: "#5aa9ff",
        area: true,
        data: candles.map((c) => ({ time: c.date.slice(0, 10), value: c.close })),
      },
    ],
    [candles],
  );

  if (error) return <div className="callout error">{error}</div>;
  if (!data) return <div className="spinner">Chargement de {symbol}…</div>;

  const profile = data.profile as Record<string, string | number | null>;
  const metrics = data.metrics;
  const quote = data.quote;
  const currency = (profile.currency as string) ?? null;
  const variation =
    quote?.last_price && quote?.prev_close ? quote.last_price / quote.prev_close - 1 : null;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-body">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div className="row" style={{ gap: 12 }}>
                <span className="sym" style={{ fontSize: 20 }}>{symbol}</span>
                <PeaBadge status={data.pea.status} reason={data.pea.reason} />
              </div>
              <div style={{ fontSize: 16, marginTop: 4 }}>{profile.name as string}</div>
              <div className="note" style={{ marginTop: 3 }}>
                {[profile.stock_exchange, profile.sector, profile.industry_category, data.pea.country_label]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="num" style={{ fontSize: 26 }}>
                {price(quote?.last_price ?? null, currency)}
              </div>
              <div className={`num ${changeClass(variation)}`} style={{ fontSize: 15 }}>
                {pct(variation)}
              </div>
            </div>
          </div>

          <div className="callout" style={{ marginTop: 12 }}>{data.pea.reason}</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Cours</span>
          <div className="chips">
            {RANGES.map((item) => (
              <button
                key={item.days}
                className={`chip ${range === item.days ? "active" : ""}`}
                onClick={() => setRange(item.days)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <div className="panel-body">
          {candles.length > 0 ? (
            <Chart series={series} height={300} />
          ) : (
            <div className="spinner">Chargement de l'historique…</div>
          )}
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><span className="panel-title">Chiffres clés</span></div>
        <div className="panel-body">
          <div className="kpis">
            <Kpi label="Capitalisation" value={compact(metrics.market_cap as number, currency ?? "")} />
            <Kpi label="PER" value={num(metrics.pe_ratio as number)} />
            <Kpi label="PER estimé" value={num(metrics.forward_pe as number)} />
            <Kpi label="Cours / actif net" value={num(metrics.price_to_book as number)} />
            <Kpi label="Rendement" value={pct(metrics.dividend_yield as number)} />
            <Kpi label="ROE" value={pct(metrics.return_on_equity as number)} />
            <Kpi label="Marge nette" value={pct(metrics.profit_margin as number)} />
            <Kpi label="Marge opér." value={pct(metrics.operating_margin as number)} />
            <Kpi label="Dette / fonds propres" value={num(metrics.debt_to_equity as number)} />
            <Kpi label="Bêta" value={num(metrics.beta as number)} />
            <Kpi label="Croissance CA" value={pct(metrics.revenue_growth as number)} />
            <Kpi label="Salariés" value={compact(profile.employees as number)} />
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="tabs">
          <button className={tab === "fondamentaux" ? "active" : ""} onClick={() => setTab("fondamentaux")}>
            Fondamentaux
          </button>
          <button className={tab === "dividendes" ? "active" : ""} onClick={() => setTab("dividendes")}>
            Dividendes
          </button>
          <button className={tab === "inities" ? "active" : ""} onClick={() => setTab("inities")}>
            Mouvements d'initiés
          </button>
          <button className={tab === "actualites" ? "active" : ""} onClick={() => setTab("actualites")}>
            Actualités
          </button>
        </div>

        {tab === "fondamentaux" && (
          <div className="panel-body flush">
            {!fundamentals ? (
              <div className="spinner">Chargement des comptes…</div>
            ) : (
              <>
                <StatementTable
                  title="Compte de résultat"
                  rows={fundamentals.income}
                  fields={[
                    ["total_revenue", "Chiffre d'affaires"],
                    ["gross_profit", "Marge brute"],
                    ["operating_income", "Résultat opérationnel"],
                    ["ebitda", "EBITDA"],
                    ["net_income", "Résultat net"],
                    ["diluted_earnings_per_share", "BPA dilué"],
                  ]}
                  currency={currency}
                />
                <StatementTable
                  title="Bilan"
                  rows={fundamentals.balance}
                  fields={[
                    ["total_assets", "Total de l'actif"],
                    ["total_current_assets", "Actif courant"],
                    ["current_liabilities", "Passif courant"],
                    ["total_debt", "Dette totale"],
                    ["net_debt", "Dette nette"],
                    ["common_stock_equity", "Capitaux propres"],
                  ]}
                  currency={currency}
                />
                <StatementTable
                  title="Flux de trésorerie"
                  rows={fundamentals.cash}
                  fields={[
                    ["operating_cash_flow", "Flux d'exploitation"],
                    ["capital_expenditure", "Investissements"],
                    ["free_cash_flow", "Flux de trésorerie libre"],
                    ["cash_dividends_paid", "Dividendes versés"],
                  ]}
                  currency={currency}
                />
                <div className="panel-body">
                  <div className="callout warn">{fundamentals.note}</div>
                </div>
              </>
            )}
          </div>
        )}

        {tab === "dividendes" && (
          <div className="panel-body flush table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date de détachement</th>
                  <th className="right">Montant</th>
                </tr>
              </thead>
              <tbody>
                {dividends.slice().reverse().slice(0, 40).map((row) => (
                  <tr key={row.ex_dividend_date}>
                    <td>{date(row.ex_dividend_date)}</td>
                    <td className="right num">{price(row.amount, currency)}</td>
                  </tr>
                ))}
                {dividends.length === 0 && (
                  <tr><td colSpan={2} className="faint" style={{ padding: 18 }}>Aucun dividende connu.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {tab === "inities" && <Inities data={insiders} symbol={symbol} />}

        {tab === "actualites" && (
          <div className="panel-body">
            {news.length === 0 && <div className="faint">Aucune actualité disponible.</div>}
            <div className="stack" style={{ gap: 10 }}>
              {news.map((item, i) => (
                <a
                  key={item.id ?? i}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  style={{ color: "inherit", textDecoration: "none" }}
                >
                  <div className="kpi">
                    <div style={{ fontWeight: 550, marginBottom: 3 }}>{item.title}</div>
                    <div className="note">{item.summary}</div>
                    <div className="faint" style={{ marginTop: 5, fontSize: 11 }}>
                      {item.source} · {date(item.date)}
                    </div>
                  </div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

/** Un état financier, exercices en colonnes — la lecture naturelle d'un analyste. */
function StatementTable({
  title,
  rows,
  fields,
  currency,
}: {
  title: string;
  rows: Record<string, unknown>[];
  fields: [string, string][];
  currency: string | null;
}) {
  if (!rows || rows.length === 0) return null;
  const periods = rows
    .map((row) => String(row.period_ending ?? "").slice(0, 10))
    .filter(Boolean);

  return (
    <div className="table-wrap" style={{ borderBottom: "1px solid var(--border-soft)" }}>
      <table>
        <thead>
          <tr>
            <th style={{ minWidth: 200 }}>{title}</th>
            {periods.map((period) => (
              <th key={period} className="right">{period.slice(0, 4)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fields.map(([key, label]) => (
            <tr key={key}>
              <td className="dim">{label}</td>
              {rows.map((row, i) => {
                const raw = row[key];
                const value = typeof raw === "number" ? raw : null;
                const perShare = key === "diluted_earnings_per_share";
                return (
                  <td key={i} className="right num">
                    {perShare ? price(value, currency) : compact(value, currency ?? "")}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


/** Déclarations de dirigeants sur cette valeur.
 *
 *  Publiées par l'AMF sous trois jours ouvrés, elles disent ce que ceux qui
 *  connaissent le mieux la société font de leurs propres titres. */
function Inities({ data, symbol }: { data: SymbolInsiders | null; symbol: string }) {
  if (data === null) {
    return <div className="spinner">Lecture des déclarations de l'AMF…</div>;
  }

  if (!data.in_scope) {
    return (
      <div className="callout">
        {symbol} n'est pas cotée en France : l'AMF ne publie donc aucune déclaration de
        dirigeant la concernant. L'absence de ligne ici ne signifie pas qu'il ne s'y
        passe rien.
      </div>
    );
  }

  if (data.insiders.length === 0) {
    return (
      <div className="callout">
        Aucune déclaration de dirigeant sur {symbol} depuis le {date(data.since)}.
      </div>
    );
  }

  const achats = data.insiders.filter((r) => r.sens === "achat");
  const ventes = data.insiders.filter((r) => r.sens === "vente");
  const solde =
    achats.reduce((t, r) => t + (r.montant ?? 0), 0) -
    ventes.reduce((t, r) => t + (r.montant ?? 0), 0);

  return (
    <div className="stack">
      <div className="kpis">
        <div className="kpi">
          <div className="label">Déclarations</div>
          <div className="value">{data.insiders.length}</div>
        </div>
        <div className="kpi">
          <div className="label">Achats</div>
          <div className="value up">{achats.length}</div>
        </div>
        <div className="kpi">
          <div className="label">Ventes</div>
          <div className="value down">{ventes.length}</div>
        </div>
        <div className="kpi">
          <div className="label">Solde net</div>
          {/* Un solde vendeur n'est pas un signal en soi : les dirigeants
              vendent aussi pour des raisons personnelles ou fiscales. */}
          <div className={`value ${changeClass(solde)}`}>{money(solde, "EUR")}</div>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Opéré le</th>
              <th>Déclarant</th>
              <th>Fonction</th>
              <th>Sens</th>
              <th>Nature</th>
              <th className="right">Volume</th>
              <th className="right">Prix payé</th>
              <th className="right">Montant</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.insiders.map((row) => (
              <tr key={row.id}>
                <td className="num">{date(row.transaction_le ?? row.publie_le)}</td>
                <td>{row.declarant ?? <span className="faint">non extrait</span>}</td>
                <td className="faint truncate" style={{ maxWidth: 220 }} title={row.fonction ?? undefined}>
                  {row.fonction ?? "—"}
                </td>
                <td className={row.sens === "achat" ? "up" : row.sens === "vente" ? "down" : ""}>
                  {row.sens === "achat" ? "▲ achat" : row.sens === "vente" ? "▼ vente" : "—"}
                </td>
                <td className="faint">{row.nature ?? "—"}</td>
                <td className="right num">{row.volume === null ? "—" : compact(row.volume)}</td>
                <td className="right num dim">{row.prix === null ? "—" : num(row.prix)}</td>
                <td className="right num">{money(row.montant, "EUR")}</td>
                <td className="right">
                  {row.document && (
                    <a className="chip" href={row.document} target="_blank" rel="noreferrer">
                      Avis
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="note">
        Déclarations publiées par l'AMF au titre de l'article L. 621-18-2, sous trois
        jours ouvrés. Le sens est déduit de la nature déclarée, qui reste affichée :
        souscrire à un plan d'épargne salariale ou recevoir des actions gratuites n'est
        pas acheter en bourse. Un solde vendeur ne constitue pas un signal en soi — les
        dirigeants cèdent aussi pour financer un impôt ou diversifier leur patrimoine.
      </div>
    </div>
  );
}
