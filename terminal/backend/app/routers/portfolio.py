"""Portefeuille lu depuis Wealthfolio.

Le terminal ne tient pas de portefeuille : c'est le rôle de Wealthfolio. Il se
contente de lire ses positions pour leur appliquer ce qu'il sait faire —
cotations, éligibilité PEA et juste valeur.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..pea import registry
from ..pea.eligibility import Eligibility, assess
from ..providers import obb_source, wealthfolio_db
from ..providers.wealthfolio_db import PortfolioUnavailable

router = APIRouter(prefix="/api/portfolio", tags=["portefeuille"])


@router.get("/status")
async def status() -> dict:
    """Wealthfolio est-il joignable, et où ?"""
    path = wealthfolio_db.database_path()
    available = path.exists()
    accounts: list[dict] = []
    if available:
        try:
            accounts = await asyncio.to_thread(wealthfolio_db.read_accounts)
        except PortfolioUnavailable:
            available = False
    return {
        "available": available,
        "database": str(path),
        "accounts": accounts,
        "hint": (
            None
            if available
            else "Installez Wealthfolio, ou pointez PEATERM_WEALTHFOLIO_DB vers sa base."
        ),
    }


async def _enrich(position) -> dict:
    """Ajoute cotation et verdict PEA à une position."""
    row = position.as_dict()

    try:
        quote = await obb_source.quote(position.symbol)
        # Les ETF remontent souvent sans dernier cours ; la clôture précédente
        # vaut mieux qu'une ligne sans valorisation, à condition de le dire.
        price = quote.get("last_price")
        row["price_source"] = "last"
        if price is None:
            price = quote.get("prev_close")
            row["price_source"] = "prev_close" if price is not None else "none"
        row["price"] = price
        row["market_value"] = (
            price * position.quantity if price is not None else None
        )
        row["as_of"] = quote.get("as_of")
    except Exception:  # noqa: BLE001
        # Une cotation manquante ne doit pas faire disparaître la ligne du
        # portefeuille : la quantité et le prix de revient restent utiles.
        row["price"] = None
        row["market_value"] = None
        row["as_of"] = None

    if row["market_value"] is not None and position.cost_basis:
        row["gain"] = row["market_value"] - position.cost_basis
        row["gain_percent"] = row["gain"] / position.cost_basis
    else:
        row["gain"] = None
        row["gain_percent"] = None

    entry = registry.get(position.symbol)
    if entry is not None:
        row["pea_status"] = entry.pea_status
        row["pea_reason"] = entry.pea_reason
        row["country_label"] = entry.country_label or None
    else:
        try:
            profile = await obb_source.profile(position.symbol)
            verdict = assess(position.symbol, profile.get("hq_country"))
            row["pea_status"] = verdict.status.value
            row["pea_reason"] = verdict.reason
            row["country_label"] = verdict.country_label
        except Exception:  # noqa: BLE001
            row["pea_status"] = Eligibility.UNKNOWN.value
            row["pea_reason"] = "Profil indisponible : éligibilité non établie."
            row["country_label"] = None

    return row


@router.get("/holdings")
async def holdings(
    quotes: bool = Query(True, description="Joindre les cotations et le statut PEA"),
) -> dict:
    """Positions courantes du portefeuille Wealthfolio."""
    try:
        positions = await asyncio.to_thread(wealthfolio_db.read_positions)
    except PortfolioUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    if not quotes:
        rows = [p.as_dict() for p in positions]
    else:
        rows = list(await asyncio.gather(*(_enrich(p) for p in positions)))

    total_value = sum(r.get("market_value") or 0 for r in rows)
    total_cost = sum(r.get("cost_basis") or 0 for r in rows)
    eligible_value = sum(
        r.get("market_value") or 0 for r in rows if r.get("pea_status") == "eligible"
    )

    return {
        "rows": rows,
        "summary": {
            "positions": len(rows),
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain": round(total_value - total_cost, 2) if total_value else None,
            "total_gain_percent": (
                round((total_value - total_cost) / total_cost, 4) if total_cost else None
            ),
            # Part de l'encours dont l'éligibilité est confirmée. Les lignes au
            # statut indéterminé — les ETF notamment — en sont exclues : mieux
            # vaut un pourcentage prudent qu'un pourcentage flatteur.
            "confirmed_pea_value": round(eligible_value, 2),
            "confirmed_pea_share": (
                round(eligible_value / total_value, 4) if total_value else None
            ),
            "snapshot_date": rows[0]["snapshot_date"] if rows else None,
        },
        "source": "Wealthfolio (lecture seule)",
    }
