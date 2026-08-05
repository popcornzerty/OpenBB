"""Consensus des analystes, via yfinance.

Aucun fournisseur OpenBB ne publie d'estimations européennes sans clé
payante. yfinance expose en revanche le consensus Refinitiv relayé par Yahoo,
vérifié disponible sur l'ensemble de l'univers visé — grandes valeurs comme
petites capitalisations.

**Deux exercices seulement.** Yahoo publie l'exercice en cours et le suivant,
là où un Zonebourse en affiche trois ou quatre. C'est la limite de la source
gratuite, pas un choix : les colonnes au-delà resteraient vides.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
from typing import Any

from ..cache import cache
from ..settings import settings

#: Les estimations bougent lentement — une révision de consensus se compte en
#: jours. Un TTL long évite de marteler Yahoo sans rien perdre d'utile.
TTL_SECONDS = 6 * 3600

#: Nombre minimal d'analystes pour qu'une estimation soit publiée telle
#: quelle. En dessous, la moyenne est celle d'une poignée de bureaux et le
#: consensus n'en est pas un : l'information reste affichée, mais signalée.
THIN_COVERAGE = 3


def _number(value: Any) -> float | None:
    """Convertit en flottant fini, sinon ``None``."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _row(frame, period: str, column: str) -> float | None:
    """Lit une cellule du tableau d'estimations, absente ou vide comprise."""
    try:
        if frame is None or period not in frame.index or column not in frame.columns:
            return None
        return _number(frame.loc[period, column])
    except Exception:  # noqa: BLE001
        return None


def _fetch(symbol: str) -> dict:
    """Interroge yfinance. Synchrone : appelé dans un thread."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    eps = ticker.earnings_estimate
    revenue = ticker.revenue_estimate

    # L'exercice de référence de Yahoo est l'exercice fiscal en cours. Sans
    # sa date de clôture on ne saurait pas à quelle année rattacher « 0y ».
    fiscal_year_end = None
    try:
        info = ticker.info or {}
        raw = info.get("lastFiscalYearEnd")
        if raw:
            fiscal_year_end = dt.date.fromtimestamp(int(raw))
    except Exception:  # noqa: BLE001
        info = {}

    targets = {}
    try:
        targets = ticker.analyst_price_targets or {}
    except Exception:  # noqa: BLE001
        targets = {}

    periods = []
    for offset, key in ((0, "0y"), (1, "+1y")):
        eps_avg = _row(eps, key, "avg")
        revenue_avg = _row(revenue, key, "avg")
        if eps_avg is None and revenue_avg is None:
            continue
        analysts = _row(eps, key, "numberOfAnalysts") or _row(
            revenue, key, "numberOfAnalysts"
        )
        periods.append(
            {
                "offset": offset,
                "eps": eps_avg,
                "eps_low": _row(eps, key, "low"),
                "eps_high": _row(eps, key, "high"),
                "eps_growth": _row(eps, key, "growth"),
                # Le bénéfice de l'exercice précédent sert d'ancrage : il doit
                # coïncider avec le dernier exercice publié, faute de quoi les
                # colonnes estimées seraient décalées d'un an.
                "year_ago_eps": _row(eps, key, "yearAgoEps"),
                "revenue": revenue_avg,
                "revenue_growth": _row(revenue, key, "growth"),
                "analysts": int(analysts) if analysts else None,
                "thin": bool(analysts and analysts < THIN_COVERAGE),
            }
        )

    return {
        "periods": periods,
        "fiscal_year_end": fiscal_year_end.isoformat() if fiscal_year_end else None,
        "price_target": {
            "mean": _number(targets.get("mean")),
            "median": _number(targets.get("median")),
            "low": _number(targets.get("low")),
            "high": _number(targets.get("high")),
            "current": _number(targets.get("current")),
        },
        "currency": (info.get("financialCurrency") or info.get("currency") or None),
    }


async def consensus(symbol: str) -> dict:
    """Estimations de bénéfice et de chiffre d'affaires, et cible de cours.

    Renvoie toujours une structure exploitable : un titre non suivi donne une
    liste de périodes vide, pas une exception. L'écran doit pouvoir afficher
    l'historique même sans consensus.
    """

    async def produce():
        try:
            return await asyncio.to_thread(_fetch, symbol)
        except Exception:  # noqa: BLE001
            return {
                "periods": [],
                "fiscal_year_end": None,
                "price_target": {},
                "currency": None,
            }

    key = f"estimates:v1:{symbol}"
    value, _, _ = await cache.resolve(key, TTL_SECONDS, produce)
    return value


__all__ = ["consensus", "TTL_SECONDS", "THIN_COVERAGE"]
