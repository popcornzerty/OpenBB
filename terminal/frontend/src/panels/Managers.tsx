import { useCallback, useEffect, useState } from "react";
import { api, type Managers as Data } from "../lib/api";
import { changeClass, compact, date, pct } from "../lib/format";

/** Gérants américains présents sur les valeurs suivies.
 *
 *  Les dépôts SEC couvrent aussi les positions européennes des gérants
 *  américains : c'est la seule vue gratuite sur des mouvements de gérants
 *  nommés. Elle est partielle, et l'écran le dit plutôt que de laisser croire
 *  à un classement des « meilleurs gérants ». */
export function Managers({
  lists,
  onOpen,
}: {
  lists: string[];
  onOpen: (symbol: string) => void;
}) {
  const [scope, setScope] = useState<"portefeuille" | "liste">("portefeuille");
  const [listName, setListName] = useState(lists[0] ?? "");
  const [top, setTop] = useState(4);
  const [data, setData] = useState<Data | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.managers(scope, scope === "liste" ? listName : "", top));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setLoading(false);
    }
  }, [scope, listName, top]);

  useEffect(() => {
    load();
  }, [load]);

  const chip = (actif: boolean) => `chip ${actif ? "active" : ""}`;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Gérants américains</span>
          <div className="chips">
            <button
              className={chip(scope === "portefeuille")}
              onClick={() => setScope("portefeuille")}
            >
              Mon portefeuille
            </button>
            {lists.map((name) => (
              <button
                key={name}
                className={chip(scope === "liste" && listName === name)}
                onClick={() => {
                  setScope("liste");
                  setListName(name);
                }}
              >
                {name}
              </button>
            ))}
          </div>
          <span className="spacer" style={{ flex: 1 }} />
          <div className="chips">
            {[4, 8, 12].map((n) => (
              <button key={n} className={chip(top === n)} onClick={() => setTop(n)}>
                {n} premiers
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="panel-body">
            <div className="callout error">{error}</div>
          </div>
        )}

        {loading && !data && <div className="spinner">Lecture des dépôts SEC…</div>}

        {data && data.managers.length === 0 && (
          <div className="panel-body">
            <div className="callout">
              Aucun gérant actif ne détient au moins deux de ces valeurs dans ses dépôts.
              {data.index_lines_excluded > 0 && (
                <> {data.index_lines_excluded} ligne(s) de fonds indiciels écartée(s).</>
              )}
            </div>
          </div>
        )}

        {data?.managers.map((manager) => (
          <div key={manager.holder} className="panel-body">
            <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
              <div>
                <strong>{manager.holder}</strong>{" "}
                <span className="faint">
                  · {manager.positions} ligne(s) · {manager.categorie}
                </span>
              </div>
              <div className="num">
                {compact(manager.value, "USD")}
                <span className="faint" style={{ marginLeft: 8 }}>
                  {manager.achats > 0 && <span className="up">▲ {manager.achats}</span>}
                  {manager.achats > 0 && manager.ventes > 0 && " / "}
                  {manager.ventes > 0 && <span className="down">▼ {manager.ventes}</span>}
                </span>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Titre</th>
                    <th className="right">Titres</th>
                    <th className="right">Encours</th>
                    <th className="right">% du capital</th>
                    <th className="right">Variation</th>
                    <th className="right">Déclaré au</th>
                  </tr>
                </thead>
                <tbody>
                  {manager.holdings.map((h) => (
                    <tr key={h.symbol}>
                      <td>
                        <button className="link sym" onClick={() => onOpen(h.symbol)}>
                          {h.symbol}
                        </button>
                      </td>
                      <td className="right num">{compact(h.shares)}</td>
                      <td className="right num dim">{compact(h.value, "USD")}</td>
                      <td className="right num faint">{pct(h.pct_held, 2).replace("+", "")}</td>
                      <td className={`right num ${changeClass(h.pct_change)}`}>
                        {h.pct_change === null || h.pct_change === 0
                          ? "—"
                          : pct(h.pct_change, 1)}
                      </td>
                      <td className="right num faint">{date(h.date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ))}
      </div>

      {data && <Limites data={data} />}
    </div>
  );
}

/** Ce que cette vue n'est pas. */
function Limites({ data }: { data: Data }) {
  return (
    <>
      <div className="note">
        <strong>Ce n'est pas un classement des meilleurs gérants.</strong> C'est la liste
        de ceux qui déclarent à la SEC et détiennent au moins deux des valeurs suivies.
        Le rang tient à la présence, pas à la performance : le terminal ne dispose
        d'aucune mesure du talent d'un gérant.
      </div>

      <div className="note">
        <strong>Part américaine seulement.</strong> Les dépôts SEC — 13F pour les
        mandats, N-PORT pour les fonds — ne couvrent que les gérants américains. Il
        n'existe pas d'équivalent européen publié : le reporting AIFMD va aux
        régulateurs, pas au public. Les pourcentages de capital affichés sont donc
        minuscules, car ils ne représentent qu'une fraction du tour de table.
      </div>

      <div className="note">
        <strong>Quarante-cinq à soixante jours de retard.</strong> Un dépôt trimestriel
        paraît après la clôture du trimestre. Dernier arrêté retenu :{" "}
        {data.as_of ? date(data.as_of) : "inconnu"}. Ce qui est affiché a déjà été fait,
        et peut avoir été défait depuis.
      </div>

      <div className="note">
        Les fonds indiciels sont écartés — {data.index_lines_excluded} ligne(s) sur cette
        sélection. Vanguard, iShares et consorts détiennent tout par construction, et
        leurs variations traduisent la collecte de leurs clients, pas une décision de
        gestion. Les garder reviendrait à les voir occuper tout le classement.{" "}
        {data.candidates} gérant(s) restaient candidats.
      </div>
    </>
  );
}
