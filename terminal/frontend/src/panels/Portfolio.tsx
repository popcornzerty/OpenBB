import { useEffect, useState } from "react";
import { api, type PortfolioRow, type PortfolioSummary } from "../lib/api";
import { PeaBadge } from "../components/PeaBadge";
import { changeClass, compact, date, money, num, pct } from "../lib/format";

/** Portefeuille tenu dans Wealthfolio, relu ici en lecture seule.
 *
 *  Le terminal ne gère pas de portefeuille — c'est le rôle de Wealthfolio.
 *  Il applique simplement à vos positions réelles ce qu'il sait faire :
 *  cotations, verdict PEA et, en un clic, sa courbe de juste valeur. */
export function Portfolio({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [rows, setRows] = useState<PortfolioRow[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const status = await api.portfolioStatus();
        if (!alive) return;
        if (!status.available) {
          setHint(status.hint);
          setError("Portefeuille Wealthfolio introuvable.");
          return;
        }
        const response = await api.portfolio();
        if (!alive) return;
        setRows(response.rows);
        setSummary(response.summary);
        setSource(response.source);
        setError(null);
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "Erreur");
      } finally {
        if (alive) setLoading(false);
      }
    };
    load();
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <div className="spinner">Lecture du portefeuille Wealthfolio…</div>;

  if (error) {
    return (
      <div className="stack">
        <div className="callout error">
          <strong>{error}</strong>
          {hint && <div style={{ marginTop: 5 }}>{hint}</div>}
        </div>
      </div>
    );
  }

  const usesFallback = rows.some((row) => row.price_source === "prev_close");

  return (
    <div className="stack">
      {summary && (
        <div className="kpis">
          <Kpi label="Valeur" value={money(summary.total_value, "EUR")} />
          <Kpi label="Prix de revient" value={money(summary.total_cost, "EUR")} />
          <Kpi
            label="Plus-value latente"
            value={money(summary.total_gain, "EUR")}
            tone={(summary.total_gain ?? 0) >= 0 ? "up" : "down"}
          />
          <Kpi
            label="Performance"
            value={pct(summary.total_gain_percent)}
            tone={(summary.total_gain_percent ?? 0) >= 0 ? "up" : "down"}
          />
          <Kpi label="Lignes" value={String(summary.positions)} />
          <Kpi
            label="PEA confirmé"
            value={pct(summary.confirmed_pea_share, 1).replace("+", "")}
          />
        </div>
      )}

      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Positions</span>
          <span className="spacer" style={{ flex: 1 }} />
          <span className="note">
            {source} · instantané du {date(summary?.snapshot_date)}
          </span>
        </div>
        <div className="panel-body flush table-wrap">
          <table>
            <thead>
              <tr>
                <th>Titre</th>
                <th>Nom</th>
                <th>PEA</th>
                <th className="right">Qté</th>
                <th className="right">PRU</th>
                <th className="right">Cours</th>
                <th className="right">Valeur</th>
                <th className="right">+/- value</th>
                <th className="right">%</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.symbol}
                  className="clickable"
                  onClick={() => onOpen(row.symbol)}
                  title="Ouvrir la fiche société"
                >
                  <td className="sym">{row.symbol}</td>
                  <td>
                    <span className="truncate dim">{row.name}</span>
                  </td>
                  <td>
                    <PeaBadge status={row.pea_status} reason={row.pea_reason} compact />
                  </td>
                  <td className="right num">{compact(row.quantity)}</td>
                  <td className="right num dim">{num(row.average_cost)}</td>
                  <td className="right num">
                    {num(row.price)}
                    {row.price_source === "prev_close" && (
                      <span className="faint" title="Clôture précédente : ce titre ne remonte pas de dernier cours">
                        {" "}*
                      </span>
                    )}
                  </td>
                  <td className="right num">{money(row.market_value, "EUR")}</td>
                  <td className={`right num ${changeClass(row.gain)}`}>
                    {money(row.gain, "EUR")}
                  </td>
                  <td className={`right num ${changeClass(row.gain_percent)}`}>
                    {pct(row.gain_percent)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="note">
        Le portefeuille est lu <strong>en lecture seule</strong> dans la base de
        Wealthfolio : le terminal ne le modifie jamais. Ajoutez ou retirez une ligne
        dans Wealthfolio, elle apparaît ici au rafraîchissement.
        {usesFallback && (
          <>
            {" "}Les lignes marquées d'un astérisque sont valorisées à la clôture
            précédente : ces instruments — des ETF le plus souvent — ne remontent pas
            de dernier cours.
          </>
        )}{" "}
        La part « PEA confirmé » exclut délibérément les lignes au statut indéterminé.
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
}) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
    </div>
  );
}
