import { useEffect, useMemo, useState } from "react";
import { api, type Valuation as ValuationData } from "../lib/api";
import { GlossaryHint } from "../components/GlossaryHint";
import { Chart, type ChartSeries } from "../components/Chart";
import { DividendBadge } from "../components/DividendBadge";
import { FinancialTable } from "../components/FinancialTable";
import { MultipleHistoryChart } from "../components/MultipleHistoryChart";
import { date, num, pct, price } from "../lib/format";

const VERDICT_COLOR: Record<string, string> = {
  "sous-évalué": "var(--up)",
  "surévalué": "var(--down)",
  "correctement valorisé": "var(--text-dim)",
  "indeterminé": "var(--text-faint)",
};

/** Courbe de juste valeur et son mode d'emploi.
 *
 *  Tout ce qui fabrique le chiffre est exposé : multiples médians, poids,
 *  composantes écartées et pourquoi, niveau de confiance. Un modèle de
 *  valorisation dont on ne peut pas inspecter les ressorts ne vaut rien. */
export function Valuation({
  symbol,
  onGlossary,
}: {
  symbol: string;
  onGlossary?: (id: string) => void;
}) {
  const [data, setData] = useState<ValuationData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api.valuation(symbol).then(setData).catch((err) => setError(err.message));
  }, [symbol]);

  const series = useMemo<ChartSeries[]>(() => {
    if (!data) return [];
    const { series: s, projection } = data;
    const out: ChartSeries[] = [
      {
        id: "price",
        label: "Cours",
        color: "#5aa9ff",
        data: s.dates.map((d, i) => ({ time: d, value: s.price[i] })),
      },
      {
        id: "fair",
        label: "Juste valeur",
        color: "#ffb454",
        width: 3,
        data: s.dates.map((d, i) => ({ time: d, value: s.fair_value[i] })),
      },
    ];
    if (projection.dates.length > 0) {
      // La projection reprend au dernier point réel pour éviter un saut visuel.
      const lastDate = s.dates[s.dates.length - 1];
      const lastValue = s.fair_value[s.fair_value.length - 1];
      out.push({
        id: "projection",
        label: "Prolongement",
        color: "#8a6d3b",
        dashed: true,
        width: 2,
        data: [
          { time: lastDate, value: lastValue },
          ...projection.dates.map((d, i) => ({ time: d, value: projection.fair_value[i] })),
        ],
      });
    }
    return out;
  }, [data]);

  if (error) {
    return (
      <div className="stack">
        <div className="callout error">
          <strong>Juste valeur non calculable pour {symbol}.</strong>
          <div style={{ marginTop: 5 }}>{error}</div>
        </div>
      </div>
    );
  }

  if (!data) return <div className="spinner">Calcul de la juste valeur de {symbol}…</div>;

  const q = data.quality;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Juste valeur — {data.name}</span>
          <span className="spacer" style={{ flex: 1 }} />
          <span className="badge plain">
            Fenêtre {data.window_years} ans
            <GlossaryHint id="fenetre-calcul" onOpen={onGlossary} />
          </span>
          <span className="badge plain">
            Confiance {data.confidence.level}
            <GlossaryHint id="confiance-faible" onOpen={onGlossary} />
          </span>
        </div>

        <div className="panel-body">
          <div className="kpis" style={{ marginBottom: 13 }}>
            <div className="kpi">
              <div className="label">Cours</div>
              <div className="value">{price(data.last_price, data.currency)}</div>
            </div>
            <div className="kpi">
              <div className="label">
                Juste valeur estimée
                <GlossaryHint id="juste-valeur" onOpen={onGlossary} />
              </div>
              <div className="value" style={{ color: "var(--amber)" }}>
                {price(data.fair_value, data.currency)}
              </div>
            </div>
            <div className="kpi">
              <div className="label">
                Écart
                <GlossaryHint id="prime-decote" onOpen={onGlossary} />
              </div>
              <div
                className="value"
                style={{ color: data.gap !== null && data.gap < 0 ? "var(--up)" : "var(--down)" }}
              >
                {pct(data.gap)}
              </div>
            </div>
            <div className="kpi">
              <div className="label">Verdict</div>
              <div className="value" style={{ fontSize: 13, color: VERDICT_COLOR[data.verdict] }}>
                {data.verdict}
              </div>
            </div>
            <div className="kpi">
              <div className="label">
                Note qualité
                <GlossaryHint id="note-qualite" onOpen={onGlossary} />
              </div>
              <div className="value">{q ? num(q.score, 1) : "—"}</div>
            </div>
            <div className="kpi">
              <div className="label">
                Prime / décote
                <GlossaryHint id="prime-decote" onOpen={onGlossary} />
              </div>
              <div className="value">{pct(data.quality_factor - 1)}</div>
            </div>
          </div>

          <Chart series={series} height={340} />
        </div>
      </div>

      {data.confidence.caveats.length > 0 && (
        <div className="callout warn">
          <strong>À savoir avant de s'y fier</strong>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {data.confidence.caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}
            {data.backfilled_until && (
              <li>
                Avant le {date(data.backfilled_until)}, la courbe s'appuie sur les
                comptes publiés les plus anciens disponibles.
              </li>
            )}
          </ul>
        </div>
      )}

      {data.dividend && data.dividend.safety !== "aucun" && (
        <div className="panel">
          <div className="panel-head">
            <span className="panel-title">Dividende</span>
            <span className="spacer" style={{ flex: 1 }} />
            <DividendBadge
              safety={data.dividend.safety}
              reason={data.dividend.safety_reason}
            />
          </div>
          <div className="panel-body">
            <div className="kpis">
              <div className="kpi">
                <div className="label">Rendement</div>
                <div className="value">
                  {pct(data.dividend.yield, 2).replace("+", "")}
                </div>
              </div>
              <div className="kpi">
                <div className="label">
                  Croissance annualisée
                  {data.dividend.growth_window && ` · ${data.dividend.growth_window}`}
                </div>
                <div
                  className={`value ${(data.dividend.growth ?? 0) >= 0 ? "up" : "down"}`}
                >
                  {pct(data.dividend.growth, 1)}
                </div>
              </div>
              <div className="kpi">
                <div className="label">Taux de distribution</div>
                <div className="value">
                  {pct(data.dividend.payout_ratio, 0).replace("+", "")}
                </div>
              </div>
              <div className="kpi">
                <div className="label">Flux libre absorbé</div>
                <div className="value">
                  {pct(data.dividend.fcf_coverage, 0).replace("+", "")}
                </div>
              </div>
              <div className="kpi">
                <div className="label">Prochain détachement</div>
                <div className="value" style={{ fontSize: 13 }}>
                  {data.dividend.next_ex_date
                    ? `≈ ${date(data.dividend.next_ex_date)}`
                    : "—"}
                </div>
              </div>
            </div>
            <div className="note" style={{ marginTop: 10 }}>
              {data.dividend.safety_reason} La croissance porte sur des années civiles
              complètes et consécutives ; la date de détachement est estimée d'après le
              rythme observé, aucune source gratuite ne publiant le calendrier à venir.
            </div>
          </div>
        </div>
      )}

      {data.per_history && <MultipleHistoryChart history={data.per_history} />}

      {data.tables && data.tables.columns.length > 0 && (
        <>
          <FinancialTable
            label="Compte de résultat et estimations"
            columns={data.tables.columns}
            rows={data.tables.income_rows}
            currency={data.currency}
          />
          <FinancialTable
            label="Valorisation par exercice"
            columns={data.tables.columns}
            rows={data.tables.valuation_rows}
            currency={data.currency}
          />

          {(data.tables.price_target.mean ?? null) !== null && (
            <div className="panel">
              <div className="panel-head">
                <span className="panel-title">Objectif de cours du consensus</span>
                <GlossaryHint id="consensus" onOpen={onGlossary} />
              </div>
              <div className="panel-body">
                <div className="kpis">
                  <div className="kpi">
                    <div className="label">Objectif moyen</div>
                    <div className="value" style={{ color: "var(--amber)" }}>
                      {price(data.tables.price_target.mean ?? null, data.currency)}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="label">Médian</div>
                    <div className="value">
                      {price(data.tables.price_target.median ?? null, data.currency)}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="label">Fourchette</div>
                    <div className="value" style={{ fontSize: 13 }}>
                      {price(data.tables.price_target.low ?? null, data.currency)} –{" "}
                      {price(data.tables.price_target.high ?? null, data.currency)}
                    </div>
                  </div>
                  <div className="kpi">
                    <div className="label">Potentiel</div>
                    <div
                      className={`value ${
                        (data.tables.price_target.mean ?? 0) >= data.last_price ? "up" : "down"
                      }`}
                    >
                      {pct(
                        ((data.tables.price_target.mean ?? data.last_price) - data.last_price) /
                          data.last_price,
                        1,
                      )}
                    </div>
                  </div>
                </div>
                <div className="note" style={{ marginTop: 10 }}>
                  Objectifs publiés par les bureaux d'analyse, sans rapport avec la juste
                  valeur calculée plus haut : ils reflètent un consensus de marché, pas un
                  modèle. Les deux peuvent diverger, et cette divergence est en soi une
                  information.
                </div>
              </div>
            </div>
          )}

          {data.tables.notes.length > 0 && (
            <div className="callout warn">
              <strong>Limites des tableaux</strong>
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {data.tables.notes.map((note, i) => <li key={i}>{note}</li>)}
                <li>
                  La source gratuite ne publie que quatre exercices et deux années
                  estimées. Les multiples historiques sont calculés au cours de clôture
                  de chaque exercice, les multiples estimés au cours actuel.
                </li>
              </ul>
            </div>
          )}
        </>
      )}

      <div className="grid2">
        <div className="panel">
          <div className="panel-head"><span className="panel-title">Composantes du calcul</span></div>
          <div className="panel-body flush table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Multiple</th>
                  <th className="right">Médiane</th>
                  <th className="right">Actuel</th>
                  <th className="right">Dispersion</th>
                  <th className="right">Poids</th>
                </tr>
              </thead>
              <tbody>
                {data.components.map((component) => (
                  <tr key={component.key}>
                    <td>{component.label}</td>
                    <td className="right num">{num(component.median_multiple)}</td>
                    <td className="right num dim">{num(component.current_multiple)}</td>
                    <td className="right num faint">{num(component.dispersion, 2)}</td>
                    <td className="right num">
                      <div className="row" style={{ justifyContent: "flex-end", gap: 7 }}>
                        <span>{pct(component.weight, 1).replace("+", "")}</span>
                        <div className="bar" style={{ width: 46 }}>
                          <span style={{ width: `${component.weight * 100}%` }} />
                        </div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.excluded_components.length > 0 && (
            <div className="panel-body">
              <div className="note">
                <strong>Composantes écartées</strong>
                <ul style={{ margin: "5px 0 0", paddingLeft: 18 }}>
                  {data.excluded_components.map((item) => (
                    <li key={item.key}>{item.label} — {item.reason}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-head"><span className="panel-title">Note de qualité</span></div>
          <div className="panel-body">
            {q ? (
              <div className="stack" style={{ gap: 11 }}>
                {q.axes.map((axis) => (
                  <div key={axis.key}>
                    <div className="row" style={{ justifyContent: "space-between", gap: 8 }}>
                      <span>{axis.label}</span>
                      <span className="num dim">
                        {num(axis.score, 0)} / 100 · poids {num(axis.weight * 100, 0)} %
                      </span>
                    </div>
                    <div className="bar" style={{ marginTop: 4 }}>
                      <span style={{ width: `${axis.score}%` }} />
                    </div>
                    <div className="note" style={{ marginTop: 3 }}>{axis.detail}</div>
                  </div>
                ))}
                <div className="note" style={{ borderTop: "1px solid var(--border-soft)", paddingTop: 9 }}>
                  {q.method}
                </div>
              </div>
            ) : (
              <div className="faint">Note indisponible.</div>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head"><span className="panel-title">Méthode</span></div>
        <div className="panel-body">
          <div className="note">{data.method}</div>
          <div className="note" style={{ marginTop: 7 }}>{data.projection.note}</div>
          <div className="note" style={{ marginTop: 7 }}>
            Exercices utilisés : {data.periods_used.map((p) => p.period_ending.slice(0, 4)).join(", ")}.
            Chaque exercice n'est pris en compte qu'à partir de sa date de publication
            estimée, pour qu'aucun calcul n'utilise une information qui n'était pas
            encore connue du marché.
          </div>
        </div>
      </div>
    </div>
  );
}
