import { useEffect, useState } from "react";
import { GlossaryHint } from "../components/GlossaryHint";
import { api, type ScreenerRow } from "../lib/api";
import { changeClass, compact, date, pct } from "../lib/format";
import { DividendBadge } from "../components/DividendBadge";
import { PeaBadge } from "../components/PeaBadge";
import { Undervalued } from "./Undervalued";

type Tab = "filtres" | "sous-cotees";

interface Filters {
  indices: string[];
  countries: { iso: string; label: string }[];
  sectors: string[];
  total: number;
}

const CAP_STEPS = [
  { label: "Toutes", value: 0 },
  { label: "≥ 1 Md €", value: 1e9 },
  { label: "≥ 10 Md €", value: 1e10 },
  { label: "≥ 50 Md €", value: 5e10 },
];

/** Screener sur l'univers européen, filtre PEA actif par défaut. */
export function Screener({
  onOpen,
  onGlossary,
}: {
  onOpen: (symbol: string) => void;
  onGlossary?: (id: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("filtres");
  const [filters, setFilters] = useState<Filters | null>(null);
  const [rows, setRows] = useState<ScreenerRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [peaOnly, setPeaOnly] = useState(true);
  const [index, setIndex] = useState("");
  const [country, setCountry] = useState("");
  const [sector, setSector] = useState("");
  const [minCap, setMinCap] = useState(0);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("market_cap_eur");
  const [descending, setDescending] = useState(true);

  useEffect(() => {
    api.screenerFilters().then(setFilters).catch(() => setFilters(null));
  }, []);

  useEffect(() => {
    let alive = true;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await api.screener({
          pea_only: peaOnly,
          index,
          country,
          sector,
          min_market_cap: minCap || undefined,
          q: query.trim() || undefined,
          sort,
          descending,
          limit: 200,
        });
        if (!alive) return;
        setRows(response.rows);
        setTotal(response.total);
        setError(null);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Erreur");
      } finally {
        if (alive) setLoading(false);
      }
    }, 180);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [peaOnly, index, country, sector, minCap, query, sort, descending]);

  const toggleSort = (key: string) => {
    if (sort === key) {
      setDescending((d) => !d);
    } else {
      setSort(key);
      // Le sens initial dépend de la colonne : un rendement ou une croissance
      // se lisent du plus élevé au plus faible, une échéance du plus proche au
      // plus lointain, un nom par ordre alphabétique.
      setDescending(
        ["market_cap_eur", "dividend_yield", "dividend_cagr"].includes(key),
      );
    }
  };

  const arrow = (key: string) => (sort === key ? (descending ? " ↓" : " ↑") : "");

  const tabs = (
    <div className="tabs" style={{ padding: 0, marginBottom: 4 }}>
      <button className={tab === "filtres" ? "active" : ""} onClick={() => setTab("filtres")}>
        Filtres
      </button>
      <button
        className={tab === "sous-cotees" ? "active" : ""}
        onClick={() => setTab("sous-cotees")}
      >
        Sous-cotées
      </button>
    </div>
  );

  if (tab === "sous-cotees") {
    return (
      <div className="stack">
        {tabs}
        <Undervalued onOpen={onOpen} />
      </div>
    );
  }

  return (
    <div className="stack">
      {tabs}
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Screener européen</span>
          <span className="note">
            {loading ? "…" : `${total} valeur${total > 1 ? "s" : ""} sur ${filters?.total ?? "—"}`}
          </span>
        </div>

        <div className="panel-body">
          <div className="row">
            <button
              className={`chip ${peaOnly ? "active" : ""}`}
              onClick={() => setPeaOnly((v) => !v)}
              title="Ne conserver que les titres dont le siège social est dans l'EEE"
            >
              {peaOnly ? "✓ " : ""}Éligibles PEA uniquement
            </button>

            <input
              placeholder="Nom ou ticker…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              style={{ minWidth: 180 }}
              aria-label="Filtre texte"
            />

            <select value={index} onChange={(event) => setIndex(event.target.value)} aria-label="Indice">
              <option value="">Tous les indices</option>
              {filters?.indices.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>

            <select value={country} onChange={(event) => setCountry(event.target.value)} aria-label="Pays du siège">
              <option value="">Tous les pays</option>
              {filters?.countries.map((item) => (
                <option key={item.iso} value={item.iso}>{item.label}</option>
              ))}
            </select>

            <select value={sector} onChange={(event) => setSector(event.target.value)} aria-label="Secteur">
              <option value="">Tous les secteurs</option>
              {filters?.sectors.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>

            <div className="chips">
              {CAP_STEPS.map((step) => (
                <button
                  key={step.value}
                  className={`chip ${minCap === step.value ? "active" : ""}`}
                  onClick={() => setMinCap(step.value)}
                >
                  {step.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {error && <div className="panel-body"><div className="callout error">{error}</div></div>}

        <div className="panel-body flush table-wrap">
          <table>
            <thead>
              <tr>
                <th className="sortable" onClick={() => toggleSort("symbol")}>Titre{arrow("symbol")}</th>
                <th className="sortable" onClick={() => toggleSort("name")}>Nom{arrow("name")}</th>
                <th>PEA</th>
                <th className="sortable" onClick={() => toggleSort("country_iso")}>Siège{arrow("country_iso")}</th>
                <th className="sortable" onClick={() => toggleSort("sector")}>Secteur{arrow("sector")}</th>
                <th className="right sortable" onClick={() => toggleSort("dividend_cagr")}>
                  Crois. div.{arrow("dividend_cagr")}
                </th>
                <th className="right sortable" onClick={() => toggleSort("dividend_yield")}>
                  Rendement{arrow("dividend_yield")}
                  <GlossaryHint id="rendement" onOpen={onGlossary} />
                </th>
                <th className="sortable" onClick={() => toggleSort("dividend_safety")}>
                  Sûreté{arrow("dividend_safety")}
                  <GlossaryHint id="surete-dividende" onOpen={onGlossary} />
                </th>
                <th className="sortable" onClick={() => toggleSort("next_ex_date")}>
                  Prochain détach.{arrow("next_ex_date")}
                </th>
                <th className="sortable" onClick={() => toggleSort("index")}>Indice{arrow("index")}</th>
                <th className="right sortable" onClick={() => toggleSort("market_cap_eur")}>
                  Capitalisation{arrow("market_cap_eur")}
                  <GlossaryHint id="capitalisation" onOpen={onGlossary} />
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.symbol} className="clickable" onClick={() => onOpen(row.symbol)}>
                  <td className="sym">{row.symbol}</td>
                  <td><span className="truncate">{row.name}</span></td>
                  <td><PeaBadge status={row.pea_status} reason={row.pea_reason} compact /></td>
                  <td className="dim">{row.country_label || "—"}</td>
                  <td className="dim">{row.sector || "—"}</td>
                  <td
                    className={`right num ${changeClass(row.dividend_cagr)}`}
                    title={
                      row.dividend_cagr_window
                        ? `Croissance annualisée sur ${row.dividend_cagr_window}, années civiles complètes et consécutives.`
                        : undefined
                    }
                  >
                    {pct(row.dividend_cagr, 1)}
                  </td>
                  {/* Un rendement de dividende n'est jamais négatif : le signe
                      que `pct` ajoute n'apporte rien et alourdit la colonne. */}
                  <td className="right num">{pct(row.dividend_yield, 2).replace("+", "")}</td>
                  <td>
                    <DividendBadge
                      safety={row.dividend_safety}
                      reason={row.dividend_safety_reason}
                    />
                  </td>
                  <td
                    className="faint num"
                    title={
                      row.next_ex_date
                        ? `Estimation d'après un rythme ${row.dividend_frequency}. Aucune source gratuite ne publie le calendrier à venir.`
                        : undefined
                    }
                  >
                    {row.next_ex_date ? `≈ ${date(row.next_ex_date)}` : "—"}
                  </td>
                  <td className="faint">{row.index || "—"}</td>
                  <td className="right num">{compact(row.market_cap_eur, "€")}</td>
                </tr>
              ))}
              {rows.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="faint" style={{ padding: 18, textAlign: "center" }}>
                    Aucune valeur ne correspond à ces critères.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="note">
        Les capitalisations sont converties en euros aux taux de référence de la
        Banque centrale européenne : les comparer en devise de cotation
        placerait mécaniquement les valeurs danoises et suédoises en tête.
        L'éligibilité PEA repose sur le pays du <strong>siège social</strong>, non
        sur la place de cotation.
      </div>
    </div>
  );
}
