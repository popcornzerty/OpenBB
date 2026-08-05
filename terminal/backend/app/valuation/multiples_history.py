"""Évolution d'un multiple dans le temps, et sa moyenne historique.

Savoir qu'un titre se paie 21 fois ses bénéfices ne dit rien seul. Ce qui
renseigne, c'est l'écart à ce qu'il s'est payé habituellement : le même PER
de 21 est cher sur une valeur qui traite d'ordinaire à 14, et bon marché sur
une qui traite à 30.

La série est construite sur la même grille que la courbe de juste valeur —
fondamentaux propagés à partir de leur date de publication, jamais avant.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .series import COMPONENTS, MULTIPLE_LABELS, FundamentalPoint, to_daily_frame

#: Bornes de winsorisation des statistiques. Un exercice de transition peut
#: propulser un PER à 400 pendant quelques semaines ; laissé tel quel, il
#: déplacerait la moyenne de plusieurs points. La courbe affichée, elle,
#: reste brute : c'est un fait de marché, pas une anomalie à masquer.
WINSOR_LOWER, WINSOR_UPPER = 0.02, 0.98

#: En deçà, la moyenne n'a pas de sens statistique.
MIN_OBSERVATIONS = 120

#: Un multiple au-delà n'est plus une valorisation mais le symptôme d'un
#: dénominateur qui s'effondre.
MAX_MULTIPLE = 300.0


def _price_series(history: list[dict]) -> pd.Series:
    rows = [
        (str(row.get("date"))[:10], row.get("close"))
        for row in history
        if row.get("date") is not None and row.get("close") is not None
    ]
    if not rows:
        return pd.Series(dtype=float)
    series = pd.Series(
        [float(value) for _, value in rows],
        index=pd.to_datetime([day for day, _ in rows]),
        dtype="float64",
    )
    return series[~series.index.duplicated(keep="last")].sort_index()


def compute(
    history: list[dict],
    points: list[FundamentalPoint],
    component: str = "earnings",
    window_years: int = 5,
) -> dict | None:
    """Série du multiple, sa moyenne, sa médiane et l'écart courant.

    Renvoie ``None`` quand l'historique ne permet pas d'établir une moyenne
    défendable — mieux vaut ne rien afficher qu'une référence bâtie sur une
    poignée de points.
    """
    if component not in COMPONENTS:
        raise ValueError(f"Composante inconnue : {component}")

    prices = _price_series(history)
    if prices.empty or not points:
        return None

    frame, backfilled_until = to_daily_frame(points, prices.index)
    fundamental = frame[component]

    # Un fondamental négatif ou nul ne produit pas de multiple : la courbe
    # s'interrompt, elle ne plonge pas sous zéro.
    usable = fundamental > 0
    multiple = (prices / fundamental).where(usable)
    multiple = multiple.where(np.isfinite(multiple) & (multiple <= MAX_MULTIPLE))

    # Fenêtre d'affichage demandée, bornée à ce dont on dispose.
    horizon = multiple.index[-1] - pd.DateOffset(years=window_years)
    multiple = multiple[multiple.index >= horizon]

    clean = multiple.dropna()
    if len(clean) < MIN_OBSERVATIONS:
        return None

    # La moyenne ne porte que sur la période réellement adossée à des comptes
    # publiés. Avant la parution du plus ancien exercice disponible, la série
    # applique ces comptes rétroactivement : les inclure reviendrait à
    # comparer le PER d'aujourd'hui à une référence en partie fabriquée.
    reference = clean
    stats_backfilled = False
    if backfilled_until is not None:
        genuine = clean[clean.index > backfilled_until]
        if len(genuine) >= MIN_OBSERVATIONS:
            reference = genuine
        else:
            # Trop peu de points publiés : on garde tout, en le disant.
            stats_backfilled = True

    lower = float(reference.quantile(WINSOR_LOWER))
    upper = float(reference.quantile(WINSOR_UPPER))
    trimmed = reference.clip(lower, upper)

    average = float(trimmed.mean())
    median = float(trimmed.median())
    deviation = float(trimmed.std())
    current = float(clean.iloc[-1])

    if not all(math.isfinite(v) for v in (average, median, current)) or average <= 0:
        return None

    # Une fréquence hebdomadaire suffit à lire une tendance sur cinq ans et
    # divise par cinq le volume transmis au client.
    weekly = multiple.resample("W-FRI").last()
    series = [
        {"date": stamp.date().isoformat(), "value": round(float(value), 3)}
        for stamp, value in weekly.items()
        if value is not None and not pd.isna(value)
    ]

    first, last = clean.index[0], clean.index[-1]
    return {
        "component": component,
        "label": MULTIPLE_LABELS[component],
        "series": series,
        "current": round(current, 2),
        "average": round(average, 2),
        "median": round(median, 2),
        "stdev": round(deviation, 2) if math.isfinite(deviation) else None,
        # Profondeur réelle de la moyenne, distincte de celle du graphique.
        "reference_from": reference.index[0].date().isoformat(),
        "reference_years": round(
            (reference.index[-1] - reference.index[0]).days / 365.25, 1
        ),
        "reference_observations": int(len(reference)),
        "stats_backfilled": stats_backfilled,
        # Écart au multiple habituel : positif, le titre se paie plus cher
        # que d'ordinaire.
        "gap_to_average": round((current - average) / average, 4),
        "gap_to_median": round((current - median) / median, 4),
        "band_low": round(average - deviation, 2) if math.isfinite(deviation) else None,
        "band_high": round(average + deviation, 2) if math.isfinite(deviation) else None,
        "min": round(float(clean.min()), 2),
        "max": round(float(clean.max()), 2),
        "observations": int(len(clean)),
        "coverage": round(len(clean) / len(multiple), 3) if len(multiple) else None,
        "from": first.date().isoformat(),
        "to": last.date().isoformat(),
        "years": round((last - first).days / 365.25, 1),
        "backfilled_until": (
            backfilled_until.date().isoformat() if backfilled_until is not None else None
        ),
    }


__all__ = ["compute", "MIN_OBSERVATIONS", "MAX_MULTIPLE"]
