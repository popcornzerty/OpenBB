import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type RankingResult, type RankingRow } from "../lib/api";
import { compact, num, pct, price } from "../lib/format";

/** Colonnes triables, avec le sens qui a du sens à la première sélection.
 *
 *  Cliquer sur « décote ajustée » doit montrer les plus sous-cotées d'abord,
 *  et sur « titre » l'ordre alphabétique : le sens initial dépend donc de la
 *  colonne, pas d'une règle unique. */
const SORTS = {
  symbol: { label: "Titre", initialDescending: false, align: "left" },
  name: { label: "Nom", initialDescending: false, align: "left" },
  market_cap_eur: { label: "Capitalisation", initialDescending: true, align: "right" },
  last_price: { label: "Cours", initialDescending: true, align: "right" },
  fair_value: { label: "Juste valeur", initialDescending: true, align: "right" },
  gap: { label: "Écart brut", initialDescending: false, align: "right" },
  adjusted_discount: { label: "Décote ajustée", initialDescending: true, align: "right" },
  reliability: { label: "Fiabilité", initialDescending: true, align: "right" },
  sector: { label: "Secteur", initialDescending: false, align: "left" },
} as const;

type SortKey = keyof typeof SORTS;

/** Classement des sociétés, de la plus à la moins sous-cotée.
 *
 *  Le classement porte sur la **décote ajustée** : l'écart cours/juste valeur
 *  pondéré par la fiabilité de l'estimation. Sans cette pondération, les
 *  décotes les plus spectaculaires — qui trahissent souvent un multiple
 *  déformé par un exercice atypique — occuperaient la tête du tableau.
 *  L'écart brut reste affiché à côté : le score ordonne, il ne masque rien. */
export function Undervalued({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [result, setResult] = useState<RankingResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("adjusted_discount");
  const [descending, setDescending] = useState(true);
  const timer = useRef<number | null>(null);

  const poll = useCallback(async () => {
    try {
      const data = await api.ranking();
      setResult(data);
      setError(null);
      if (data.state !== "running" && timer.current) {
        window.clearInterval(timer.current);
        timer.current = null;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  }, []);

  useEffect(() => {
    poll();
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [poll]);

  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      await api.startRanking(true);
      await poll();
      if (!timer.current) timer.current = window.setInterval(poll, 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setStarting(false);
    }
  };

  const running = result?.state === "running";

  const toggleSort = (key: SortKey) => {
    if (sort === key) {
      setDescending((current) => !current);
    } else {
      setSort(key);
      setDescending(SORTS[key].initialDescending);
    }
  };

  const rows = useMemo(() => {
    const source = result?.rows ?? [];
    // Les valeurs manquantes ferment toujours la marche, quel que soit le sens
    // du tri : les inclure dans la comparaison les ferait remonter en tête dès
    // qu'on trie en décroissant, ce qui mettrait les lignes les moins
    // renseignées en avant — l'inverse de l'intention.
    const missing = (row: RankingRow) => {
      const value = row[sort];
      return value === null || value === undefined || value === "";
    };
    const present = source.filter((row) => !missing(row));
    const absent = source.filter(missing);

    present.sort((a, b) => {
      const left = a[sort];
      const right = b[sort];
      const comparison =
        typeof left === "string" && typeof right === "string"
          ? left.localeCompare(right, "fr")
          : Number(left) - Number(right);
      return descending ? -comparison : comparison;
    });

    return [...present, ...absent];
  }, [result, sort, descending]);

  const arrow = (key: SortKey) => (sort === key ? (descending ? " ↓" : " ↑") : "");

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Sociétés sous-cotées</span>
          <span className="spacer" style={{ flex: 1 }} />
          {result && result.state !== "idle" && (
            <span className="note">
              {result.computed} valorisées · {result.skipped} sans estimation
              {result.elapsed_seconds !== null && ` · ${Math.round(result.elapsed_seconds)} s`}
            </span>
          )}
          <button className="chip" onClick={start} disabled={running || starting}>
            {running ? "Calcul en cours…" : rows.length > 0 ? "Recalculer" : "Calculer"}
          </button>
        </div>

        <div className="panel-body">
          {running && (
            <div className="stack" style={{ gap: 6 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="note">
                  {result!.done} / {result!.total} titres analysés
                </span>
                <span className="note num">{pct(result!.progress, 0).replace("+", "")}</span>
              </div>
              <div className="bar">
                <span style={{ width: `${(result!.progress * 100).toFixed(1)}%` }} />
              </div>
              <div className="note">
                Comptez un quart d'heure à froid : la source de données bride les
                requêtes, c'est elle qui fixe le rythme. Le résultat reste ensuite
                valable 24 heures, et un recalcul dans cette fenêtre est quasi immédiat.
              </div>
            </div>
          )}

          {!running && rows.length === 0 && !error && (
            <div className="callout">
              Lancez le calcul pour classer les {result?.total || "375"} valeurs éligibles
              PEA de la plus à la moins sous-cotée. Comptez un quart d'heure la première
              fois — rien ne part vers la source de données sans votre clic.
            </div>
          )}

          {error && <div className="callout error">{error}</div>}
        </div>

        {rows.length > 0 && (
          <div className="panel-body flush table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 40 }}>#</th>
                  {(Object.keys(SORTS) as SortKey[]).map((key) => (
                    <th
                      key={key}
                      className={`sortable ${SORTS[key].align === "right" ? "right" : ""}`}
                      onClick={() => toggleSort(key)}
                      title="Trier sur cette colonne"
                    >
                      {SORTS[key].label}
                      {arrow(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr
                    key={row.symbol}
                    className="clickable"
                    onClick={() => onOpen(row.symbol)}
                    onMouseEnter={() => setDetail(describe(row))}
                    onMouseLeave={() => setDetail(null)}
                  >
                    <td className="faint num">{index + 1}</td>
                    <td className="sym">{row.symbol}</td>
                    <td>
                      <span className="truncate dim">{row.name}</span>
                    </td>
                    <td className="right num dim">{compact(row.market_cap_eur, "€")}</td>
                    <td className="right num">{price(row.last_price, row.currency)}</td>
                    <td className="right num dim">{price(row.fair_value, row.currency)}</td>
                    <td className={`right num ${(row.gap ?? 0) < 0 ? "up" : "down"}`}>
                      {pct(row.gap)}
                    </td>
                    <td
                      className={`right num ${(row.adjusted_discount ?? 0) > 0 ? "up" : "down"}`}
                      style={{ fontWeight: 600 }}
                    >
                      {pct(row.adjusted_discount)}
                    </td>
                    <td className="right num">
                      <div className="row" style={{ justifyContent: "flex-end", gap: 7 }}>
                        <span className="faint">{num(row.reliability, 2)}</span>
                        <div className="bar" style={{ width: 42 }}>
                          <span style={{ width: `${row.reliability * 100}%` }} />
                        </div>
                      </div>
                    </td>
                    <td className="faint">{row.sector || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {detail && <div className="callout">{detail}</div>}

      {result?.method && (
        <div className="note">
          <strong>Comment lire ce classement.</strong> {result.method} Une décote ajustée
          de 20 % peut donc venir d'un écart de 20 % pleinement fiable comme d'un écart de
          40 % à moitié fiable — la colonne « écart brut » vous dit lequel.{" "}
          {result.skipped > 0 && (
            <>
              {result.skipped} valeurs n'ont pas d'estimation exploitable : fondamentaux
              insuffisants, exercices déficitaires, ou société financière sans multiple
              retenu. Elles ferment la marche plutôt que d'être écartées en silence.
            </>
          )}
        </div>
      )}

      <div className="note">
        Ces estimations reposent sur cinq exercices publiés au maximum, plafond des
        sources gratuites. Elles ne constituent pas un conseil en investissement, et une
        décote peut refléter une difficulté réelle de l'entreprise autant qu'une
        opportunité.
      </div>
    </div>
  );
}

/** Phrase explicative d'une ligne, affichée au survol. */
function describe(row: RankingRow): string {
  const parts = row.reliability_parts;
  return (
    `${row.symbol} — ${row.verdict}. Fiabilité ${num(row.reliability, 2)} : ` +
    `${row.periods_used} exercices (facteur ${num(parts.periods, 2)}), ` +
    `${row.components} multiples retenus (facteur ${num(parts.breadth, 2)}), ` +
    `dispersion moyenne ${num(parts.weighted_dispersion, 2)} (facteur ${num(parts.stability, 2)}).`
  );
}
