import { useMemo } from "react";
import type { MultipleHistory } from "../lib/api";
import { Chart, type ChartSeries } from "./Chart";
import { date, num, pct } from "../lib/format";

/** Évolution d'un multiple face à sa moyenne historique.
 *
 *  Un PER de 21 ne dit rien seul. Ce qui renseigne, c'est l'écart à ce que le
 *  titre s'est habituellement payé — d'où la moyenne, et la bande d'un
 *  écart-type qui montre ce qui relève de la respiration normale. */
export function MultipleHistoryChart({ history }: { history: MultipleHistory }) {
  const series = useMemo<ChartSeries[]>(() => {
    const points = history.series;
    if (points.length === 0) return [];

    // Les repères horizontaux sont tracés comme des séries constantes sur
    // toute l'étendue : lightweight-charts n'expose pas de ligne libre.
    const flat = (value: number | null) =>
      value === null
        ? []
        : points.map((point) => ({ time: point.date, value }));

    const out: ChartSeries[] = [
      {
        id: "multiple",
        label: history.label,
        color: "#5aa9ff",
        width: 2,
        data: points.map((point) => ({ time: point.date, value: point.value })),
      },
      {
        id: "average",
        label: "Moyenne",
        color: "#ffb454",
        width: 2,
        data: flat(history.average),
      },
    ];

    if (history.band_low !== null && history.band_high !== null) {
      out.push(
        { id: "low", label: "−1 écart-type", color: "#5c4a2a", dashed: true, width: 1,
          data: flat(history.band_low) },
        { id: "high", label: "+1 écart-type", color: "#5c4a2a", dashed: true, width: 1,
          data: flat(history.band_high) },
      );
    }
    return out;
  }, [history]);

  const gap = history.gap_to_average;
  // Payer moins cher qu'à l'accoutumée n'est pas une bonne nouvelle en soi,
  // mais c'est le sens dans lequel un investisseur lit l'écart.
  const tone = gap <= 0 ? "up" : "down";

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">Évolution du {history.label}</span>
        <span className="spacer" style={{ flex: 1 }} />
        <span className="badge plain">{num(history.years, 1)} ans affichés</span>
        <span className="badge plain">
          moyenne sur {num(history.reference_years, 1)} ans
        </span>
      </div>
      <div className="panel-body">
        <div className="kpis" style={{ marginBottom: 13 }}>
          <div className="kpi">
            <div className="label">{history.label} actuel</div>
            <div className="value">{num(history.current, 1)}×</div>
          </div>
          <div className="kpi">
            <div className="label">Moyenne historique</div>
            <div className="value" style={{ color: "var(--amber)" }}>
              {num(history.average, 1)}×
            </div>
          </div>
          <div className="kpi">
            <div className="label">Médiane</div>
            <div className="value">{num(history.median, 1)}×</div>
          </div>
          <div className="kpi">
            <div className="label">Écart à la moyenne</div>
            <div className={`value ${tone}`}>{pct(gap, 1)}</div>
          </div>
          <div className="kpi">
            <div className="label">Amplitude observée</div>
            <div className="value" style={{ fontSize: 13 }}>
              {num(history.min, 1)}× – {num(history.max, 1)}×
            </div>
          </div>
        </div>

        <Chart series={series} height={260} priceFormat={{ precision: 1, minMove: 0.1 }} />

        <div className="note" style={{ marginTop: 10 }}>
          Le {history.label} rapporte le cours au bénéfice par action du moment, les
          comptes n'étant pris en compte qu'à partir de leur date de publication.{" "}
          {history.stats_backfilled ? (
            <>
              La moyenne s'appuie en partie sur une période antérieure à la publication
              des comptes les plus anciens disponibles : à considérer comme un ordre de
              grandeur.
            </>
          ) : (
            <>
              La moyenne ne porte que sur la période réellement adossée à des comptes
              publiés, depuis le {date(history.reference_from)} — soit{" "}
              {num(history.reference_years, 1)} ans, moins que les{" "}
              {num(history.years, 1)} ans affichés.
              {history.backfilled_until && (
                <>
                  {" "}Avant le {date(history.backfilled_until)}, la courbe applique
                  rétroactivement les comptes les plus anciens connus.
                </>
              )}
            </>
          )}{" "}
          La bande figure un écart-type de part et d'autre de la moyenne.
        </div>
      </div>
    </div>
  );
}
