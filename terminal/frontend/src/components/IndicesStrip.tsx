import { useEffect, useState } from "react";
import { api, type IndexSnapshot } from "../lib/api";
import { changeClass, num, pctPoints } from "../lib/format";

/** Bandeau des grands indices européens, en tête d'écran. */
export function IndicesStrip() {
  const [indices, setIndices] = useState<IndexSnapshot[]>([]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const response = await api.indices();
        if (alive) {
          setIndices(response.indices);
          setFailed(false);
        }
      } catch {
        if (alive) setFailed(true);
      }
    };
    load();
    // Les indices européens sont différés : un rafraîchissement par minute suffit.
    const timer = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  if (failed) {
    return (
      <div className="strip">
        <span className="strip-item faint">Indices indisponibles — backend injoignable</span>
      </div>
    );
  }

  if (indices.length === 0) {
    return (
      <div className="strip">
        <span className="strip-item faint">Chargement des indices…</span>
      </div>
    );
  }

  return (
    <div className="strip">
      {indices.map((index) => (
        <div className="strip-item" key={index.symbol}>
          <span className="name">{index.name}</span>
          {index.error ? (
            <span className="faint">—</span>
          ) : (
            <>
              <span className="val">{num(index.close, 2)}</span>
              <span className={`val ${changeClass(index.change_percent)}`}>
                {pctPoints(index.change_percent)}
              </span>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
