"""Juste valeur et score de qualité."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..valuation import ValuationError
from ..valuation.service import valuation_for

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


@router.get("/{symbol}")
async def get_valuation(symbol: str) -> dict:
    """Courbe de juste valeur d'un titre, avec le détail de ses composantes."""
    try:
        return await valuation_for(symbol)
    except ValuationError as exc:
        # 422 et non 404 : le titre existe, c'est le calcul qui n'est pas
        # possible avec les données publiées.
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"Calcul impossible pour {symbol}: {exc}") from exc
