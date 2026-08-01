"""Fiche société : profil, statut PEA, fondamentaux, dividendes, actualités."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..pea.eligibility import assess
from ..providers import obb_source

router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/{symbol}")
async def get_company(symbol: str) -> dict:
    """Profil de la société, accompagné du verdict PEA et des ratios courants."""
    profile, metrics, quote = await asyncio.gather(
        obb_source.profile(symbol),
        obb_source.metrics(symbol),
        obb_source.quote(symbol),
        return_exceptions=True,
    )

    if isinstance(profile, Exception):
        raise HTTPException(404, f"Société introuvable : {symbol}")

    status = assess(symbol, profile.get("hq_country"))
    return {
        "symbol": symbol,
        "profile": profile,
        "pea": status.as_dict(),
        "metrics": {} if isinstance(metrics, Exception) else metrics,
        "quote": None if isinstance(quote, Exception) else quote,
    }


@router.get("/{symbol}/fundamentals")
async def get_fundamentals(
    symbol: str,
    period: str = Query("annual", pattern="^(annual|quarter)$"),
) -> dict:
    """Compte de résultat, bilan et tableau de flux.

    Cinq exercices au maximum : c'est la profondeur publiée par la source
    gratuite, pas un choix d'affichage.
    """
    statements = await obb_source.statements(symbol, period=period, limit=5)
    if not any(statements.values()):
        raise HTTPException(404, f"États financiers indisponibles pour {symbol}")
    return {
        "symbol": symbol,
        "period": period,
        **statements,
        "note": "Profondeur limitée à 5 exercices par la source de données.",
    }


@router.get("/{symbol}/dividends")
async def get_dividends(symbol: str) -> dict:
    """Historique des dividendes."""
    try:
        rows = await obb_source.dividends(symbol)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Dividendes indisponibles pour {symbol}") from exc
    return {"symbol": symbol, "rows": rows}


@router.get("/{symbol}/news")
async def get_news(symbol: str, limit: int = Query(20, ge=1, le=100)) -> dict:
    """Actualités liées au titre."""
    try:
        rows = await obb_source.news(symbol, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Actualités indisponibles pour {symbol}") from exc
    return {"symbol": symbol, "rows": rows}
