import { useEffect, useState } from "react";
import { api, type Quote } from "../lib/api";
import { changeClass, compact, money, num, pct, time } from "../lib/format";

/** Listes de suivi : cotations d'un lot de titres, rafraîchies en continu. */
export function Watchlist({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [lists, setLists] = useState<Record<string, string[]>>({});
  const [active, setActive] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [errors, setErrors] = useState<{ symbol: string; error: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    api
      .watchlists()
      .then((response) => {
        setLists(response.watchlists);
        setActive(Object.keys(response.watchlists)[0] ?? null);
      })
      .catch((err) => setFailure(err instanceof Error ? err.message : "Erreur"));
  }, []);

  useEffect(() => {
    if (!active || !lists[active]) return;
    let alive = true;
    const load = async () => {
      try {
        const response = await api.quotes(lists[active]);
        if (!alive) return;
        setQuotes(response.quotes);
        setErrors(response.errors);
        setFailure(null);
      } catch (err) {
        if (alive) setFailure(err instanceof Error ? err.message : "Erreur");
      } finally {
        if (alive) setLoading(false);
      }
    };
    setLoading(true);
    load();
    const timer = setInterval(load, 60_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [active, lists]);

  const change = (quote: Quote): number | null => {
    if (quote.last_price === null || !quote.prev_close) return null;
    return quote.last_price / quote.prev_close - 1;
  };

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Listes de suivi</span>
          <div className="chips">
            {Object.keys(lists).map((name) => (
              <button
                key={name}
                className={`chip ${name === active ? "active" : ""}`}
                onClick={() => setActive(name)}
              >
                {name}
              </button>
            ))}
          </div>
          <span className="spacer" style={{ flex: 1 }} />
          <span className="note">
            {quotes[0]?.as_of ? `Mise à jour ${time(quotes[0].as_of)}` : ""}
          </span>
        </div>

        {failure && <div className="panel-body"><div className="callout error">{failure}</div></div>}

        {loading && quotes.length === 0 && !failure && (
          <div className="spinner">Chargement des cotations…</div>
        )}

        {quotes.length > 0 && (
          <div className="panel-body flush table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Titre</th>
                  <th>Nom</th>
                  <th className="right">Cours</th>
                  <th className="right">Var.</th>
                  <th className="right">Ouv.</th>
                  <th className="right">+ Haut</th>
                  <th className="right">+ Bas</th>
                  <th className="right">Volume</th>
                  <th className="right">52s bas–haut</th>
                </tr>
              </thead>
              <tbody>
                {quotes.map((quote) => {
                  const variation = change(quote);
                  return (
                    <tr
                      key={quote.symbol}
                      className="clickable"
                      onClick={() => onOpen(quote.symbol)}
                    >
                      <td className="sym">{quote.symbol}</td>
                      <td>
                        <span className="truncate dim">{quote.name ?? "—"}</span>
                      </td>
                      <td className="right num">{money(quote.last_price, quote.currency)}</td>
                      <td className={`right num ${changeClass(variation)}`}>{pct(variation)}</td>
                      <td className="right num dim">{num(quote.open)}</td>
                      <td className="right num dim">{num(quote.high)}</td>
                      <td className="right num dim">{num(quote.low)}</td>
                      <td className="right num dim">{compact(quote.volume)}</td>
                      <td className="right num faint">
                        {num(quote.year_low)} – {num(quote.year_high)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {errors.length > 0 && (
          <div className="panel-body">
            <div className="callout warn">
              Cotation indisponible pour : {errors.map((e) => e.symbol).join(", ")}
            </div>
          </div>
        )}
      </div>

      <div className="note">
        Cotations Euronext et XETRA différées d'environ 15 minutes — aucune source
        gratuite ne diffuse ces places en temps réel.
      </div>
    </div>
  );
}
