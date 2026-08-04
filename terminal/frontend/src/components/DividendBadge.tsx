import type { DividendSafety } from "../lib/api";

const LABELS: Record<DividendSafety, string> = {
  sur: "Sûr",
  tendu: "Tendu",
  non_couvert: "Non couvert",
  inconnu: "?",
  aucun: "—",
};

/** Pastille de sûreté du dividende.
 *
 *  Vert : le dividende tient dans le résultat et dans la trésorerie générée.
 *  Orange : il est couvert mais absorbe une large part de l'un ou de l'autre.
 *  Rouge : il dépasse le résultat, ou le flux de trésorerie libre ne suffit pas.
 *
 *  La justification est portée par l'infobulle : une couleur sans motif
 *  n'aide pas à décider. */
export function DividendBadge({
  safety,
  reason,
}: {
  safety: DividendSafety;
  reason?: string;
}) {
  if (safety === "aucun") {
    return (
      <span className="faint" title="Cette société ne verse pas de dividende.">
        —
      </span>
    );
  }
  return (
    <span className={`badge dividend-${safety}`} title={reason}>
      <span className="dot" />
      {LABELS[safety]}
    </span>
  );
}
