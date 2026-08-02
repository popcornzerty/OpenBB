import { useCallback, useEffect, useState } from "react";
import { CommandBar } from "./components/CommandBar";
import { IndicesStrip } from "./components/IndicesStrip";
import { Company } from "./panels/Company";
import { Portfolio } from "./panels/Portfolio";
import { Screener } from "./panels/Screener";
import { Valuation } from "./panels/Valuation";
import { Watchlist } from "./panels/Watchlist";

type View = "marche" | "portefeuille" | "screener" | "societe" | "valorisation";

const VIEWS: { id: View; label: string; key: string }[] = [
  { id: "marche", label: "Marché", key: "1" },
  { id: "portefeuille", label: "Portefeuille", key: "2" },
  { id: "screener", label: "Screener PEA", key: "3" },
  { id: "societe", label: "Société", key: "4" },
  { id: "valorisation", label: "Valorisation", key: "5" },
];

export default function App() {
  const [view, setView] = useState<View>("marche");
  const [symbol, setSymbol] = useState("MC.PA");
  const [commandOpen, setCommandOpen] = useState(false);

  const openSymbol = useCallback((next: string) => {
    setSymbol(next);
    setView("societe");
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target && (target.tagName === "INPUT" || target.tagName === "SELECT" || target.isContentEditable);

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
        return;
      }
      if (typing) return;

      // Raccourcis à touche unique, dans l'esprit d'un terminal : on ne les
      // arme que hors saisie, sinon taper « 2 » dans un filtre changerait d'écran.
      if (event.key === "/") {
        event.preventDefault();
        setCommandOpen(true);
        return;
      }
      const match = VIEWS.find((item) => item.key === event.key);
      if (match) setView(match.id);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="mark">◧</span>
          <span>Terminal PEA</span>
          <span className="sub">actions européennes</span>
        </div>

        <nav className="nav">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? "active" : ""}
              onClick={() => setView(item.id)}
              title={`Raccourci : ${item.key}`}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="spacer" />

        {(view === "societe" || view === "valorisation") && (
          <span className="sym">{symbol}</span>
        )}

        <span className="header-hint">
          <kbd>Ctrl</kbd> <kbd>K</kbd> rechercher · <kbd>1</kbd>–<kbd>5</kbd> écrans
        </span>
      </header>

      <IndicesStrip />

      <main className="main">
        {view === "marche" && <Watchlist onOpen={openSymbol} />}
        {view === "portefeuille" && <Portfolio onOpen={openSymbol} />}
        {view === "screener" && <Screener onOpen={openSymbol} />}
        {view === "societe" && <Company symbol={symbol} />}
        {view === "valorisation" && <Valuation symbol={symbol} />}
      </main>

      <CommandBar
        open={commandOpen}
        onClose={() => setCommandOpen(false)}
        onPick={openSymbol}
      />
    </div>
  );
}
