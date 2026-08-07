import { useEffect, useMemo, useRef, useState } from "react";
import {
  CATEGORY_LABELS,
  LOCATION_LABELS,
  type GlossaryCategory,
  type GlossaryEntry,
  glossaryEntries,
  searchGlossary,
} from "../data/glossary";

type Filtre = "tous" | GlossaryCategory;

const FILTRES: { id: Filtre; label: string }[] = [
  { id: "tous", label: "Tous" },
  { id: "dividendes", label: CATEGORY_LABELS.dividendes },
  { id: "fondamentaux", label: CATEGORY_LABELS.fondamentaux },
  { id: "valorisation", label: CATEGORY_LABELS.valorisation },
  { id: "risque", label: CATEGORY_LABELS.risque },
  { id: "donnees", label: CATEGORY_LABELS.donnees },
];

/** Glossaire des indicateurs du terminal.
 *
 *  Les écrans affichent des sigles et des ratios sans les expliquer : un
 *  « P/B » ou un « flux libre absorbé » n'a de sens que pour qui le connaît
 *  déjà. Cette page est le renvoi commun de tous ces marqueurs. */
export function Glossary({
  focus,
}: {
  /** Fiche à ouvrir. Le compteur distingue deux demandes identiques :
   *  sans lui, recliquer le même renvoi ne ramènerait pas la fiche. */
  focus?: { id: string; n: number } | null;
}) {
  const [requete, setRequete] = useState("");
  const [filtre, setFiltre] = useState<Filtre>("tous");
  const [ouverts, setOuverts] = useState<Set<string>>(new Set());
  const champ = useRef<HTMLInputElement>(null);
  const fiches = useRef<Map<string, HTMLDivElement>>(new Map());

  // Arriver depuis un renvoi contextuel doit ouvrir la fiche visée et
  // l'amener sous les yeux : la laisser repliée au milieu de quarante autres
  // reviendrait à ne pas y avoir mené.
  useEffect(() => {
    if (!focus) return;
    setRequete("");
    setFiltre("tous");
    setOuverts((actuels) => new Set(actuels).add(focus.id));
    // Le rendu de la fiche dépliée précède le défilement.
    const minuteur = setTimeout(() => {
      fiches.current
        .get(focus.id)
        ?.scrollIntoView({ block: "center", behavior: "smooth" });
    }, 60);
    return () => clearTimeout(minuteur);
  }, [focus]);

  const resultats = useMemo(() => {
    const trouves = searchGlossary(requete);
    return filtre === "tous"
      ? trouves
      : trouves.filter((entry) => entry.category === filtre);
  }, [requete, filtre]);

  const basculer = (id: string) =>
    setOuverts((actuels) => {
      const suivant = new Set(actuels);
      if (suivant.has(id)) suivant.delete(id);
      else suivant.add(id);
      return suivant;
    });

  const compte = (id: Filtre) =>
    id === "tous"
      ? glossaryEntries.length
      : glossaryEntries.filter((entry) => entry.category === id).length;

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Glossaire</span>
          <span className="spacer" style={{ flex: 1 }} />
          <span className="note">{resultats.length} terme(s)</span>
        </div>

        <div className="panel-body stack" style={{ gap: 10 }}>
          <div className="note" style={{ marginTop: 0 }}>
            Les indicateurs affichés dans le terminal, expliqués simplement.
          </div>

          <input
            ref={champ}
            value={requete}
            onChange={(event) => setRequete(event.target.value)}
            placeholder="Rechercher un terme ou un sigle…"
            aria-label="Rechercher dans le glossaire"
          />

          <div className="chips">
            {FILTRES.map((item) => (
              <button
                key={item.id}
                className={`chip ${filtre === item.id ? "active" : ""}`}
                onClick={() => setFiltre(item.id)}
              >
                {item.label} <span className="faint">{compte(item.id)}</span>
              </button>
            ))}
          </div>
        </div>

        {resultats.length === 0 ? (
          <div className="panel-body">
            <div className="callout">
              Aucun terme ne correspond à « {requete.trim()} ». Les sigles sont
              recherchables — essayez « P/B », « FCF » ou « EPS ».
            </div>
          </div>
        ) : (
          <div className="panel-body stack" style={{ gap: 4 }}>
            {resultats.map((entry) => (
              <Fiche
                key={entry.id}
                entry={entry}
                ouverte={ouverts.has(entry.id)}
                onBasculer={() => basculer(entry.id)}
                enregistrer={(element) => {
                  if (element) fiches.current.set(entry.id, element);
                  else fiches.current.delete(entry.id);
                }}
              />
            ))}
          </div>
        )}
      </div>

      <div className="note">
        Ce glossaire décrit ce que le terminal affiche. Il n'énonce aucune
        recommandation d'achat ou de vente, et les indicateurs maison — sûreté du
        dividende, note qualité, juste valeur — y sont signalés comme tels.
      </div>
    </div>
  );
}

function Fiche({
  entry,
  ouverte,
  onBasculer,
  enregistrer,
}: {
  entry: GlossaryEntry;
  ouverte: boolean;
  onBasculer: () => void;
  enregistrer: (element: HTMLDivElement | null) => void;
}) {
  return (
    <div className="glossaire-fiche" id={`glossaire-${entry.id}`} ref={enregistrer}>
      <button
        type="button"
        className={`glossaire-entete ${ouverte ? "ouverte" : ""}`}
        onClick={onBasculer}
        aria-expanded={ouverte}
      >
        <span className="glossaire-chevron">{ouverte ? "▾" : "▸"}</span>
        <span className="glossaire-terme">{entry.term}</span>
        {entry.aliases && entry.aliases.length > 0 && (
          <span className="faint glossaire-alias">{entry.aliases.join(" · ")}</span>
        )}
        <span className="spacer" style={{ flex: 1 }} />
        <span className="badge plain">{CATEGORY_LABELS[entry.category]}</span>
      </button>

      {ouverte && (
        <div className="glossaire-corps">
          <p>{entry.definition}</p>

          {entry.formula && (
            <p className="glossaire-formule">
              <span className="faint">Calcul</span>
              <code>{entry.formula}</code>
            </p>
          )}

          <p className="note" style={{ marginTop: 0 }}>
            Affiché dans :{" "}
            {entry.locations.map((lieu) => LOCATION_LABELS[lieu]).join(", ")}.
          </p>

          {/* La mise en garde est le seul élément coloré de la fiche : c'est
              ce qu'on lit quand on a déjà compris la définition. */}
          {entry.caution && <p className="glossaire-garde">{entry.caution}</p>}
        </div>
      )}
    </div>
  );
}
