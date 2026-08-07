"""Détenteurs institutionnels américains de valeurs européennes.

Les gérants américains déclarent leurs positions à la SEC — formulaire 13F
pour les mandats, N-PORT pour les fonds — y compris lorsqu'elles portent sur
des titres cotés en Europe. Yahoo relaie ces dépôts, ce qui donne la seule
vue gratuite sur des mouvements de gérants identifiés.

Trois limites structurent la lecture, et l'écran les affiche :

- **c'est la part américaine seulement.** Les gérants européens ne déclarent
  rien de comparable : l'AIFMD ne publie pas, et il n'existe pas de 13F
  européen. Les pourcentages détenus sont donc minuscules — quelques dixièmes
  de pour cent — car ils ne représentent pas le capital réel du titre ;
- **45 à 60 jours de retard.** Un dépôt trimestriel arrive après la clôture
  du trimestre. Ce qui est affiché a déjà été fait ;
- **les fonds indiciels dominent.** Vanguard et iShares détiennent tout, et
  leurs variations traduisent une collecte, pas une décision. Ils sont donc
  écartés, faute de quoi ils occuperaient tout le classement.
"""

from __future__ import annotations

import asyncio
import math
import re
from typing import Any

from ..cache import cache

#: Les dépôts sont trimestriels : les relire chaque jour n'apporte rien.
TTL_SECONDS = 24 * 3600

#: Gestion indicielle et supports de réplication. Leur présence est mécanique
#: — ils répliquent un indice — et leurs variations suivent la collecte, pas
#: une conviction. Les garder reviendrait à classer Vanguard premier partout.
_INDICIELS = re.compile(
    r"\b(index|indice|ishares|vanguard|spdr|etf|tracker|msci|s&p|russell|ftse"
    r"|stoxx|nasdaq[- ]100|dow jones|total (international|market)|developed markets"
    r"|eafe|all[- ]world|equity market)\b",
    re.IGNORECASE,
)

#: En deçà, un gérant n'est présent que sur une valeur : ce n'est pas une
#: politique d'investissement lisible, c'est une ligne isolée.
MIN_POSITIONS = 2


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def est_indiciel(nom: str) -> bool:
    """Vrai si le détenteur est un support de réplication."""
    return bool(_INDICIELS.search(nom or ""))


def _fetch(symbol: str) -> list[dict]:
    """Détenteurs déclarés pour un titre. Synchrone : appelé dans un thread."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    lignes: list[dict] = []
    for source, categorie in (
        ("institutional_holders", "mandat"),
        ("mutualfund_holders", "fonds"),
    ):
        try:
            frame = getattr(ticker, source)
        except Exception:  # noqa: BLE001
            continue
        if frame is None or getattr(frame, "empty", True):
            continue
        for _, row in frame.iterrows():
            nom = str(row.get("Holder") or "").strip()
            if not nom:
                continue
            lignes.append(
                {
                    "holder": nom,
                    "categorie": categorie,
                    "symbol": symbol.upper(),
                    "date": str(row.get("Date Reported") or "")[:10],
                    "shares": _number(row.get("Shares")),
                    "value": _number(row.get("Value")),
                    "pct_held": _number(row.get("pctHeld")),
                    "pct_change": _number(row.get("pctChange")),
                }
            )
    return lignes


async def _holders(symbol: str) -> list[dict]:
    async def produce():
        try:
            return await asyncio.to_thread(_fetch, symbol)
        except Exception:  # noqa: BLE001
            return []

    value, _, _ = await cache.resolve(f"holders:v1:{symbol.upper()}", TTL_SECONDS, produce)
    return value


async def managers(symbols: list[str], top: int = 4) -> dict:
    """Gérants actifs les plus présents sur ces valeurs, et leurs mouvements.

    Le classement retient la présence — le nombre de lignes détenues — plutôt
    que l'encours : un gérant qui détient huit des valeurs suivies exprime une
    vue sur le marché, là où un encours élevé sur une seule ligne peut n'être
    qu'un pari isolé.
    """
    semaphore = asyncio.Semaphore(6)

    async def one(symbol: str) -> list[dict]:
        async with semaphore:
            return await _holders(symbol)

    groupes = await asyncio.gather(
        *(one(s) for s in symbols), return_exceptions=True
    )

    par_gerant: dict[str, list[dict]] = {}
    ecartes = 0
    dates: set[str] = set()
    for groupe in groupes:
        if not isinstance(groupe, list):
            continue
        for ligne in groupe:
            if est_indiciel(ligne["holder"]):
                ecartes += 1
                continue
            par_gerant.setdefault(ligne["holder"], []).append(ligne)
            if ligne["date"]:
                dates.add(ligne["date"])

    retenus = []
    for nom, lignes in par_gerant.items():
        if len(lignes) < MIN_POSITIONS:
            continue
        encours = sum(l["value"] or 0 for l in lignes)
        mouvements = [l for l in lignes if l["pct_change"]]
        retenus.append(
            {
                "holder": nom,
                "categorie": lignes[0]["categorie"],
                "positions": len(lignes),
                "value": round(encours, 2),
                "last_reported": max((l["date"] for l in lignes if l["date"]), default=""),
                "achats": sum(1 for l in mouvements if (l["pct_change"] or 0) > 0),
                "ventes": sum(1 for l in mouvements if (l["pct_change"] or 0) < 0),
                "holdings": sorted(
                    lignes, key=lambda l: -(l["value"] or 0)
                ),
            }
        )

    retenus.sort(key=lambda m: (-m["positions"], -m["value"]))
    return {
        "managers": retenus[:top],
        "candidates": len(par_gerant),
        "index_lines_excluded": ecartes,
        "as_of": max(dates) if dates else "",
        "symbols": sorted({s.upper() for s in symbols}),
    }


__all__ = ["managers", "est_indiciel", "MIN_POSITIONS"]
