import { useCallback, useEffect, useState } from "react";
import { api, type Quote } from "../lib/api";
import { changeClass, compact, num, pct, price, time } from "../lib/format";

/** Listes de suivi : cotations d'un lot de titres, rafraîchies en continu.
 *
 *  Les listes livrées ne sont que des exemples de départ. Elles se modifient
 *  ici — sans quoi elles resteraient un décor qu'on ne peut ni corriger ni
 *  faire sien. */
export function Watchlist({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [lists, setLists] = useState<Record<string, string[]>>({});
  const [active, setActive] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [errors, setErrors] = useState<{ symbol: string; error: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async (keep?: string) => {
    const response = await api.watchlists();
    setLists(response.watchlists);
    const names = Object.keys(response.watchlists);
    setActive((current) => {
      const wanted = keep ?? current;
      return wanted && names.includes(wanted) ? wanted : (names[0] ?? null);
    });
  }, []);

  useEffect(() => {
    reload().catch((err) =>
      setFailure(err instanceof Error ? err.message : "Erreur"),
    );
  }, [reload]);

  const write = async (name: string, symbols: string[], message: string) => {
    setBusy(true);
    try {
      await api.saveWatchlist(name, symbols);
      await reload(name);
      setNotice(message);
      setFailure(null);
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  };

  const addSymbol = async () => {
    const raw = query.trim();
    if (!raw || !active) return;
    setBusy(true);
    try {
      // La recherche accepte un ticker, un ISIN ou un nom : on lui laisse le
      // soin de résoudre plutôt que d'exiger la syntaxe exacte de Yahoo.
      const found = await api.search(raw, 1);
      const symbol = found.results[0]?.symbol ?? raw.toUpperCase();
      const current = lists[active] ?? [];
      if (current.includes(symbol)) {
        setNotice(`${symbol} est déjà dans « ${active} ».`);
        setQuery("");
        return;
      }
      setQuery("");
      await write(active, [...current, symbol], `${symbol} ajouté à « ${active} ».`);
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "Valeur introuvable");
    } finally {
      setBusy(false);
    }
  };

  const removeSymbol = (symbol: string) => {
    if (!active) return;
    const rest = (lists[active] ?? []).filter((s) => s !== symbol);
    return write(active, rest, `${symbol} retiré de « ${active} ».`);
  };

  const createList = async () => {
    const name = window.prompt("Nom de la nouvelle liste ?")?.trim();
    if (!name) return;
    if (lists[name]) {
      setNotice(`« ${name} » existe déjà.`);
      return;
    }
    await write(name, [], `Liste « ${name} » créée. Ajoutez-y des valeurs.`);
  };

  const removeList = async () => {
    if (!active) return;
    if (!window.confirm(`Supprimer la liste « ${active} » ?`)) return;
    setBusy(true);
    try {
      await api.deleteWatchlist(active);
      await reload();
      setNotice(`Liste « ${active} » supprimée.`);
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "Erreur");
    } finally {
      setBusy(false);
    }
  };

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
          <button
            className={`chip ${editing ? "active" : ""}`}
            onClick={() => setEditing((value) => !value)}
          >
            {editing ? "Terminer" : "Modifier"}
          </button>
        </div>

        {editing && (
          <div className="panel-body">
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") addSymbol();
                }}
                placeholder="Ticker, ISIN ou nom — MC.PA, FR0000121014, Air Liquide"
                style={{ flex: 1, minWidth: 260 }}
              />
              <button className="chip active" onClick={addSymbol} disabled={busy || !query.trim()}>
                Ajouter
              </button>
              <button className="chip" onClick={createList} disabled={busy}>
                + Nouvelle liste
              </button>
              <button
                className="chip"
                style={{ color: "var(--down)" }}
                onClick={removeList}
                disabled={busy || Object.keys(lists).length <= 1}
                title={
                  Object.keys(lists).length <= 1
                    ? "La dernière liste ne peut pas être supprimée."
                    : `Supprime « ${active} ».`
                }
              >
                Supprimer la liste
              </button>
            </div>
            <div className="note" style={{ marginTop: 6 }}>
              La recherche résout un ISIN ou un nom en ticker. Vos listes sont
              enregistrées localement ; tant que vous n'y touchez pas, les deux listes
              d'exemple livrées avec le terminal s'affichent.
            </div>
          </div>
        )}

        {notice && (
          <div className="panel-body">
            <div className="callout">{notice}</div>
          </div>
        )}

        {failure && <div className="panel-body"><div className="callout error">{failure}</div></div>}

        {loading && quotes.length === 0 && !failure && (
          <div className="spinner">Chargement des cotations…</div>
        )}

        {!loading && active !== null && (lists[active]?.length ?? 0) === 0 && (
          <div className="panel-body">
            <div className="callout">
              La liste « {active} » est vide. Ouvrez <strong>Modifier</strong> pour y
              ajouter des valeurs.
            </div>
          </div>
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
                  {editing && <th />}
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
                      <td className="right num">{price(quote.last_price, quote.currency)}</td>
                      <td className={`right num ${changeClass(variation)}`}>{pct(variation)}</td>
                      <td className="right num dim">{num(quote.open)}</td>
                      <td className="right num dim">{num(quote.high)}</td>
                      <td className="right num dim">{num(quote.low)}</td>
                      <td className="right num dim">{compact(quote.volume)}</td>
                      <td className="right num faint">
                        {num(quote.year_low)} – {num(quote.year_high)}
                      </td>
                      {editing && (
                        <td className="right">
                          <button
                            className="chip"
                            style={{ color: "var(--down)" }}
                            onClick={(event) => {
                              // La ligne entière ouvre la fiche société.
                              event.stopPropagation();
                              removeSymbol(quote.symbol);
                            }}
                            disabled={busy}
                            title={`Retirer ${quote.symbol} de la liste`}
                          >
                            Retirer
                          </button>
                        </td>
                      )}
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
