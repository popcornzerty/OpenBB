"""Cotations, historiques et indices."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query

from ..providers import obb_source

router = APIRouter(prefix="/api/market", tags=["market"])

#: Indices européens suivis par la barre de marché.
EUROPEAN_INDICES = [
    {"symbol": "^FCHI", "name": "CAC 40", "country": "FR"},
    {"symbol": "^GDAXI", "name": "DAX", "country": "DE"},
    {"symbol": "^STOXX50E", "name": "Euro Stoxx 50", "country": "EU"},
    {"symbol": "^AEX", "name": "AEX", "country": "NL"},
    {"symbol": "^IBEX", "name": "IBEX 35", "country": "ES"},
    {"symbol": "^BFX", "name": "BEL 20", "country": "BE"},
    {"symbol": "^N100", "name": "Euronext 100", "country": "EU"},
]


@router.get("/quote/{symbol}")
async def get_quote(symbol: str) -> dict:
    """Dernière cotation connue d'un titre."""
    try:
        return await obb_source.quote(symbol)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Cotation indisponible pour {symbol}: {exc}") from exc


@router.get("/quotes")
async def get_quotes(symbols: str = Query(..., description="Symboles séparés par des virgules")) -> dict:
    """Cotations d'un lot de titres — alimente les watchlists.

    Un symbole en échec n'interrompt pas le lot : il est simplement signalé.
    """
    wanted = [s.strip() for s in symbols.split(",") if s.strip()]
    if not wanted:
        return {"quotes": [], "errors": []}

    results = await asyncio.gather(
        *(obb_source.quote(symbol) for symbol in wanted), return_exceptions=True
    )
    quotes, errors = [], []
    for symbol, result in zip(wanted, results, strict=True):
        if isinstance(result, Exception):
            errors.append({"symbol": symbol, "error": str(result)[:200]})
        else:
            quotes.append(result)
    return {"quotes": quotes, "errors": errors}


@router.get("/historical/{symbol}")
async def get_historical(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = Query("1d", pattern="^(1m|2m|5m|15m|30m|60m|90m|1h|1d|1W|1M)$"),
) -> dict:
    """Série OHLCV d'un titre."""
    try:
        rows = await obb_source.historical(
            symbol, start_date=start_date, end_date=end_date, interval=interval
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Historique indisponible pour {symbol}: {exc}") from exc
    return {"symbol": symbol, "interval": interval, "rows": rows}


@router.get("/indices")
async def get_indices() -> dict:
    """Instantané des grands indices européens (dernier point et variation)."""
    async def snapshot(index: dict) -> dict:
        try:
            rows = await obb_source.index_historical(index["symbol"])
            if len(rows) < 2:
                return {**index, "error": "Historique insuffisant"}
            last, previous = rows[-1], rows[-2]
            close, prev_close = last.get("close"), previous.get("close")
            change = (close / prev_close - 1) if close and prev_close else None
            return {
                **index,
                "date": last.get("date"),
                "close": close,
                "change_percent": round(change * 100, 2) if change is not None else None,
            }
        except Exception as exc:  # noqa: BLE001
            return {**index, "error": str(exc)[:150]}

    return {"indices": await asyncio.gather(*(snapshot(i) for i in EUROPEAN_INDICES))}


@router.get("/index/{symbol}")
async def get_index_history(symbol: str, start_date: str | None = None) -> dict:
    """Série historique d'un indice."""
    try:
        rows = await obb_source.index_historical(symbol, start_date=start_date)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Indice indisponible : {symbol}") from exc
    return {"symbol": symbol, "rows": rows}
