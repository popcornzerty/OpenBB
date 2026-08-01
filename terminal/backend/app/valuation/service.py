"""Orchestration du calcul de juste valeur pour un titre."""

from __future__ import annotations

import asyncio
import datetime as dt

from ..providers import obb_source
from ..settings import settings
from . import fairvalue, quality
from .series import build_points


async def valuation_for(symbol: str) -> dict:
    """Assemble les données nécessaires puis calcule la courbe de juste valeur."""
    # L'historique doit couvrir la fenêtre de calcul, avec une marge pour que
    # le lissage centré dispose de points de part et d'autre.
    start = dt.date.today() - dt.timedelta(
        days=int(365.25 * (settings.valuation_window_years + 1))
    )

    history, statements, metrics, profile = await asyncio.gather(
        obb_source.historical(symbol, start_date=start.isoformat()),
        obb_source.statements(symbol, period="annual", limit=5),
        obb_source.metrics(symbol),
        obb_source.profile(symbol),
        return_exceptions=True,
    )

    if isinstance(history, Exception):
        raise fairvalue.ValuationError(
            f"Historique de cours indisponible pour {symbol}."
        ) from history
    if isinstance(statements, Exception) or not any(statements.values()):
        raise fairvalue.ValuationError(
            f"États financiers indisponibles pour {symbol}."
        )

    metrics_data = {} if isinstance(metrics, Exception) else metrics
    profile_data = {} if isinstance(profile, Exception) else profile

    points = build_points(statements)
    if not points:
        raise fairvalue.ValuationError(
            f"Aucun fondamental par action exploitable pour {symbol} "
            "(nombre d'actions ou comptes manquants)."
        )

    quality_score = quality.compute(statements, metrics_data)
    result = fairvalue.compute(
        history, points, quality_score, sector=profile_data.get("sector")
    )
    result["symbol"] = symbol
    result["name"] = profile_data.get("name") or symbol
    result["currency"] = profile_data.get("currency") or metrics_data.get("currency")
    result["periods_used"] = [
        {
            "period_ending": point.period_ending.isoformat(),
            "available_from": point.available_from.isoformat(),
            **{k: v for k, v in point.values.items()},
        }
        for point in points
    ]
    return result
