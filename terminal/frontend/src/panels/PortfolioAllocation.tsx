import { useEffect, useState } from "react";
import { api, type Allocation, type AllocationComparison } from "../lib/api";
import { compact, pct } from "../lib/format";

/** Répartition sectorielle et géographique, confrontée à vos cibles.
 *
 *  Les fonds sont ventilés selon leur composition publiée : sans cette
 *  transparence, un portefeuille majoritairement logé en ETF verrait
 *  l'essentiel de son encours classé « inconnu ». */
export function PortfolioAllocation() {
  const [data, setData] = useState<Allocation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [axis, setAxis] = useState<"sectors" | "regions">("sectors");
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const result = await api.allocation();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (error) return <div className="callout error">{error}</div>;
  if (!data) return <div className="spinner">Analyse de la répartition…</div>;

  const rows = axis === "sectors" ? data.sector_comparison : data.region_comparison;
  const targetsTotal =
    axis === "sectors" ? data.targets_total.sectors : data.targets_total.regions;

  const value = (label: string) =>
    draft[label] ?? String(Math.round(((axis === "sectors"
      ? data.targets.sectors[label]
      : data.targets.regions[label]) ?? 0) * 1000) / 10);

  const saveTargets = async () => {
    setSaving(true);
    try {
      const current = { ...data.targets };
      const updated: Record<string, number> = {};
      for (const row of rows) {
        const raw = draft[row.label];
        const kept =
          raw !== undefined
            ? Number(raw.replace(",", ".")) / 100
            : (axis === "sectors" ? current.sectors : current.regions)[row.label];
        if (kept && kept > 0) updated[row.label] = kept;
      }
      await api.saveTargets(
        axis === "sectors" ? updated : current.sectors,
        axis === "regions" ? updated : current.regions,
      );
      setDraft({});
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="stack">
      <div className="panel">
        <div className="panel-head">
          <span className="panel-title">Répartition</span>
          <div className="chips">
            <button
              className={`chip ${axis === "sectors" ? "active" : ""}`}
              onClick={() => { setAxis("sectors"); setDraft({}); }}
            >
              Secteurs
            </button>
            <button
              className={`chip ${axis === "regions" ? "active" : ""}`}
              onClick={() => { setAxis("regions"); setDraft({}); }}
            >
              Zones géographiques
            </button>
          </div>
          <span className="spacer" style={{ flex: 1 }} />
          <span className="note">
            cible cumulée {pct(targetsTotal, 0).replace("+", "")}
          </span>
          <button className="chip" onClick={saveTargets} disabled={saving}>
            {saving ? "Enregistrement…" : "Enregistrer les cibles"}
          </button>
        </div>

        <div className="panel-body flush table-wrap">
          <table>
            <thead>
              <tr>
                <th>{axis === "sectors" ? "Secteur" : "Zone"}</th>
                <th className="right">Encours</th>
                <th className="right">Part</th>
                <th style={{ width: 200 }}>Répartition</th>
                <th className="right" style={{ width: 110 }}>Cible %</th>
                <th className="right">Écart</th>
                <th>Principales lignes</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Row
                  key={row.label}
                  row={row}
                  contributors={
                    (axis === "sectors" ? data.sectors : data.regions).find(
                      (s) => s.label === row.label,
                    )?.contributors ?? []
                  }
                  draft={value(row.label)}
                  onDraft={(v) => setDraft((d) => ({ ...d, [row.label]: v }))}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="note">
        {data.note} La transparence porte sur {pct(data.look_through_share, 0).replace("+", "")}{" "}
        de l'encours — la part logée dans des fonds. {pct(data.classified_share, 0).replace("+", "")}{" "}
        de l'encours est classé.
        {targetsTotal > 0 && Math.abs(targetsTotal - 1) > 0.01 && (
          <>
            {" "}Vos cibles totalisent {pct(targetsTotal, 0).replace("+", "")} : ce n'est pas
            une erreur si vous ne visez qu'une partie du portefeuille, mais l'écart affiché
            se lit alors relativement à cette base.
          </>
        )}
      </div>

      <div className="note">
        Il n'existe pas d'allocation optimale universelle : ces cibles sont les vôtres, le
        terminal se contente de mesurer l'écart. Il ne recommande rien.
      </div>
    </div>
  );
}

function Row({
  row,
  contributors,
  draft,
  onDraft,
}: {
  row: AllocationComparison;
  contributors: string[];
  draft: string;
  onDraft: (value: string) => void;
}) {
  const gap = row.gap;
  return (
    <tr>
      <td>{row.label}</td>
      <td className="right num dim">{compact(row.value, "€")}</td>
      <td className="right num">{pct(row.share, 1).replace("+", "")}</td>
      <td>
        <div className="bar" style={{ position: "relative" }}>
          <span style={{ width: `${Math.min(row.share * 100, 100)}%` }} />
          {row.target !== null && (
            // Repère de la cible, posé sur la même échelle que la barre.
            <i
              style={{
                position: "absolute",
                left: `${Math.min(row.target * 100, 100)}%`,
                top: -2,
                bottom: -2,
                width: 2,
                background: "var(--amber)",
              }}
              title={`Cible ${pct(row.target, 1).replace("+", "")}`}
            />
          )}
        </div>
      </td>
      <td className="right">
        <input
          value={draft}
          onChange={(event) => onDraft(event.target.value)}
          inputMode="decimal"
          className="num"
          style={{ width: 70, textAlign: "right" }}
          aria-label={`Cible pour ${row.label}`}
        />
      </td>
      <td className={`right num ${gap === null ? "" : gap > 0 ? "down" : "up"}`}>
        {gap === null ? "—" : pct(gap, 1)}
      </td>
      <td className="faint">
        {contributors.length ? contributors.slice(0, 3).join(", ") : "—"}
      </td>
    </tr>
  );
}
