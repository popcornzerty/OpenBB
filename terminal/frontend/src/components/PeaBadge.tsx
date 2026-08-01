import type { PeaStatus } from "../lib/api";
import { PEA_LABEL } from "../lib/format";

/** Pastille d'éligibilité PEA. Le titre au survol porte la justification :
 *  l'utilisateur doit pouvoir savoir *pourquoi* un titre est classé ainsi. */
export function PeaBadge({
  status,
  reason,
  compact = false,
}: {
  status: PeaStatus;
  reason?: string;
  compact?: boolean;
}) {
  return (
    <span className={`badge ${status}`} title={reason}>
      <span className="dot" />
      {compact ? (status === "eligible" ? "PEA" : status === "non_eligible" ? "Hors" : "?") : PEA_LABEL[status]}
    </span>
  );
}
