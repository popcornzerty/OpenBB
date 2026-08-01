"""Courbe de juste valeur historique.

Méthode, telle que spécifiée :

1. Pour chaque fondamental — bénéfices, ventes, valeur comptable, flux de
   trésorerie — le **multiple médian historique du titre** est appliqué à la
   donnée par action correspondante.
2. Les contributions sont combinées avec une pondération **inversement
   proportionnelle à la volatilité de chaque multiple** : un multiple
   historiquement stable pèse davantage.
3. La courbe est **lissée**.
4. Un facteur dérivé de la note de qualité applique une **prime** (qualité
   élevée) ou une **décote** (qualité faible), dans la limite de **±15 %**.
5. La portion projetée prolonge la courbe sur 18 mois selon sa croissance
   récente — illustratif, non prédictif.

Écart assumé par rapport à la spécification d'origine : la fenêtre de calcul
est de 5 ans et non 10. Aucune source gratuite ne publie plus de 5 exercices
pour les valeurs européennes (Yahoo s'arrête à 5, stockanalysis.com aussi en
accès libre). La fenêtre est un réglage — ``valuation_window_years`` — que le
branchement d'une source payante suffit à porter à 10 ans.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..settings import settings
from .quality import QualityScore
from .series import COMPONENTS, MULTIPLE_LABELS, FundamentalPoint, to_daily_frame

#: Un multiple doit couvrir au moins cette part de la fenêtre pour être retenu.
#:
#: Une composante présente sur une fraction seulement de la période affiche
#: mécaniquement une faible dispersion — elle n'a pas eu le temps de varier —
#: et capterait donc un poids démesuré. C'est ce qui se produisait sur les
#: banques, dont le flux de trésorerie libre n'est publié que par intermittence.
MIN_COVERAGE = 0.60

#: Plancher absolu, pour les historiques courts.
MIN_OBSERVATIONS = 120

#: Plancher sur le coefficient de variation, pour qu'un multiple quasi constant
#: n'écrase pas à lui seul la pondération.
MIN_DISPERSION = 0.05

#: Écrêtage des multiples avant calcul de la médiane et de la dispersion.
#:
#: Un exercice ponctuellement déprimé (dépréciation exceptionnelle) produit un
#: PER de plusieurs centaines qui, avec seulement quatre ou cinq exercices
#: disponibles, occupe une part telle des observations qu'il déplace la médiane
#: elle-même. L'écrêtage aux déciles extrêmes neutralise cet effet sans changer
#: la nature de la méthode.
WINSOR_LOWER, WINSOR_UPPER = 0.05, 0.95

#: Secteurs pour lesquels le flux de trésorerie libre n'a pas de sens.
#:
#: Chez une banque ou un assureur, les flux d'exploitation sont dominés par les
#: variations de bilan (dépôts, crédits) : le « FCF » qui en résulte n'est pas
#: une mesure de création de valeur et ne doit pas servir de base de valorisation.
SECTORS_WITHOUT_CASH_FLOW = {"financial services", "financials", "banks", "insurance"}


@dataclass
class ComponentResult:
    """Résultat pour un fondamental donné."""

    key: str
    label: str
    median_multiple: float
    dispersion: float
    weight: float
    current_multiple: float | None
    observations: int

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "median_multiple": round(self.median_multiple, 2),
            "dispersion": round(self.dispersion, 3),
            "weight": round(self.weight, 4),
            "current_multiple": (
                round(self.current_multiple, 2) if self.current_multiple is not None else None
            ),
            "observations": self.observations,
        }


class ValuationError(RuntimeError):
    """La juste valeur n'a pas pu être établie."""


def _price_series(history: list[dict]) -> pd.Series:
    """Série des cours de clôture, indexée par date."""
    if not history:
        raise ValuationError("Historique de cours indisponible.")
    frame = pd.DataFrame(history)
    if "date" not in frame or "close" not in frame:
        raise ValuationError("Historique de cours inexploitable.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True).dt.tz_localize(None)
    frame = frame.dropna(subset=["date", "close"]).sort_values("date")
    return pd.Series(
        frame["close"].astype("float64").to_numpy(),
        index=pd.DatetimeIndex(frame["date"]),
        name="close",
    )


def _project(curve: pd.Series, months: int) -> pd.Series:
    """Prolonge la courbe selon son rythme de croissance récent.

    Purement illustratif : c'est l'extension de la tendance passée de la juste
    valeur, pas une prévision.
    """
    curve = curve.dropna()
    if len(curve) < 60 or months <= 0:
        return pd.Series(dtype="float64")

    lookback = curve.loc[curve.index >= curve.index[-1] - pd.DateOffset(years=3)]
    if len(lookback) < 60:
        lookback = curve

    start, end = float(lookback.iloc[0]), float(lookback.iloc[-1])
    years = max((lookback.index[-1] - lookback.index[0]).days / 365.25, 0.5)
    if start <= 0 or end <= 0:
        return pd.Series(dtype="float64")

    growth = (end / start) ** (1 / years) - 1
    # Une extrapolation ne doit pas partir dans des ordres de grandeur absurdes.
    growth = max(-0.25, min(0.25, growth))

    last_date = curve.index[-1]
    future = pd.date_range(
        last_date + pd.Timedelta(days=7), periods=months * 4, freq="7D"
    )
    elapsed = np.array([(d - last_date).days / 365.25 for d in future])
    return pd.Series(end * (1 + growth) ** elapsed, index=future)


def compute(
    history: list[dict],
    points: list[FundamentalPoint],
    quality: QualityScore | None = None,
    sector: str | None = None,
) -> dict:
    """Calcule la courbe de juste valeur et ses composantes."""
    price = _price_series(history)
    window_start = price.index[-1] - pd.DateOffset(years=settings.valuation_window_years)
    price = price.loc[price.index >= window_start]
    if len(price) < MIN_OBSERVATIONS:
        raise ValuationError(
            "Historique de cours trop court pour établir des multiples fiables."
        )

    fundamentals, backfilled_until = to_daily_frame(points, price.index)

    is_financial = (sector or "").casefold() in SECTORS_WITHOUT_CASH_FLOW
    minimum = max(MIN_OBSERVATIONS, int(len(price) * MIN_COVERAGE))

    components: list[ComponentResult] = []
    fair_values: dict[str, pd.Series] = {}
    excluded: list[dict] = []

    for key in COMPONENTS:
        if key == "cash_flow" and is_financial:
            excluded.append(
                {
                    "key": key,
                    "label": MULTIPLE_LABELS[key],
                    "reason": "Flux de trésorerie libre non significatif pour une société financière.",
                }
            )
            continue

        values = fundamentals[key]
        # Un fondamental négatif ou nul ne produit pas de multiple exploitable
        # (un exercice à perte n'a pas de PER porteur de sens).
        usable = values > 0
        multiple = (price / values).where(usable)
        observations = int(multiple.notna().sum())
        if observations < minimum:
            excluded.append(
                {
                    "key": key,
                    "label": MULTIPLE_LABELS[key],
                    "reason": (
                        f"Couverture insuffisante : {observations} observations sur "
                        f"{len(price)} ({observations / len(price):.0%} de la fenêtre)."
                    ),
                }
            )
            continue

        # Écrêtage aux déciles extrêmes avant les statistiques.
        clean = multiple.dropna()
        low, high = clean.quantile(WINSOR_LOWER), clean.quantile(WINSOR_UPPER)
        clipped = clean.clip(lower=low, upper=high)

        median = float(clipped.median())
        if not math.isfinite(median) or median <= 0:
            continue

        dispersion = float(clipped.std() / abs(median))
        if not math.isfinite(dispersion):
            continue
        dispersion = max(dispersion, MIN_DISPERSION)

        current = multiple.dropna()
        components.append(
            ComponentResult(
                key=key,
                label=MULTIPLE_LABELS[key],
                median_multiple=median,
                dispersion=dispersion,
                weight=0.0,  # renseigné après normalisation
                current_multiple=float(current.iloc[-1]) if len(current) else None,
                observations=observations,
            )
        )
        fair_values[key] = (values * median).where(usable)

    if not components:
        detail = " ".join(item["reason"] for item in excluded) or ""
        raise ValuationError(
            "Aucun multiple exploitable : les fondamentaux publiés sont "
            f"insuffisants ou négatifs sur toute la période. {detail}".strip()
        )

    # Pondération inversement proportionnelle à la volatilité du multiple.
    inverse = {c.key: 1.0 / c.dispersion for c in components}
    total_inverse = sum(inverse.values())
    for component in components:
        component.weight = inverse[component.key] / total_inverse

    # Combinaison. Les poids sont renormalisés date par date sur les seules
    # composantes disponibles, pour qu'un trou dans l'une ne creuse pas la courbe.
    weighted = pd.DataFrame(
        {key: fair_values[key] * inverse[key] for key in fair_values}, index=price.index
    )
    available_weight = pd.DataFrame(
        {key: fair_values[key].notna() * inverse[key] for key in fair_values},
        index=price.index,
    ).sum(axis=1)
    raw = weighted.sum(axis=1, min_count=1) / available_weight.replace(0.0, np.nan)

    smoothed = raw.rolling(
        window=settings.valuation_smoothing_days, min_periods=1, center=True
    ).mean()

    # Prime ou décote de qualité, bornée.
    cap = settings.valuation_quality_cap
    if quality is not None:
        quality_factor = 1.0 + cap * (2.0 * quality.score / 100.0 - 1.0)
        quality_factor = max(1.0 - cap, min(1.0 + cap, quality_factor))
    else:
        quality_factor = 1.0
    curve = smoothed * quality_factor

    projection = _project(curve, settings.valuation_projection_months)

    # Restriction à la fenêtre affichée.
    display_start = price.index[-1] - pd.DateOffset(years=settings.valuation_display_years)
    curve_display = curve.loc[curve.index >= display_start]
    price_display = price.loc[price.index >= display_start]

    last_price = float(price.iloc[-1])
    last_fair = float(curve.dropna().iloc[-1]) if curve.notna().any() else None
    gap = (last_price / last_fair - 1.0) if last_fair else None

    confidence = _confidence(components, len(points))

    return {
        "currency": None,
        "window_years": settings.valuation_window_years,
        "quality_factor": round(quality_factor, 4),
        "quality": quality.as_dict() if quality is not None else None,
        "last_price": round(last_price, 4),
        "fair_value": round(last_fair, 4) if last_fair else None,
        "gap": round(gap, 4) if gap is not None else None,
        "verdict": _verdict(gap),
        "confidence": confidence,
        "components": [c.as_dict() for c in components],
        "excluded_components": excluded,
        "backfilled_until": (
            backfilled_until.date().isoformat() if backfilled_until is not None else None
        ),
        "series": {
            "dates": [d.date().isoformat() for d in price_display.index],
            "price": [_round(v) for v in price_display.tolist()],
            "fair_value": [_round(v) for v in curve_display.reindex(price_display.index)],
        },
        "projection": {
            "dates": [d.date().isoformat() for d in projection.index],
            "fair_value": [_round(v) for v in projection.tolist()],
            "note": (
                "Prolongement de la tendance récente de la juste valeur sur "
                f"{settings.valuation_projection_months} mois — illustratif, non prédictif."
            ),
        },
        "method": (
            "Multiple médian historique appliqué au fondamental par action, "
            "composantes pondérées par l'inverse de leur volatilité, courbe lissée, "
            f"puis prime ou décote de qualité bornée à ±{int(cap * 100)} %. "
            f"Fenêtre de calcul : {settings.valuation_window_years} ans. "
            "Multiples écrêtés aux déciles extrêmes ; composantes couvrant moins de "
            f"{int(MIN_COVERAGE * 100)} % de la fenêtre écartées."
        ),
        "as_of": dt.date.today().isoformat(),
    }


def _round(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else round(number, 4)


def _confidence(components: list[ComponentResult], periods: int) -> dict:
    """Qualifie la robustesse du calcul, et dit pourquoi.

    Le seul nombre qui compte vraiment ici est le nombre d'exercices publiés :
    avec quatre ou cinq, un exercice atypique — dépréciation exceptionnelle,
    année de perte — pèse un quart de l'échantillon et déplace la médiane. La
    méthode reste appliquée telle quelle, mais l'utilisateur doit le savoir.
    """
    caveats: list[str] = []

    if periods <= 4:
        level = "faible"
        caveats.append(
            f"{periods} exercices publiés seulement : un exercice atypique pèse "
            "lourdement sur les multiples médians."
        )
    elif periods == 5:
        level = "moyenne"
        caveats.append(
            "5 exercices publiés — plafond de la source gratuite. Une fenêtre de "
            "10 ans stabiliserait les médianes."
        )
    else:
        level = "bonne"

    volatile = [c.label for c in components if c.dispersion > 0.5]
    if volatile:
        caveats.append(
            "Multiples très dispersés, donc peu contributifs : "
            + ", ".join(volatile)
            + "."
        )

    if len(components) <= 2:
        level = "faible"
        caveats.append(
            f"{len(components)} composante(s) seulement ont pu être retenues."
        )

    return {"level": level, "periods_used": periods, "caveats": caveats}


def _verdict(gap: float | None) -> str:
    """Qualifie l'écart entre le cours et la juste valeur."""
    if gap is None:
        return "indeterminé"
    if gap <= -0.15:
        return "sous-évalué"
    if gap >= 0.15:
        return "surévalué"
    return "correctement valorisé"
