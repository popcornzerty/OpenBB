import { useCallback, useEffect, useState } from "react";
import { CommandBar } from "./components/CommandBar";
import { IndicesStrip } from "./components/IndicesStrip";
import { Company } from "./panels/Company";
import { Glossary } from "./panels/Glossary";
import { Portfolio } from "./panels/Portfolio";
import { Screener } from "./panels/Screener";
import { Valuation } from "./panels/Valuation";
import { Market } from "./panels/Market";

type View =
  | "marche"
  | "portefeuille"
  | "screener"
  | "societe"
  | "valorisation"
  | "glossaire";

const VIEWS: { id: View; label: string; key: string }[] = [
  { id: "marche", label: "Marché", key: "1" },
  { id: "portefeuille", label: "Portefeuille", key: "2" },
  { id: "screener", label: "Screener PEA", key: "3" },
  { id: "societe", label: "Société", key: "4" },
  { id: "valorisation", label: "Valorisation", key: "5" },
  { id: "glossaire", label: "Glossaire", key: "6" },
];

export default function App() {
  const [view, setView] = useState<View>("marche");
  const [symbol, setSymbol] = useState("MC.PA");
  const [commandOpen, setCommandOpen] = useState(false);
  // Fiche du glossaire à ouvrir, quand on y arrive depuis un renvoi
  // contextuel. Un compteur accompagne l'identifiant : cliquer deux fois sur
  // le même renvoi doit ramener la fiche à l'écran, or une valeur inchangée
  // ne déclencherait aucun effet.
  const [glossaryFocus, setGlossaryFocus] = useState<{ id: string; n: number } | null>(
    null,
  );

  const openSymbol = useCallback((next: string) => {
    setSymbol(next);
    setView("societe");
  }, []);

  const openGlossary = useCallback((id: string) => {
    setGlossaryFocus((current) => ({ id, n: (current?.n ?? 0) + 1 }));
    setView("glossaire");
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
          <kbd>Ctrl</kbd> <kbd>K</kbd> rechercher · <kbd>1</kbd>–<kbd>6</kbd> écrans
        </span>
      </header>

      <IndicesStrip />

      <main className="main">
        {view === "marche" && <Market onOpen={openSymbol} />}
        {view === "portefeuille" && <Portfolio onOpen={openSymbol} />}
        {view === "screener" && (
          <Screener onOpen={openSymbol} onGlossary={openGlossary} />
        )}
        {view === "societe" && <Company symbol={symbol} onGlossary={openGlossary} />}
        {view === "valorisation" && (
          <Valuation symbol={symbol} onGlossary={openGlossary} />
        )}
        {view === "glossaire" && <Glossary focus={glossaryFocus} />}
      </main>

      <CommandBar
        open={commandOpen}
        onClose={() => setCommandOpen(false)}
        onPick={openSymbol}
        onGlossary={openGlossary}
      />
    </div>
  );
}
