import type { TableColumn, TableRow } from "../lib/api";
import { compact, num, pct } from "../lib/format";

/** Tableau par exercice : une ligne par agrégat, une colonne par année.
 *
 *  Les exercices estimés sont visuellement distincts des exercices publiés.
 *  Confondre un chiffre constaté et un consensus d'analystes serait la pire
 *  erreur que puisse commettre cet écran. */
export function FinancialTable({
  columns,
  rows,
  currency,
  label,
}: {
  columns: TableColumn[];
  rows: TableRow[];
  currency: string | null;
  label: string;
}) {
  if (columns.length === 0) return null;

  const symbol = currency === "EUR" ? " €" : currency ? ` ${currency}` : "";

  const format = (value: number | null, unit: TableRow["unit"], key: string) => {
    if (value === null) return "—";
    switch (unit) {
      case "percent":
        // Le signe explicite n'a de sens que sur une variation. Une marge de
        // « +33,7 % » se lit comme une progression qu'elle n'est pas.
        return key.includes("growth") ? pct(value, 1) : pct(value, 1).replace("+", "");
      case "ratio":
        return `${num(value, 1)}×`;
      case "per_share":
        // Un bénéfice ou un dividende par action se lit au centime ; les trois
        // décimales des petits cours n'ont pas cours ici.
        return `${num(value, 2)}${symbol}`;
      case "count":
        return compact(value);
      default:
        return compact(value, currency ?? "");
    }
  };

  // Une marge ou une croissance se lit mieux colorée ; un multiple ou un
  // encours, non — un PER élevé n'est ni bon ni mauvais dans l'absolu.
  const tone = (value: number | null, unit: TableRow["unit"], key: string) => {
    if (value === null || unit !== "percent") return "";
    if (!key.includes("growth")) return "";
    return value >= 0 ? "up" : "down";
  };

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="panel-title">{label}</span>
        <span className="spacer" style={{ flex: 1 }} />
        {columns.some((c) => c.estimate) && (
          <span className="note">colonnes « e » : consensus des analystes</span>
        )}
      </div>
      <div className="panel-body flush table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ minWidth: 210 }} />
              {columns.map((column) => (
                <th
                  key={column.label}
                  className="right"
                  style={{
                    color: column.estimate ? "var(--amber)" : undefined,
                    fontStyle: column.estimate ? "italic" : undefined,
                  }}
                  title={
                    column.estimate
                      ? `Consensus${column.analysts ? ` de ${column.analysts} analystes` : ""}, ` +
                        `multiples au cours actuel`
                      : `Exercice clos le ${column.period_ending}, ` +
                        `multiples au cours de clôture`
                  }
                >
                  {column.label}
                  {column.thin && <span className="faint" title="Moins de trois analystes"> ⚠</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td title={row.note || undefined}>
                  {row.label}
                  {row.note && <span className="faint"> ⓘ</span>}
                </td>
                {row.values.map((value, index) => (
                  <td
                    key={columns[index]?.label ?? index}
                    className={`right num ${tone(value, row.unit, row.key)}`}
                    style={{
                      fontStyle: columns[index]?.estimate ? "italic" : undefined,
                      opacity: columns[index]?.estimate ? 0.92 : undefined,
                    }}
                  >
                    {format(value, row.unit, row.key)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
