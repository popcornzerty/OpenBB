import { useCallback, useEffect, useState } from "react";
import { api, type AmfMovements as Movements } from "../lib/api";
import { compact, date, money, num, price } from "../lib/format";

type Source = "institutionnels" | "inities";

/** Mouvements déclarés à l'AMF : institutionnels et initiés.
 *
 *  Deux régimes que rien n'oblige à lire ensemble, mais qui se complètent :
 *  un gérant qui franchit 5 % engage un capital, un dirigeant qui vend engage
 *  sa lecture de sa propre société. */
export function AmfMovements({
  lists,
  onOpen,
}: {
  lists: string[];
  onOpen: (symbol: string) => void;
}) {
  const [scope, setScope] = useState<"portefeuille" | "liste">("portefeuille");
  const [listName, setListName] = useState(lists[0] ?? "");
  const [days, setDays] = useState(180);
  const [source, setSource] = useState<Source>("institutionnels");
  const [data, setData] = useState<Movements | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.amfMovements(scope, scope === "liste" ? listName : "", days);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setLoading(false);
    }
  }, [scope, listName, days]);

  useEffect(() => {
    load();
  }, [load]);

  const chip = (actif: boolean) => `chip ${actif ? "active" : ""}`;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Mouvements déclarés</span>
          <div className="chips">
            <button className={chip(scope === "portefeuille")} onClick={() => setScope("portefeuille")}>
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
            {[90, 180, 365].map((d) => (
              <button key={d} className={chip(days === d)} onClick={() => setDays(d)}>
                {d === 365 ? "1 an" : `${d} j`}
              </button>
            ))}
          </div>
        </div>

        <div className="panel-body">
          <div className="chips">
            <button
              className={chip(source === "institutionnels")}
              onClick={() => setSource("institutionnels")}
            >
              Institutionnels — franchissements de seuils
              {data ? ` (${data.crossings.length})` : ""}
            </button>
            <button className={chip(source === "inities")} onClick={() => setSource("inities")}>
              Initiés — déclarations de dirigeants
              {data ? ` (${data.insiders.length})` : ""}
            </button>
          </div>
        </div>

        {error && (
          <div className="panel-body">
            <div className="callout error">{error}</div>
          </div>
        )}

        {loading && !data && (
          <div className="spinner">
            Lecture des avis de l'AMF — chaque déclaration est un document à ouvrir…
          </div>
        )}

        {data && source === "institutionnels" && (
          <Institutionnels data={data} onOpen={onOpen} />
        )}
        {data && source === "inities" && <Inities data={data} onOpen={onOpen} />}
      </div>

      {data && <Perimetre data={data} />}
    </div>
  );
}

function Institutionnels({
  data,
  onOpen,
}: {
  data: Movements;
  onOpen: (symbol: string) => void;
}) {
  if (data.crossings.length === 0) {
    return (
      <div className="panel-body">
        <div className="callout">
          Aucun franchissement de seuil déclaré sur ces valeurs depuis le{" "}
          {date(data.since)}. {data.crossings_scanned} avis parcourus sur l'ensemble de
          la cote française.
        </div>
      </div>
    );
  }

  return (
    <div className="panel-body flush table-wrap">
      <table>
        <thead>
          <tr>
            <th>Franchi le</th>
            <th>Titre</th>
            <th>Nom</th>
            <th>Déclarant</th>
            <th>Nature</th>
            <th className="right">Seuil</th>
            <th>Sens</th>
            <th className="right">Actions détenues</th>
            <th className="right">Cours du jour</th>
            <th className="right">Valeur détenue</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.crossings.map((row) => (
            <tr key={row.id}>
              <td className="num">{date(row.franchi_le ?? row.publie_le)}</td>
              <td>
                <button className="link sym" onClick={() => onOpen(row.symbol)}>
                  {row.symbol}
                </button>
              </td>
              <td className="truncate dim" style={{ maxWidth: 190 }} title={row.name ?? undefined}>
                {row.name ?? <span className="faint">—</span>}
              </td>
              <td title={row.societe ?? undefined}>
                {row.declarant ?? <span className="faint">non extrait</span>}
              </td>
              <td className="faint">
                {row.declarant_nature === "physique"
                  ? "personne physique"
                  : row.declarant_nature === "morale"
                    ? "société"
                    : "—"}
              </td>
              <td className="right num">
                {row.seuil === null ? "—" : `${num(row.seuil, 0)} %`}
                {row.seuil_nature && (
                  <span className="faint" style={{ fontSize: 11 }}> {row.seuil_nature}</span>
                )}
              </td>
              <td className={row.sens === "hausse" ? "up" : row.sens === "baisse" ? "down" : ""}>
                {row.sens === "hausse" ? "▲ en hausse" : row.sens === "baisse" ? "▼ en baisse" : "—"}
              </td>
              <td className="right num">
                {row.actions === null ? "—" : compact(row.actions)}
                {row.part_capital !== null && (
                  <span className="faint" style={{ fontSize: 11 }}>
                    {" "}
                    {(row.part_capital * 100).toFixed(2).replace(".", ",")} %
                  </span>
                )}
              </td>
              <td className="right num dim" title={`Clôture du ${date(row.franchi_le ?? row.publie_le)}`}>
                {price(row.cours, "EUR")}
              </td>
              <td className="right num">{money(row.valeur_participation, "EUR")}</td>
              <td className="right">
                {row.document && (
                  <a className="chip" href={row.document} target="_blank" rel="noreferrer">
                    Avis
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Inities({ data, onOpen }: { data: Movements; onOpen: (symbol: string) => void }) {
  if (data.insiders.length === 0) {
    return (
      <div className="panel-body">
        <div className="callout">
          Aucune déclaration de dirigeant sur ces valeurs depuis le {date(data.since)}.
        </div>
      </div>
    );
  }

  return (
    <div className="panel-body flush table-wrap">
      <table>
        <thead>
          <tr>
            <th>Opéré le</th>
            <th>Titre</th>
            <th>Nom</th>
            <th>Déclarant</th>
            <th>Fonction</th>
            <th>Sens</th>
            <th>Nature</th>
            <th className="right">Volume</th>
            <th className="right" title="Prix effectivement pratiqué, déclaré par l'intéressé">
              Prix payé
            </th>
            <th className="right">Montant</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data.insiders.map((row) => (
            <tr key={row.id}>
              <td className="num">{date(row.transaction_le ?? row.publie_le)}</td>
              <td>
                <button className="link sym" onClick={() => onOpen(row.symbol)}>
                  {row.symbol}
                </button>
              </td>
              <td className="truncate dim" style={{ maxWidth: 190 }} title={row.name ?? undefined}>
                {row.name ?? <span className="faint">—</span>}
              </td>
              <td title={row.emetteur ?? undefined}>
                {row.declarant ?? <span className="faint">non extrait</span>}
              </td>
              <td className="faint truncate" style={{ maxWidth: 220 }} title={row.fonction ?? undefined}>
                {row.fonction ?? "—"}
              </td>
              <td className={row.sens === "achat" ? "up" : row.sens === "vente" ? "down" : ""}>
                {row.sens === "achat" ? "▲ achat" : row.sens === "vente" ? "▼ vente" : "—"}
              </td>
              {/* La nature exacte compte : souscrire à un plan d'épargne
                  salariale n'est pas acheter en bourse. */}
              <td className="faint">{row.nature ?? "—"}</td>
              <td className="right num">{row.volume === null ? "—" : compact(row.volume)}</td>
              <td className="right num dim">{row.prix === null ? "—" : num(row.prix)}</td>
              <td className="right num">{money(row.montant, "EUR")}</td>
              <td className="right">
                {row.document && (
                  <a className="chip" href={row.document} target="_blank" rel="noreferrer">
                    Avis
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Ce que la source couvre, et surtout ce qu'elle ne couvre pas. */
function Perimetre({ data }: { data: Movements }) {
  return (
    <>
      <div className="note">
        <strong>Périmètre français uniquement.</strong> L'AMF ne publie que les
        déclarations portant sur des émetteurs cotés en France. Une absence d'alerte sur
        une valeur étrangère ne veut donc pas dire qu'il ne s'y passe rien : elle est
        hors du champ de cette source.
        {data.out_of_scope.length > 0 && (
          <>
            {" "}Non couvertes ici : <strong>{data.out_of_scope.join(", ")}</strong>.
          </>
        )}
        {data.in_scope.length > 0 && (
          <> Suivies : {data.in_scope.join(", ")}.</>
        )}
      </div>

      <div className="note">
        <strong>Deux natures de prix.</strong> Chez les initiés, le prix est celui
        réellement pratiqué : il figure dans la déclaration. Chez les institutionnels, il
        n'y en a pas — un avis de franchissement indique l'assiette atteinte, jamais le
        volume ni le prix de la transaction. La colonne « cours du jour » est donc la
        clôture du jour de franchissement, calculée par le terminal, et la « valeur
        détenue » en découle : c'est ce que pèse la participation, pas ce qu'elle a coûté.
      </div>

      <div className="note">
        Les <strong>franchissements de seuils</strong> ne se déclarent qu'aux paliers
        légaux — 5 %, 10 %, 15 %, 20 %, 25 %, 30 %, 50 %… Un gérant qui passe de 1 % à
        3 % reste invisible. Les <strong>déclarations de dirigeants</strong>, elles,
        couvrent chaque opération, sous trois jours ouvrés.
      </div>

      <div className="note">
        Sources : API ouverte info-financière (AMF/DILA) pour les franchissements, base
        BDIF de l'AMF pour les dirigeants. Cette seconde n'expose pas d'interface
        publique documentée : une refonte du site de l'AMF interromprait la lecture des
        déclarations de dirigeants, sans préavis.
      </div>
    </>
  );
}
