import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type PortfolioRow,
  type PortfolioSummary,
  type PositionInput,
} from "../lib/api";
import { PeaBadge } from "../components/PeaBadge";
import { PortfolioAllocation } from "./PortfolioAllocation";
import { changeClass, compact, date, money, num, pct } from "../lib/format";

type Tab = "positions" | "repartition";

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
      setNotice(`${symbol} supprimée.`);
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
                  Aucune position. Ajoutez-en une à la main, importez un CSV, ou reprenez
                  celles de Wealthfolio. Le CSV doit comporter au minimum les colonnes
                  <strong> symbole</strong> et <strong>quantité</strong> ; un prix de revient,
                  une devise et une date d'entrée sont reconnus s'ils sont présents.
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
              </div>
              <div className="panel-body flush table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Date estimée</th>
                      <th>Titre</th>
                      <th className="right">Montant attendu</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.upcoming.map((item) => (
                      <tr key={`${item.symbol}-${item.date}`}>
                        <td className="num">≈ {date(item.date)}</td>
                        <td className="sym">{item.symbol}</td>
                        <td className="right num">{money(item.amount, "EUR")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="panel-body">
                <div className="note">
                  Dates projetées d'après le rythme de versement observé, montants estimés
                  d'après le dernier détachement connu. Aucune source gratuite ne publie le
                  calendrier ni les montants annoncés pour les valeurs européennes.
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
      <Kpi label="Dividendes perçus" value={money(summary.dividends_collected, "EUR")} />
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

function Kpi({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className={`value ${tone ?? ""}`}>{value}</div>
    </div>
  );
}

/** Saisie ou modification d'une position. */
function PositionForm({
  position,
  onCancel,
  onSave,
  onDelete,
}: {
  position: PositionInput;
  onCancel: () => void;
  onSave: (position: PositionInput) => void;
  onDelete?: (symbol: string) => void;
}) {
  const [form, setForm] = useState(position);
  const isNew = !position.symbol;

  const set = (key: keyof PositionInput, value: string) =>
    setForm((current) => ({
      ...current,
      [key]:
        key === "quantity" || key === "average_cost"
          ? Number(value.replace(",", ".")) || 0
          : value,
    }));

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
          <Field label="Quantité">
            <input value={String(form.quantity)} onChange={(e) => set("quantity", e.target.value)} inputMode="decimal" />
          </Field>
          <Field label="Prix de revient unitaire">
            <input value={String(form.average_cost)} onChange={(e) => set("average_cost", e.target.value)} inputMode="decimal" />
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
            <div>
              {onDelete && (
                <button
                  className="chip"
                  style={{ color: "var(--down)" }}
                  onClick={() => onDelete(position.symbol)}
                >
                  Supprimer
                </button>
              )}
            </div>
            <div className="row">
              <button className="chip" onClick={onCancel}>Annuler</button>
              <button
                className="chip active"
                onClick={() => onSave(form)}
                disabled={!form.symbol || form.quantity <= 0}
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
