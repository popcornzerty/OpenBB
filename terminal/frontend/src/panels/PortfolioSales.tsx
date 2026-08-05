import { useCallback, useEffect, useState } from "react";
import { api, type RealizedTotals, type Sale } from "../lib/api";
import { changeClass, compact, date, money, num, pct, price } from "../lib/format";

type SortKey = "closed_at" | "gain" | "gain_percent" | "total_return" | "holding_days";

/** Historique des cessions et plus-values réalisées.
 *
 *  Une ligne vendue reste un résultat du portefeuille : sans cette trace, la
 *  performance affichée ne retiendrait que ce qui n'a pas encore été arbitré. */
export function PortfolioSales({
  onChanged,
  onOpen,
}: {
  onChanged: () => void;
  onOpen: (symbol: string) => void;
}) {
  const [sales, setSales] = useState<Sale[]>([]);
  const [totals, setTotals] = useState<RealizedTotals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>("closed_at");
  const [asc, setAsc] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.realized();
      setSales(data.sales);
      setTotals(data.totals);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const cancel = async (sale: Sale) => {
    try {
      await api.cancelSale(sale.id);
      setNotice(
        `Cession de ${sale.symbol} annulée : ${sale.quantity} titre(s) remis en portefeuille.`,
      );
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  const toggle = (key: SortKey) => {
    if (key === sort) setAsc((value) => !value);
    else {
      setSort(key);
      // Les dates les plus récentes et les plus gros gains d'abord : c'est ce
      // qu'on cherche en ouvrant l'écran.
      setAsc(false);
    }
  };

  const sorted = [...sales].sort((a, b) => {
    const pick = (s: Sale) => (sort === "closed_at" ? s.closed_at : s[sort]);
    const left = pick(a);
    const right = pick(b);
    // Une durée ou un pourcentage inconnu se range en fin de liste, quel que
    // soit le sens du tri.
    if (left === null) return 1;
    if (right === null) return -1;
    if (left === right) return 0;
    return (left < right ? -1 : 1) * (asc ? 1 : -1);
  });

  if (loading && sales.length === 0) {
    return <div className="spinner">Chargement des cessions…</div>;
  }

  if (error) return <div className="callout error">{error}</div>;

  if (sales.length === 0) {
    return (
      <div className="stack">
        {notice && <div className="callout">{notice}</div>}
        <div className="callout">
          Aucune cession enregistrée. Le bouton <strong>Vendre</strong> d'une ligne
          enregistre la plus-value réalisée et fige les dividendes déjà perçus, que la
          disparition de la position effacerait autrement.
        </div>
      </div>
    );
  }

  const Head = ({ label, k, right }: { label: string; k: SortKey; right?: boolean }) => (
    <th
      className={right ? "right sortable" : "sortable"}
      onClick={() => toggle(k)}
      style={{ cursor: "pointer" }}
      title="Trier"
    >
      {label}
      {sort === k && <span className="faint">{asc ? " ▲" : " ▼"}</span>}
    </th>
  );

  return (
    <div className="stack">
      {notice && <div className="callout">{notice}</div>}

      {totals && (
        <div className="kpis">
          <Kpi label="Cessions" value={String(totals.count)} />
          <Kpi label="Capital engagé" value={money(totals.cost_basis, "EUR")} />
          <Kpi label="Produit des ventes" value={money(totals.proceeds, "EUR")} />
          <Kpi
            label="Plus-value réalisée"
            value={money(totals.gain, "EUR")}
            tone={changeClass(totals.gain) as "up" | "down" | undefined}
          />
          <Kpi
            label="Rendement des opérations"
            value={pct(totals.gain_percent, 2)}
            tone={changeClass(totals.gain_percent) as "up" | "down" | undefined}
          />
          <Kpi label="Dividendes encaissés" value={money(totals.dividends, "EUR")} />
          <Kpi
            label="Rendement total"
            value={money(totals.total_return, "EUR")}
            tone={changeClass(totals.total_return) as "up" | "down" | undefined}
          />
          <Kpi
            label="Opérations gagnantes"
            value={pct(totals.win_rate, 0).replace("+", "")}
          />
        </div>
      )}

      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Cessions</span>
        </div>
        <div className="panel-body flush table-wrap">
          <table>
            <thead>
              <tr>
                <Head label="Vendue le" k="closed_at" />
                <th>Titre</th>
                <th className="right">Qté</th>
                <th className="right">PRU</th>
                <th className="right">Prix de vente</th>
                <th className="right">Produit</th>
                <Head label="+/- value" k="gain" right />
                <Head label="%" k="gain_percent" right />
                <th className="right">Dividendes</th>
                <Head label="Total" k="total_return" right />
                <Head label="Détention" k="holding_days" right />
                <th />
              </tr>
            </thead>
            <tbody>
              {sorted.map((sale) => (
                <tr key={sale.id}>
                  <td className="num">{date(sale.closed_at)}</td>
                  <td>
                    <button
                      className="link sym"
                      onClick={() => onOpen(sale.symbol)}
                      title={sale.note || sale.label || sale.symbol}
                    >
                      {sale.symbol}
                    </button>
                  </td>
                  <td className="right num">{compact(sale.quantity)}</td>
                  <td className="right num dim">{num(sale.average_cost)}</td>
                  <td className="right num">{price(sale.sale_price, sale.currency)}</td>
                  <td className="right num dim">{money(sale.proceeds, "EUR")}</td>
                  <td className={`right num ${changeClass(sale.gain)}`}>
                    {money(sale.gain, "EUR")}
                  </td>
                  <td className={`right num ${changeClass(sale.gain_percent)}`}>
                    {pct(sale.gain_percent)}
                  </td>
                  <td className="right num dim">
                    {sale.dividends ? money(sale.dividends, "EUR") : "—"}
                  </td>
                  <td className={`right num ${changeClass(sale.total_return)}`}>
                    {money(sale.total_return, "EUR")}
                  </td>
                  <td className="right num faint">
                    {sale.holding_days === null
                      ? "—"
                      : sale.holding_days >= 365
                        ? `${num(sale.holding_days / 365, 1)} an(s)`
                        : `${sale.holding_days} j`}
                  </td>
                  <td className="right">
                    <button
                      className="chip"
                      onClick={() => cancel(sale)}
                      title="Annule la cession et remet les titres en portefeuille au prix de revient d'origine."
                    >
                      Annuler
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="note">
        Les dividendes d'une ligne vendue sont figés au moment de la cession : une fois la
        position partie, ils ne seraient plus recalculables. Ils restent comptés dans le
        cumul du portefeuille.
      </div>

      <div className="note">
        Dans un PEA, ces plus-values ne sont pas imposées tant qu'aucun retrait n'est
        effectué. Ce tableau est un suivi de performance, pas une déclaration fiscale.
      </div>
    </div>
  );
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
    </div>
  );
}
