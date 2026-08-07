import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { AmfMovements } from "./AmfMovements";
import { Managers } from "./Managers";
import { Watchlist } from "./Watchlist";

type Onglet = "cotations" | "mouvements" | "gerants";

/** Écran Marché : cotations suivies et mouvements déclarés.
 *
 *  Les deux répondent à des questions différentes — ce que fait le cours, et
 *  ce que font ceux qui en détiennent beaucoup — mais portent sur les mêmes
 *  valeurs, d'où leur réunion sous un même écran. */
export function Market({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [onglet, setOnglet] = useState<Onglet>("cotations");
  const [lists, setLists] = useState<string[]>([]);

  useEffect(() => {
    api
      .watchlists()
      .then((response) => setLists(Object.keys(response.watchlists)))
      .catch(() => setLists([]));
  }, []);

  return (
    <div className="stack">
      <div className="tabs" style={{ padding: 0, marginBottom: 4 }}>
        <button
          className={onglet === "cotations" ? "active" : ""}
          onClick={() => setOnglet("cotations")}
        >
          Cotations
        </button>
        <button
          className={onglet === "mouvements" ? "active" : ""}
          onClick={() => setOnglet("mouvements")}
        >
          Mouvements déclarés
        </button>
        <button
          className={onglet === "gerants" ? "active" : ""}
          onClick={() => setOnglet("gerants")}
        >
          Gérants américains
        </button>
      </div>

      {onglet === "cotations" ? (
        <Watchlist onOpen={onOpen} />
      ) : onglet === "mouvements" ? (
        <AmfMovements lists={lists} onOpen={onOpen} />
      ) : (
        <Managers lists={lists} onOpen={onOpen} />
      )}
    </div>
  );
}
