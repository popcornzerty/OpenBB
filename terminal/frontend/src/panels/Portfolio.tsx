import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type PortfolioRow,
  type PortfolioSummary,
  type PositionInput,
} from "../lib/api";
import { PeaBadge } from "../components/PeaBadge";
import { PortfolioAllocation } from "./PortfolioAllocation";
import { PortfolioSales } from "./PortfolioSales";
import { changeClass, compact, date, money, num, pct } from "../lib/format";

type Tab = "positions" | "repartition" | "cessions";

const EMPTY: PositionInput = {
  symbol: "",
  quantity: 0,
  average_cost: 0,
  currency: "EUR",
  opened_at: "",
  label: "",
};

/** Portefeuille tenu par le terminal.
 *
 *  Les positions sont saisies, importées ou modifiées ici. Wealthfolio reste
 *  disponible en source d'import initial, mais n'alimente plus l'affichage :
 *  une modification faite ici ne remonte jamais vers lui. */
export function Portfolio({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [tab, setTab] = useState<Tab>("positions");
  const [rows, setRows] = useState<PortfolioRow[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [empty, setEmpty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<PositionInput | null>(null);
  // Ligne en cours de cession, avec son cours pour préremplir le prix.
  const [selling, setSelling] = useState<PortfolioRow | null>(null);
  const [wealthfolioCount, setWealthfolioCount] = useState(0);
  // Fichier lu, en attente du choix « compléter » ou « remplacer ».
  const [pending, setPending] = useState<{ name: string; content: string } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [data, status] = await Promise.all([api.portfolio(), api.portfolioStatus()]);
      setRows(data.rows);
      setSummary(data.summary);
      setEmpty(data.empty);
      setWealthfolioCount(status.wealthfolio.positions);
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

  const savePosition = async (position: PositionInput) => {
    try {
      await api.savePosition(position.symbol, position);
      setEditing(null);
      setNotice(`${position.symbol.toUpperCase()} enregistrée.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  const removePosition = async (symbol: string) => {
    try {
      await api.deletePosition(symbol);
      setNotice(
        `${symbol} retirée sans enregistrer de cession. ` +
          "Si vous l'avez vendue, utilisez « Vendre » pour conserver la plus-value.",
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  const sell = async (
    symbol: string,
    sale: {
      quantity: number | null;
      price: number;
      date: string;
      fees: number;
      note: string;
    },
  ) => {
    try {
      const result = await api.sellPosition(symbol, sale);
      setSelling(null);
      const gain = result.sale.gain;
      setNotice(
        `${symbol} : ${result.sale.quantity} titre(s) vendu(s), ` +
          `${gain >= 0 ? "plus-value" : "moins-value"} de ${money(gain, "EUR")}.` +
          (result.remaining > 0 ? ` Il reste ${result.remaining} titre(s).` : ""),
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  const runImport = async (replace: boolean) => {
    if (!pending) return;
    setPending(null);
    try {
      const result = await api.importCsv(pending.content, replace);
      setNotice(
        `${result.imported} position(s) ${replace ? "importée(s)" : "ajoutée(s)"}.` +
          (result.warnings.length ? ` ${result.warnings.join(" ")}` : ""),
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import impossible");
    }
  };

  const importWealthfolio = async () => {
    try {
      const result = await api.importWealthfolio();
      setNotice(`${result.imported} position(s) reprises depuis Wealthfolio.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  const tabs = (
    <div className="tabs" style={{ padding: 0, marginBottom: 4 }}>
      <button className={tab === "positions" ? "active" : ""} onClick={() => setTab("positions")}>
        Positions
      </button>
      <button
        className={tab === "repartition" ? "active" : ""}
        onClick={() => setTab("repartition")}
        disabled={empty}
      >
        Répartition
      </button>
      <button
        className={tab === "cessions" ? "active" : ""}
        onClick={() => setTab("cessions")}
      >
        Cessions{summary?.realized.count ? ` (${summary.realized.count})` : ""}
      </button>
    </div>
  );

  if (loading && rows.length === 0) {
    return (
      <div className="stack">
        {tabs}
        <div className="spinner">Chargement du portefeuille…</div>
      </div>
    );
  }

  return (
    <div className="stack">
      {tabs}

      {error && <div className="callout error">{error}</div>}
      {notice && <div className="callout">{notice}</div>}

      {tab === "repartition" ? (
        <PortfolioAllocation />
      ) : tab === "cessions" ? (
        <PortfolioSales onChanged={load} onOpen={onOpen} />
      ) : (
        <>
          {summary && <Summary summary={summary} />}

          <div className="panel">
            <div className="panel-head">
              <span className="panel-title">Positions</span>
              <span className="spacer" style={{ flex: 1 }} />
              <button className="chip" onClick={() => setEditing({ ...EMPTY })}>
                + Ajouter
              </button>
              <button className="chip" onClick={() => fileInput.current?.click()}>
                Importer un CSV
              </button>
              {wealthfolioCount > 0 && (
                <button
                  className="chip"
                  onClick={importWealthfolio}
                  title="Reprend les positions tenues dans Wealthfolio. Import ponctuel : rien ne repart vers lui."
                >
                  Reprendre depuis Wealthfolio ({wealthfolioCount})
                </button>
              )}
              <input
                ref={fileInput}
                type="file"
                accept=".csv,text/csv"
                style={{ display: "none" }}
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (!file) return;
                  // Le sens de l'import n'est pas devinable : un relevé de
                  // positions remplace le portefeuille, une liste de nouvelles
                  // lignes le complète. On demande plutôt que d'écraser.
                  setError(null);
                  setPending({ name: file.name, content: await file.text() });
                }}
              />
            </div>

            {pending && (
              <div className="panel-body">
                <div className="callout">
                  <div>
                    <strong>{pending.name}</strong> — que faire des {rows.length} ligne(s)
                    déjà enregistrée(s) ?
                  </div>
                  <div className="row" style={{ gap: 8, marginTop: 8 }}>
                    <button className="chip" onClick={() => runImport(false)}>
                      Compléter l'existant
                    </button>
                    <button className="chip" onClick={() => runImport(true)}>
                      Remplacer tout le portefeuille
                    </button>
                    <button className="chip" onClick={() => setPending(null)}>
                      Annuler
                    </button>
                  </div>
                  <div className="note" style={{ marginTop: 6 }}>
                    « Compléter » conserve vos lignes actuelles ; une valeur présente dans
                    les deux est écrasée par celle du fichier. Les titres désignés par ISIN
                    sont résolus en tickers automatiquement.
                  </div>
                </div>
              </div>
            )}

            {empty ? (
              <div className="panel-body">
                <div className="callout">
                  Aucune position. Ajoutez-en une à la main ou importez un CSV
                  {/* Ne proposer Wealthfolio que s'il est réellement installé :
                      l'évoquer sinon laisserait croire qu'il est nécessaire. */}
                  {wealthfolioCount > 0 && <> , ou reprenez celles de Wealthfolio</>}.
                  {" "}Le CSV doit comporter au minimum les colonnes
                  <strong> symbole</strong> et <strong>quantité</strong> ; un prix de revient,
                  une devise et une date d'entrée sont reconnus s'ils sont présents. Les
                  titres désignés par leur ISIN sont résolus automatiquement.
                </div>
              </div>
            ) : (
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
                      <th className="right">Div. perçus</th>
                      <th>Prochain détach.</th>
                      <th style={{ width: 90 }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const accrued = row.dividend?.accrued;
                      return (
                        <tr key={row.symbol}>
                          <td
                            className="sym clickable"
                            onClick={() => onOpen(row.symbol)}
                            title="Ouvrir la fiche société"
                          >
                            {row.symbol}
                          </td>
                          <td>
                            <span className="truncate dim">{row.name ?? row.label}</span>
                          </td>
                          <td>
                            <PeaBadge status={row.pea_status} reason={row.pea_reason} compact />
                          </td>
                          <td className="right num">{compact(row.quantity)}</td>
                          <td className="right num dim">{num(row.average_cost)}</td>
                          <td className="right num">
                            {num(row.price)}
                            {row.price_source === "prev_close" && (
                              <span className="faint" title="Clôture précédente : ce titre ne remonte pas de dernier cours"> *</span>
                            )}
                          </td>
                          <td className="right num">{money(row.market_value, "EUR")}</td>
                          <td className={`right num ${changeClass(row.gain)}`}>
                            {money(row.gain, "EUR")}
                          </td>
                          <td
                            className={`right num ${changeClass(row.gain_percent)}`}
                            title={
                              row.gain_percent === null
                                ? "Prix de revient absent : la performance ne peut pas être calculée."
                                : `Rapportée au prix de revient de ${money(row.cost_basis, "EUR")}`
                            }
                          >
                            {pct(row.gain_percent)}
                          </td>
                          <td
                            className="right num"
                            title={
                              accrued?.amount === null
                                ? "Date d'entrée non renseignée : le cumul ne peut pas être établi."
                                : `${accrued?.payments ?? 0} détachement(s) depuis le ${date(row.opened_at)}`
                            }
                          >
                            {accrued?.amount === null || accrued === undefined
                              ? "—"
                              : money(accrued.amount, "EUR")}
                          </td>
                          <td className="faint num">
                            {row.dividend?.next_ex_date
                              ? `≈ ${date(row.dividend.next_ex_date)}`
                              : "—"}
                          </td>
                          <td className="right">
                            <button
                              className="chip"
                              onClick={() =>
                                setEditing({
                                  symbol: row.symbol,
                                  quantity: row.quantity,
                                  average_cost: row.average_cost,
                                  currency: row.currency,
                                  opened_at: row.opened_at,
                                  label: row.label,
                                })
                              }
                            >
                              Modifier
                            </button>
                            <button
                              className="chip"
                              style={{ marginLeft: 4 }}
                              onClick={() => setSelling(row)}
                              title="Enregistre une cession : la plus-value et les dividendes déjà perçus sont conservés."
                            >
                              Vendre
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {summary && summary.upcoming.length > 0 && (
            <div className="panel">
              <div className="panel-head">
                <span className="panel-title">Prochains dividendes attendus</span>
                <span className="spacer" style={{ flex: 1 }} />
                <span className="badge plain">
                  {money(summary.upcoming_total, "EUR")} attendus
                </span>
              </div>
              <div className="panel-body flush table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date estimée</th>
                      <th>Titre</th>
                      <th className="right">Montant attendu</th>
                      <th className="right" title="Somme des détachements jusqu'à cette date incluse">
                        Cumulé
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.upcoming.map((item) => (
                      <tr key={`${item.symbol}-${item.date}`}>
                        <td className="num">≈ {date(item.date)}</td>
                        <td className="sym">{item.symbol}</td>
                        <td className="right num">{money(item.amount, "EUR")}</td>
                        <td className="right num dim">{money(item.cumulative, "EUR")}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={2} className="faint">
                        Total sur {summary.upcoming.length} détachement(s)
                      </td>
                      <td className="right num" />
                      <td className="right num">
                        <strong>{money(summary.upcoming_total, "EUR")}</strong>
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
              <div className="panel-body">
                <div className="note">
                  Dates projetées d'après le rythme de versement observé, montants estimés
                  d'après le dernier détachement connu. Aucune source gratuite ne publie le
                  calendrier ni les montants annoncés pour les valeurs européennes. Le
                  cumul ne couvre qu'un détachement par ligne — le prochain — et non une
                  année entière de distribution.
                  {summary.upcoming_unknown > 0 && (
                    <>
                      {" "}
                      {summary.upcoming_unknown} ligne(s) sans montant estimé restent hors
                      du total.
                    </>
                  )}
                </div>
              </div>
            </div>
          )}

          <div className="note">
            Les dividendes perçus ne comptent que les détachements <strong>postérieurs à la
            date d'entrée</strong> de chaque ligne, à quantité supposée constante : un
            renforcement en cours de période surestime les premiers versements. Renseignez
            vos vraies dates d'achat pour que le cumul ait un sens.
          </div>
        </>
      )}

      {editing && (
        <PositionForm
          position={editing}
          onCancel={() => setEditing(null)}
          onSave={savePosition}
          onDelete={rows.some((r) => r.symbol === editing.symbol) ? removePosition : undefined}
          onSell={
            rows.some((r) => r.symbol === editing.symbol)
              ? () => {
                  const row = rows.find((r) => r.symbol === editing.symbol) ?? null;
                  setEditing(null);
                  setSelling(row);
                }
              : undefined
          }
        />
      )}

      {selling && (
        <SaleForm
          row={selling}
          onCancel={() => setSelling(null)}
          onConfirm={(sale) => sell(selling.symbol, sale)}
        />
      )}
    </div>
  );
}

function Summary({ summary }: { summary: PortfolioSummary }) {
  return (
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
      {summary.realized.count > 0 && (
        <Kpi
          label="Plus-value réalisée"
          value={money(summary.realized.gain, "EUR")}
          // Rapportée au capital engagé sur les lignes vendues, pas au
          // portefeuille : c'est le rendement des opérations closes.
          sub={pct(summary.realized.gain_percent)}
          tone={changeClass(summary.realized.gain) as "up" | "down" | undefined}
        />
      )}
      <Kpi label="Dividendes perçus" value={money(summary.dividends_collected, "EUR")} />
      {summary.realized.count > 0 && (
        <Kpi
          label="Gain total"
          value={money(summary.overall_gain, "EUR")}
          sub={pct(summary.overall_gain_percent)}
          tone={changeClass(summary.overall_gain) as "up" | "down" | undefined}
        />
      )}
      <Kpi
        label="Rendement sur PRU"
        value={pct(summary.dividend_yield_on_cost, 2).replace("+", "")}
      />
      <Kpi label="Lignes" value={String(summary.positions)} />
      <Kpi
        label="PEA confirmé"
        value={pct(summary.confirmed_pea_share, 1).replace("+", "")}
      />
    </div>
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
  /** Précision affichée sous la valeur — un pourcentage, le plus souvent. */
  sub?: string;
}) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
      {sub && <div className={`faint num ${tone ?? ""}`} style={{ fontSize: 11 }}>{sub}</div>}
    </div>
  );
}

/** Saisie ou modification d'une position. */
function PositionForm({
  position,
  onCancel,
  onSave,
  onDelete,
  onSell,
}: {
  position: PositionInput;
  onCancel: () => void;
  onSave: (position: PositionInput) => void;
  onDelete?: (symbol: string) => void;
  onSell?: () => void;
}) {
  const [form, setForm] = useState(position);
  const isNew = !position.symbol;

  // Les montants sont tenus en texte tant que la saisie dure. Les convertir à
  // chaque frappe rendait toute décimale impossible : « 10, » repassait par
  // Number(), redevenait 10, et le séparateur disparaissait sous les doigts.
  const [quantity, setQuantity] = useState(
    position.quantity ? String(position.quantity) : "",
  );
  const [cost, setCost] = useState(
    position.average_cost ? String(position.average_cost) : "",
  );

  const toNumber = (text: string) =>
    Number(text.replace(",", ".").replace(/[\s  ]/g, "")) || 0;
  const quantityValue = toNumber(quantity);
  const costValue = toNumber(cost);

  const set = (key: keyof PositionInput, value: string) =>
    setForm((current) => ({ ...current, [key]: value }));

  return (
    <div className="overlay" onMouseDown={onCancel}>
      <div className="command" onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-head">
          <span className="panel-title">
            {isNew ? "Ajouter une position" : `Modifier ${position.symbol}`}
          </span>
        </div>
        <div className="panel-body stack" style={{ gap: 10 }}>
          <Field label="Symbole" hint="Ticker Yahoo, par exemple MC.PA ou DTE.DE">
            <input
              value={form.symbol}
              onChange={(event) => set("symbol", event.target.value.toUpperCase())}
              disabled={!isNew}
              autoFocus={isNew}
            />
          </Field>
          <Field label="Quantité" hint="Décimales acceptées, à la virgule comme au point.">
            <input
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              inputMode="decimal"
            />
          </Field>
          <Field label="Prix de revient unitaire">
            <input
              value={cost}
              onChange={(event) => setCost(event.target.value)}
              inputMode="decimal"
            />
          </Field>
          <Field
            label="Date d'entrée"
            hint="Décide des dividendes comptabilisés : seuls ceux détachés après cette date ont été perçus."
          >
            <input
              type="date"
              value={form.opened_at}
              onChange={(event) => set("opened_at", event.target.value)}
            />
          </Field>
          <Field label="Libellé" hint="Facultatif">
            <input value={form.label} onChange={(event) => set("label", event.target.value)} />
          </Field>

          <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
            <div className="row" style={{ gap: 6 }}>
              {onSell && (
                <button className="chip" onClick={onSell}>
                  Vendre…
                </button>
              )}
              {onDelete && (
                <button
                  className="chip"
                  style={{ color: "var(--down)" }}
                  onClick={() => onDelete(position.symbol)}
                  title="Retire la ligne sans enregistrer de plus-value. Pour une vente, utilisez « Vendre »."
                >
                  Supprimer
                </button>
              )}
            </div>
            <div className="row">
              <button className="chip" onClick={onCancel}>Annuler</button>
              <button
                className="chip active"
                onClick={() =>
                  onSave({ ...form, quantity: quantityValue, average_cost: costValue })
                }
                disabled={!form.symbol || quantityValue <= 0}
              >
                Enregistrer
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Enregistrement d'une cession, totale ou partielle.
 *
 *  Distincte de la suppression : elle conserve la plus-value réalisée et les
 *  dividendes déjà encaissés, que la disparition de la ligne effacerait. */
function SaleForm({
  row,
  onCancel,
  onConfirm,
}: {
  row: PortfolioRow;
  onCancel: () => void;
  onConfirm: (sale: {
    quantity: number | null;
    price: number;
    date: string;
    fees: number;
    note: string;
  }) => void;
}) {
  const [quantity, setQuantity] = useState(String(row.quantity));
  // Le dernier cours connu est le point de départ le plus probable, mais il
  // reste modifiable : une vente s'est faite à un prix, pas à une estimation.
  const [price, setPrice] = useState(row.price !== null ? String(row.price) : "");
  const [when, setWhen] = useState(new Date().toISOString().slice(0, 10));
  const [fees, setFees] = useState("");
  const [note, setNote] = useState("");

  const parsed = (value: string) =>
    Number(value.replace(",", ".").replace(/[\s  ]/g, "")) || 0;
  const soldQuantity = parsed(quantity);
  const soldPrice = parsed(price);
  const soldFees = parsed(fees);
  const partial = soldQuantity > 0 && soldQuantity < row.quantity;
  const tooMany = soldQuantity > row.quantity;
  const proceeds = soldQuantity * soldPrice;
  const netProceeds = proceeds - soldFees;
  // La plus-value se mesure sur ce qui rentre réellement : le courtage et les
  // taxes sont payés, ils ne sont pas un gain.
  const gain = netProceeds - soldQuantity * row.average_cost;
  const valid = soldQuantity > 0 && !tooMany && soldPrice > 0;

  return (
    <div className="overlay" onMouseDown={onCancel}>
      <div className="command" onMouseDown={(event) => event.stopPropagation()}>
        <div className="panel-head">
          <span className="panel-title">Vendre {row.symbol}</span>
        </div>
        <div className="panel-body stack" style={{ gap: 10 }}>
          <Field
            label="Quantité vendue"
            hint={`${compact(row.quantity)} titre(s) en portefeuille. Une quantité inférieure enregistre une cession partielle.`}
          >
            <input
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              inputMode="decimal"
              autoFocus
            />
          </Field>
          <Field label="Prix de vente unitaire" hint="Prérempli au dernier cours connu.">
            <input
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              inputMode="decimal"
            />
          </Field>
          <Field label="Date de vente">
            <input type="date" value={when} onChange={(e) => setWhen(e.target.value)} />
          </Field>
          <Field
            label="Frais et taxes"
            hint="Courtage et taxes de l'opération, en euros. Déduits de la plus-value."
          >
            <input
              value={fees}
              onChange={(event) => setFees(event.target.value)}
              inputMode="decimal"
              placeholder="0"
            />
          </Field>
          <Field
            label="Motif"
            hint="Conservé et affiché dans l'historique des cessions."
          >
            <input
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Arbitrage vers la santé, prise de bénéfice…"
            />
          </Field>

          {tooMany && (
            <div className="callout error">
              Vous ne détenez que {compact(row.quantity)} titre(s) de {row.symbol}.
            </div>
          )}

          {valid && (
            <div className="callout">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>Produit brut</span>
                <span className="num">{money(proceeds, "EUR")}</span>
              </div>
              {soldFees > 0 && (
                <>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span>Frais et taxes</span>
                    <span className="num down">−{money(soldFees, "EUR")}</span>
                  </div>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span>Produit net encaissé</span>
                    <strong className="num">{money(netProceeds, "EUR")}</strong>
                  </div>
                </>
              )}
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>Prix de revient ({num(row.average_cost)} × {compact(soldQuantity)})</span>
                <span className="num">{money(soldQuantity * row.average_cost, "EUR")}</span>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span>{gain >= 0 ? "Plus-value réalisée" : "Moins-value réalisée"}</span>
                <strong className={`num ${changeClass(gain)}`}>{money(gain, "EUR")}</strong>
              </div>
              {partial && (
                <div className="note" style={{ marginTop: 6 }}>
                  Cession partielle : il restera {compact(row.quantity - soldQuantity)}{" "}
                  titre(s) au même prix de revient unitaire.
                </div>
              )}
            </div>
          )}

          <div className="note">
            Dans un PEA, une plus-value réalisée n'est pas imposée tant qu'aucun retrait
            n'est effectué : elle est enregistrée ici à titre de suivi, pas de fiscalité.
          </div>

          <div className="row" style={{ justifyContent: "flex-end", marginTop: 4 }}>
            <button className="chip" onClick={onCancel}>Annuler</button>
            <button
              className="chip active"
              disabled={!valid}
              onClick={() =>
                onConfirm({
                  quantity: soldQuantity >= row.quantity ? null : soldQuantity,
                  price: soldPrice,
                  date: when,
                  fees: soldFees,
                  note: note.trim(),
                })
              }
            >
              Enregistrer la cession
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
    <div>
      <div className="label" style={{ fontSize: 11, color: "var(--text-faint)", marginBottom: 3 }}>
        {label}
      </div>
      {children}
      {hint && <div className="note" style={{ marginTop: 3 }}>{hint}</div>}
    </div>
  );
}
