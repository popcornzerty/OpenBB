"""Recherche de titres par nom, ticker ou ISIN."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query

from ..pea import registry
from ..pea.eligibility import Eligibility, assess
from ..providers import obb_source, yahoo_search

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=1, description="Nom, ticker ou ISIN"),
    limit: int = Query(15, ge=1, le=50),
) -> dict:
    """Recherche un titre et joint son statut PEA.

    L'univers local répond instantanément ; au-delà, la recherche Yahoo prend
    le relais, ce qui permet de résoudre un ISIN comme ``FR0000121014``.
    """
    query = q.strip()
    is_isin = yahoo_search.looks_like_isin(query)

    local = []
    if not is_isin:
        needle = query.casefold()
        for entry in registry.entries:
            if needle in entry.symbol.casefold() or needle in entry.name.casefold():
                local.append(
                    {
                        "symbol": entry.symbol,
                        "name": entry.name,
                        "exchange": entry.exchange,
                        "listing_country": entry.country_iso,
                        "quote_type": "EQUITY",
                        "pea_status": entry.pea_status,
                        "source": "univers",
                    }
                )
            if len(local) >= limit:
                break

    remote = await yahoo_search.search(query, limit=limit)
    known = {item["symbol"].upper() for item in local}

    async def with_status(item: dict) -> dict:
        entry = registry.get(item["symbol"])
        if entry is not None:
            item["pea_status"] = entry.pea_status
        elif item.get("quote_type") == "EQUITY":
            # Titre hors univers : on va chercher son pays de siège pour
            # pouvoir trancher, plutôt que d'afficher un statut vide.
            try:
                profile = await obb_source.profile(item["symbol"])
                item["pea_status"] = assess(
                    item["symbol"], profile.get("hq_country")
                ).status.value
            except Exception:  # noqa: BLE001
                item["pea_status"] = Eligibility.UNKNOWN.value
        else:
            item["pea_status"] = Eligibility.UNKNOWN.value
        item["source"] = "recherche"
        return item

    fresh = [item for item in remote if item["symbol"].upper() not in known]
    enriched = await asyncio.gather(*(with_status(item) for item in fresh[:limit]))

    return {"query": query, "is_isin": is_isin, "results": (local + list(enriched))[:limit]}


@router.get("/isin/{isin}")
async def resolve(isin: str) -> dict:
    """Résout un ISIN vers son ticker principal."""
    symbol = await yahoo_search.resolve_isin(isin)
    return {"isin": isin.upper(), "symbol": symbol}
