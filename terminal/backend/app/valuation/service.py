"""Orchestration du calcul de juste valeur pour un titre."""

from __future__ import annotations

import asyncio
import datetime as dt

from ..pea.dividends import dividend_growth, fcf_coverage, next_ex_date, safety
from ..providers import estimates, obb_source
from ..settings import settings
from . import fairvalue, multiples_history, quality, tables
from .series import build_points


async def valuation_for(symbol: str) -> dict:
    """Assemble les données nécessaires puis calcule la courbe de juste valeur."""
    # L'historique doit couvrir la fenêtre de calcul, avec une marge pour que
    # le lissage centré dispose de points de part et d'autre.
    start = dt.date.today() - dt.timedelta(
        days=int(365.25 * (settings.valuation_window_years + 1))
    )

    history, statements, metrics, profile, quote, consensus = await asyncio.gather(
        obb_source.historical(symbol, start_date=start.isoformat()),
        obb_source.statements(symbol, period="annual", limit=5),
        obb_source.metrics(symbol),
        obb_source.profile(symbol),
        obb_source.quote(symbol),
        estimates.consensus(symbol),
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

    # Le dividende éclaire la valorisation : une décote sur un titre dont le
    # dividende progresse ne se lit pas comme la même décote sur un titre qui
    # le rabote. L'échec de cette collecte ne doit pas priver de la courbe.
    dividend_block: dict | None = None
    try:
        rows = await obb_source.dividends(symbol)
        cagr, window = dividend_growth(rows)
        coverage = None
        cash_rows = statements.get("cash") or []
        if cash_rows:
            coverage = fcf_coverage(
                cash_rows[0].get("free_cash_flow"),
                cash_rows[0].get("cash_dividends_paid"),
            )
        verdict, verdict_reason = safety(
            metrics_data.get("payout_ratio"), coverage, metrics_data.get("dividend_yield")
        )
        upcoming = next_ex_date([r.get("ex_dividend_date") for r in rows])
        dividend_block = {
            "yield": metrics_data.get("dividend_yield"),
            "growth": round(cagr, 4) if cagr is not None else None,
            "growth_window": window,
            "payout_ratio": metrics_data.get("payout_ratio"),
            "fcf_coverage": (
                None if coverage is None or coverage == float("inf") else round(coverage, 3)
            ),
            "safety": verdict.value,
            "safety_reason": verdict_reason,
            "next_ex_date": upcoming.isoformat() if upcoming else None,
        }
    except Exception:  # noqa: BLE001
        dividend_block = None

    quality_score = quality.compute(statements, metrics_data)
    result = fairvalue.compute(
        history, points, quality_score, sector=profile_data.get("sector")
    )
    result["symbol"] = symbol
    result["name"] = profile_data.get("name") or symbol
    result["dividend"] = dividend_block
    result["currency"] = profile_data.get("currency") or metrics_data.get("currency")
    # Le tableau par exercice et l'évolution du PER complètent la courbe sans
    # en dépendre : leur échec ne doit pas priver de la juste valeur.
    quote_data = {} if isinstance(quote, Exception) else quote
    consensus_data = (
        {"periods": [], "price_target": {}} if isinstance(consensus, Exception) else consensus
    )
    try:
        result["tables"] = tables.build(
            statements,
            history,
            consensus_data,
            last_price=quote_data.get("last_price") or quote_data.get("prev_close"),
        )
    except Exception:  # noqa: BLE001
        result["tables"] = None

    try:
        result["per_history"] = multiples_history.compute(history, points, "earnings")
    except Exception:  # noqa: BLE001
        result["per_history"] = None

    result["periods_used"] = [
        {
            "period_ending": point.period_ending.isoformat(),
            "available_from": point.available_from.isoformat(),
            **{k: v for k, v in point.values.items()},
        }
        for point in points
    ]
    return result
