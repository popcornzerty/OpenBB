import { useEffect, useMemo, useRef, useState } from "react";
import { api, type SearchResult } from "../lib/api";
import { type GlossaryEntry, searchGlossary } from "../data/glossary";
import { PeaBadge } from "./PeaBadge";

/** Palette de recherche, ouverte au clavier.
 *
 *  Accepte un nom, un ticker ou un **ISIN** : les relevés de brokers français
 *  identifient les titres par ISIN, saisir « FR0000121014 » doit donc mener
 *  directement à LVMH. */
export function CommandBar({
  open,
  onClose,
  onPick,
  onGlossary,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (symbol: string) => void;
  /** Ouvre une fiche du glossaire. Absent, seuls les titres sont proposés. */
  onGlossary?: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setCursor(0);
      setError(null);
      // Le focus doit attendre que l'overlay soit peint.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      return;
    }
    // Anti-rebond : on ne part pas en requête à chaque frappe.
    const timer = setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const response = await api.search(term);
        setResults(response.results);
        setCursor(0);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Recherche indisponible");
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 220);
    return () => clearTimeout(timer);
  }, [query, open]);

  // Le glossaire vit en mémoire : il répond à la frappe, sans attendre le
  // réseau. Ses résultats précèdent donc toujours ceux des titres.
  const termes = useMemo<GlossaryEntry[]>(() => {
    const terme = query.trim();
    if (!onGlossary || terme.length < 2) return [];
    return searchGlossary(terme).slice(0, 4);
  }, [query, onGlossary]);

  const total = termes.length + results.length;

  if (!open) return null;

  const choose = (symbol: string) => {
    onPick(symbol);
    onClose();
  };

  const chooseTerme = (id: string) => {
    onGlossary?.(id);
    onClose();
  };

  /** Élément désigné par le curseur, glossaire d'abord puis titres. */
  const activer = (index: number) => {
    if (index < termes.length) chooseTerme(termes[index].id);
    else results[index - termes.length] && choose(results[index - termes.length].symbol);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      onClose();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((c) => Math.min(c + 1, total - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (event.key === "Enter" && total > 0) {
      activer(cursor);
    }
  };

  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="command" onMouseDown={(event) => event.stopPropagation()}>
        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            onGlossary
              ? "Titre ou terme — LVMH, FR0000121014, PER, P/B…"
              : "Nom, ticker ou ISIN — ex. LVMH, MC.PA, FR0000121014"
          }
          aria-label="Recherche de titre"
        />
        <div className="command-results">
          {error && <div className="command-empty">{error}</div>}
          {!error && busy && results.length === 0 && (
            <div className="command-empty">Recherche…</div>
          )}
          {!error && !busy && query.trim().length >= 2 && total === 0 && (
            <div className="command-empty">Aucun résultat pour « {query.trim()} »</div>
          )}
          {termes.map((entry, index) => (
            <button
              key={`glossaire-${entry.id}`}
              className={`command-item ${index === cursor ? "active" : ""}`}
              onMouseEnter={() => setCursor(index)}
              onClick={() => chooseTerme(entry.id)}
            >
              <span className="badge plain">Glossaire</span>
              <span className="name">{entry.term}</span>
              <span className="faint">{(entry.aliases ?? []).join(" · ")}</span>
            </button>
          ))}
          {query.trim().length < 2 && (
            <div className="command-empty">
              Saisissez au moins deux caractères. Un ISIN est résolu
              automatiquement, et les termes du glossaire sont cherchés par leur
              nom comme par leur sigle.
            </div>
          )}
          {results.map((item, index) => (
            <button
              key={item.symbol}
              className={`command-item ${index + termes.length === cursor ? "active" : ""}`}
              onMouseEnter={() => setCursor(index + termes.length)}
              onClick={() => choose(item.symbol)}
            >
              <span className="sym">{item.symbol}</span>
              <span className="name">{item.name}</span>
              <span className="faint">{item.exchange ?? ""}</span>
              <PeaBadge status={item.pea_status} compact />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
