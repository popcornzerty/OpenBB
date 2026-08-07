import { useState } from "react";
import { glossaryById } from "../data/glossary";

/** Renvoi contextuel vers une fiche du glossaire.
 *
 *  Posé à côté d'un indicateur technique, il donne la définition courte au
 *  survol et mène à la fiche complète au clic. Un terme qu'on ne comprend pas
 *  doit s'expliquer là où on le rencontre, pas au prix d'une recherche. */
export function GlossaryHint({
  id,
  onOpen,
}: {
  id: string;
  /** Ouvre le glossaire sur cette fiche. Absent, le renvoi reste informatif. */
  onOpen?: (id: string) => void;
}) {
  const entry = glossaryById[id];
  const [ouvert, setOuvert] = useState(false);
  // Un identifiant inconnu ne doit rien afficher plutôt qu'une bulle vide :
  // renommer une fiche ne doit pas laisser de marqueur orphelin dans l'écran.
  if (!entry) return null;

  return (
    <span
      className="glossaire-renvoi"
      onMouseEnter={() => setOuvert(true)}
      onMouseLeave={() => setOuvert(false)}
    >
      <button
        type="button"
        className="glossaire-icone"
        aria-label={`Définition de ${entry.term}`}
        onClick={(event) => {
          event.stopPropagation();
          onOpen?.(id);
        }}
      >
        ⓘ
      </button>
      {ouvert && (
        <span className="glossaire-bulle" role="tooltip">
          <strong>{entry.term}</strong>
          <span>{entry.definition}</span>
          {entry.formula && <code>{entry.formula}</code>}
          {entry.caution && <em>{entry.caution}</em>}
          {onOpen && <span className="faint">Cliquer pour ouvrir la fiche</span>}
        </span>
      )}
    </span>
  );
}
