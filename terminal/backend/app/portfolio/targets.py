"""Pondérations cibles définies par l'utilisateur.

Il n'existe pas d'allocation optimale universelle : une cible que le terminal
inventerait aurait l'apparence d'un conseil sans en être un. Ce sont donc vos
cibles, saisies par vous, et le terminal se contente de mesurer l'écart.
"""

from __future__ import annotations

import json
from threading import Lock

from ..settings import settings

_lock = Lock()


def _path():
    return settings.state_dir / "allocation_targets.json"


def load() -> dict[str, dict[str, float]]:
    """Cibles enregistrées, par axe (``sectors``, ``regions``)."""
    path = _path()
    if not path.exists():
        return {"sectors": {}, "regions": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"sectors": {}, "regions": {}}
    return {
        "sectors": {k: float(v) for k, v in (raw.get("sectors") or {}).items()},
        "regions": {k: float(v) for k, v in (raw.get("regions") or {}).items()},
    }


def save(targets: dict[str, dict[str, float]]) -> dict:
    """Enregistre les cibles. Une cible nulle ou négative est retirée."""
    with _lock:
        cleaned = {
            axis: {k: float(v) for k, v in (targets.get(axis) or {}).items() if float(v) > 0}
            for axis in ("sectors", "regions")
        }
        _path().write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return cleaned


def compare(slices: list[dict], targets: dict[str, float]) -> list[dict]:
    """Confronte la répartition réelle aux cibles.

    Les libellés présents d'un seul côté apparaissent quand même : une cible
    non pourvue est aussi informative qu'une exposition non voulue, et la
    masquer reviendrait à cacher précisément ce qu'on cherche à voir.
    """
    actual = {s["label"]: s["share"] for s in slices}
    values = {s["label"]: s["value"] for s in slices}

    rows = []
    for label in sorted(set(actual) | set(targets)):
        current = actual.get(label, 0.0)
        target = targets.get(label)
        rows.append(
            {
                "label": label,
                "share": round(current, 4),
                "value": round(values.get(label, 0.0), 2),
                "target": round(target, 4) if target is not None else None,
                "gap": round(current - target, 4) if target is not None else None,
            }
        )

    # Les écarts les plus criants d'abord ; à défaut de cible, par poids.
    rows.sort(key=lambda r: (r["gap"] is None, -abs(r["gap"] or 0), -r["share"]))
    return rows


def total(targets: dict[str, float]) -> float:
    return round(sum(targets.values()), 4)
