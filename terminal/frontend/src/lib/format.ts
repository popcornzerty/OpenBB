/** Formatage francophone des nombres, montants et dates. */

const NBSP = " "; // espace fine insécable, séparateur de milliers français

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("fr-FR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function pct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${num(value * 100, digits)}${NBSP}%`;
}

/** Pourcentage déjà exprimé en points (12.5 pour 12,5 %). */
export function pctPoints(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value >= 0 ? "+" : ""}${num(value, digits)}${NBSP}%`;
}

/** Capitalisations et volumes : abrégés pour rester lisibles en tableau. */
export function compact(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const symbol = unit === "EUR" ? "€" : unit;
  const suffix = symbol ? NBSP + symbol : "";
  if (abs >= 1e12) return `${num(value / 1e12, 2)}${NBSP}T${suffix}`;
  if (abs >= 1e9) return `${num(value / 1e9, 1)}${NBSP}Md${suffix}`;
  if (abs >= 1e6) return `${num(value / 1e6, 1)}${NBSP}M${suffix}`;
  if (abs >= 1e3) return `${num(value / 1e3, 1)}${NBSP}k${suffix}`;
  return `${num(value, 0)}${suffix}`;
}

function withCurrency(value: number, currency: string | null, digits: number): string {
  const symbol = currency === "EUR" ? "€" : currency ? NBSP + currency : "";
  return `${num(value, digits)}${currency === "EUR" ? NBSP + symbol : symbol}`;
}

/** Montant en portefeuille : toujours au centime.
 *
 *  Un encours ou un dividende encaissé se lit en euros et centimes. Y ajouter
 *  une troisième décimale — « 96,000 € », « 0,000 € » — suggère une précision
 *  qui n'existe pas. */
export function money(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return withCurrency(value, currency, 2);
}

/** Cours ou donnée par action : trois décimales sous 100.
 *
 *  Un titre à 6,81 € et un dividende de 0,45 €/action perdent une information
 *  utile au centime près. Le seuil porte sur la magnitude, sans quoi une
 *  valeur de -774,40 € passerait dessous et s'afficherait « -774,400 € ». */
export function price(value: number | null | undefined, currency: string | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return withCurrency(value, currency, value !== 0 && Math.abs(value) < 100 ? 3 : 2);
}

export function date(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10);
  return parsed.toLocaleDateString("fr-FR", { day: "2-digit", month: "short", year: "numeric" });
}

export function time(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

export function changeClass(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (value > 0) return "up";
  if (value < 0) return "down";
  return "";
}

export const PEA_LABEL: Record<string, string> = {
  eligible: "PEA éligible",
  non_eligible: "Hors PEA",
  inconnu: "PEA indéterminé",
};
