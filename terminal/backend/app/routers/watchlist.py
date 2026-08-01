"""Listes de suivi, stockées localement."""

from __future__ import annotations

import json
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..settings import settings

router = APIRouter(prefix="/api/watchlists", tags=["watchlists"])

_lock = Lock()

DEFAULT_WATCHLISTS = {
    "PEA — Cœur": ["MC.PA", "AIR.PA", "SU.PA", "ASML.AS", "SAP.DE", "TTE.PA"],
    "Dividendes": ["TTE.PA", "SAN.PA", "ENGI.PA", "ALV.DE", "ENI.MI", "IBE.MC"],
}


class WatchlistPayload(BaseModel):
    """Contenu d'une liste de suivi."""

    symbols: list[str] = Field(default_factory=list)


def _read() -> dict[str, list[str]]:
    path = settings.watchlist_path
    if not path.exists():
        return dict(DEFAULT_WATCHLISTS)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un fichier corrompu ne doit pas empêcher le terminal de démarrer.
        return dict(DEFAULT_WATCHLISTS)


def _write(data: dict[str, list[str]]) -> None:
    settings.watchlist_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


@router.get("")
async def list_watchlists() -> dict:
    """Toutes les listes de suivi."""
    with _lock:
        return {"watchlists": _read()}


@router.put("/{name}")
async def upsert_watchlist(name: str, payload: WatchlistPayload) -> dict:
    """Crée ou remplace une liste de suivi."""
    symbols = [s.strip().upper() for s in payload.symbols if s.strip()]
    with _lock:
        data = _read()
        data[name] = list(dict.fromkeys(symbols))  # dédoublonne en gardant l'ordre
        _write(data)
        return {"name": name, "symbols": data[name]}


@router.delete("/{name}")
async def delete_watchlist(name: str) -> dict:
    """Supprime une liste de suivi."""
    with _lock:
        data = _read()
        if name not in data:
            raise HTTPException(404, f"Liste inconnue : {name}")
        del data[name]
        _write(data)
        return {"deleted": name}
