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
  const [editing, setEditing] = useState<Sale | null>(null);

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

  const save = async (id: string, changes: Parameters<typeof api.editSale>[1]) => {
    try {
      await api.editSale(id, changes);
      setEditing(null);
      setNotice("Cession corrigée.");
      await load();
      // La plus-value réalisée entre dans les indicateurs du portefeuille.
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
          <Kpi
            label="Produit des ventes"
            value={money(totals.net_proceeds, "EUR")}
            sub={totals.fees > 0 ? `dont ${money(totals.fees, "EUR")} de frais` : undefined}
          />
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
                <th className="right">Produit net</th>
                <th className="right">Frais</th>
                <Head label="+/- value" k="gain" right />
                <Head label="%" k="gain_percent" right />
                <th className="right">Dividendes</th>
                <Head label="Total" k="total_return" right />
                <Head label="Détention" k="holding_days" right />
                <th>Motif</th>
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
                      title={sale.label || sale.symbol}
                    >
                      {sale.symbol}
                    </button>
                  </td>
                  <td className="right num">{compact(sale.quantity)}</td>
                  <td className="right num dim">{num(sale.average_cost)}</td>
                  <td className="right num">{price(sale.sale_price, sale.currency)}</td>
                  <td
                    className="right num dim"
                    title={
                      sale.fees
                        ? `Produit brut ${money(sale.proceeds, "EUR")}, moins ${money(sale.fees, "EUR")} de frais`
                        : undefined
                    }
                  >
                    {money(sale.net_proceeds, "EUR")}
                  </td>
                  <td className="right num faint">
                    {sale.fees ? money(sale.fees, "EUR") : "—"}
                  </td>
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
                  <td className="faint" style={{ maxWidth: 260 }} title={sale.note}>
                    {sale.note || "—"}
                  </td>
                  <td className="right" style={{ whiteSpace: "nowrap" }}>
                    <button
                      className="chip"
                      onClick={() => setEditing(sale)}
                      title="Corrige le prix, les frais, les dates ou le motif."
                    >
                      Modifier
                    </button>
                    <button
                      className="chip"
                      style={{ marginLeft: 4 }}
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
        La plus-value est calculée sur le produit <strong>net de frais</strong> : le
        courtage et les taxes sont payés, ils ne sont pas un gain. Le produit brut reste
        lisible en infobulle, pour rapprochement avec le relevé du courtier.
      </div>

      <div className="note">
        Dans un PEA, ces plus-values ne sont pas imposées tant qu'aucun retrait n'est
        effectué. Ce tableau est un suivi de performance, pas une déclaration fiscale.
      </div>

      {editing && (
        <SaleEditForm
          sale={editing}
          onCancel={() => setEditing(null)}
          onSave={(changes) => save(editing.id, changes)}
        />
      )}
    </div>
  );
}

/** Correction d'une cession déjà enregistrée.
 *
 *  Le relevé du courtier arrive après la vente, avec le prix exact et les
 *  frais réels. Sans cet écran, les reprendre imposait d'annuler puis de
 *  ressaisir — au risque d'oublier la seconde étape et de laisser des titres
 *  revenus en portefeuille. */
function SaleEditForm({
  sale,
  onCancel,
  onSave,
}: {
  sale: Sale;
  onCancel: () => void;
  onSave: (changes: Parameters<typeof api.editSale>[1]) => void;
}) {
  const [salePrice, setSalePrice] = useState(String(sale.sale_price));
  const [fees, setFees] = useState(sale.fees ? String(sale.fees) : "");
  const [averageCost, setAverageCost] = useState(String(sale.average_cost));
  const [closedAt, setClosedAt] = useState(sale.closed_at.slice(0, 10));
  const [openedAt, setOpenedAt] = useState(sale.opened_at.slice(0, 10));
  const [note, setNote] = useState(sale.note);

  const parsed = (value: string) =>
    Number(value.replace(",", ".").replace(/[\s  ]/g, "")) || 0;
  const price = parsed(salePrice);
  const cost = parsed(averageCost);
  const charge = parsed(fees);
  const gain = sale.quantity * price - charge - sale.quantity * cost;
  const valid = price > 0;

  return (
    <div className="overlay" onMouseDown={onCancel}>
      <div className="command" onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-head">
          <span className="panel-title">Corriger la cession de {sale.symbol}</span>
        </div>
        <div className="panel-body stack" style={{ gap: 10 }}>
          <Field
            label="Quantité vendue"
            hint="Non modifiable : les titres ont été retirés du portefeuille à la vente. Pour la corriger, annulez la cession — les titres reviennent — puis ressaisissez-la."
          >
            <input value={compact(sale.quantity)} disabled />
          </Field>
          <Field label="Prix de vente unitaire">
            <input
              value={salePrice}
              onChange={(event) => setSalePrice(event.target.value)}
              inputMode="decimal"
              autoFocus
            />
          </Field>
          <Field label="Frais et taxes" hint="En euros, déduits de la plus-value.">
            <input
              value={fees}
              onChange={(event) => setFees(event.target.value)}
              inputMode="decimal"
              placeholder="0"
            />
          </Field>
          <Field
            label="Prix de revient unitaire"
            hint="Celui qui s'appliquait à la vente. Le corriger ne touche pas au portefeuille."
          >
            <input
              value={averageCost}
              onChange={(event) => setAverageCost(event.target.value)}
              inputMode="decimal"
            />
          </Field>
          <Field label="Date de vente">
            <input
              type="date"
              value={closedAt}
              onChange={(event) => setClosedAt(event.target.value)}
            />
          </Field>
          <Field label="Date d'entrée" hint="Sert au calcul de la durée de détention.">
            <input
              type="date"
              value={openedAt}
              onChange={(event) => setOpenedAt(event.target.value)}
            />
          </Field>
          <Field label="Motif">
            <input value={note} onChange={(event) => setNote(event.target.value)} />
          </Field>

          {valid && (
            <div className="callout">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>Produit net encaissé</span>
                <strong className="num">
                  {money(sale.quantity * price - charge, "EUR")}
                </strong>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>{gain >= 0 ? "Plus-value" : "Moins-value"} recalculée</span>
                <strong className={`num ${changeClass(gain)}`}>{money(gain, "EUR")}</strong>
              </div>
              {Math.abs(gain - sale.gain) > 0.005 && (
                <div className="note" style={{ marginTop: 6 }}>
                  Enregistrée jusqu'ici : {money(sale.gain, "EUR")}. Les dividendes figés
                  à la vente ({money(sale.dividends, "EUR")}) ne sont pas recalculés.
                </div>
              )}
            </div>
          )}

          <div className="row" style={{ justifyContent: "flex-end", marginTop: 4 }}>
            <button className="chip" onClick={onCancel}>Annuler</button>
            <button
              className="chip active"
              disabled={!valid}
              onClick={() =>
                onSave({
                  sale_price: price,
                  fees: charge,
                  average_cost: cost,
                  closed_at: closedAt,
                  opened_at: openedAt,
                  note: note.trim(),
                })
              }
            >
              Enregistrer
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="stack" style={{ gap: 3 }}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="note">{hint}</span>}
    </label>
  );
}

function Kpi({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
  /** Précision affichée sous la valeur — le montant des frais, par exemple. */
  sub?: string;
}) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
      {sub && <div className="faint num" style={{ fontSize: 11 }}>{sub}</div>}
    </div>
  );
}
