"""Mouvements déclarés : institutionnels et initiés.

Deux régimes distincts, deux sources, deux niveaux de fiabilité :

- les **franchissements de seuils** (article L. 233-7 du code de commerce)
  viennent d'une API ouverte de l'AMF, stable et sous licence libre ;
- les **déclarations de dirigeants** (article L. 621-18-2) sont moissonnées
  dans la BDIF, dont rien ne garantit la pérennité des points d'entrée.

Les deux ne couvrent que les émetteurs cotés en France. L'écran le dit, car
une absence d'alerte sur Deutsche Telekom ne signifie pas qu'il ne s'y passe
rien : cette valeur n'est simplement pas dans le champ de l'AMF.
"""

from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, HTTPException, Query

from ..pea import registry
from ..portfolio import store
from ..providers import amf_filings, amf_insiders, us_managers

router = APIRouter(prefix="/api/alerts", tags=["alertes"])

#: Places françaises couvertes par l'AMF. Interroger la BDIF pour une valeur
#: allemande ou néerlandaise ne rendrait jamais rien.
FRENCH_SUFFIXES = (".PA", ".NX")

#: Formes juridiques à retirer avant d'interroger l'autocomplétion : l'AMF
#: connaît « VINCI », pas « Vinci SA ».
_FORMES = re.compile(
    r"\s*(,)?\s*(S\.?A\.?S?|S\.?E\.?|SCA|SASU|N\.?V\.?|Soci[ée]t[ée] Europ[ée]enne"
    r"|Group(e)?|Holding)\.?\s*$",
    re.IGNORECASE,
)


def _raison_sociale(name: str) -> str:
    """Ramène un nom de cotation à la raison sociale attendue par l'AMF."""
    nom = name.strip()
    for _ in range(3):  # « Vinci SA, Société Européenne » cumule les suffixes
        reduit = _FORMES.sub("", nom).strip(" ,")
        if reduit == nom:
            break
        nom = reduit
    return nom.upper()


def _french(symbols: list[str]) -> list[str]:
    return [s for s in symbols if s.upper().endswith(FRENCH_SUFFIXES)]


async def _symbols_for(scope: str, name: str) -> list[str]:
    if scope == "portefeuille":
        return [p.symbol for p in store.load().positions]
    if scope == "liste":
        from ..routers.watchlist import _read

        lists = _read()
        if name not in lists:
            raise HTTPException(404, f"Liste inconnue : {name}")
        return list(lists[name])
    raise HTTPException(422, "Portée inconnue : attendu « portefeuille » ou « liste ».")


@router.get("/amf")
async def amf_movements(
    scope: str = Query("portefeuille", description="portefeuille ou liste"),
    name: str = Query("", description="Nom de la liste de suivi"),
    days: int = Query(180, ge=7, le=365),
) -> dict:
    """Franchissements de seuils et déclarations de dirigeants."""
    symbols = await _symbols_for(scope, name)
    francais = _french(symbols)

    # La BDIF s'interroge par raison sociale : on la tire de l'univers, qui
    # porte le nom officiel de chaque valeur.
    couples: list[tuple[str, str]] = []
    for symbol in francais:
        entry = registry.get(symbol)
        if entry and entry.name:
            couples.append((symbol, _raison_sociale(entry.name)))

    crossings, insiders = await asyncio.gather(
        amf_filings.crossings(couples, days=days),
        amf_insiders.insiders(couples, days=days),
        return_exceptions=True,
    )

    vide = {"crossings": [], "covered": [], "scanned": 0, "since": ""}
    crossings = vide if isinstance(crossings, Exception) else crossings
    insiders = (
        {"insiders": [], "covered": [], "since": ""}
        if isinstance(insiders, Exception)
        else insiders
    )

    return {
        "scope": scope,
        "name": name,
        "days": days,
        "symbols": sorted(set(s.upper() for s in symbols)),
        # Ce que la source peut couvrir, indépendamment de ce qu'elle a trouvé.
        "in_scope": sorted(set(s.upper() for s in francais)),
        "out_of_scope": sorted(set(s.upper() for s in symbols) - set(s.upper() for s in francais)),
        "crossings": crossings.get("crossings", []),
        "crossings_scanned": crossings.get("scanned", 0),
        "insiders": insiders.get("insiders", []),
        "since": crossings.get("since") or insiders.get("since"),
    }


@router.get("/managers")
async def american_managers(
    scope: str = Query("portefeuille", description="portefeuille ou liste"),
    name: str = Query("", description="Nom de la liste de suivi"),
    top: int = Query(4, ge=1, le=12),
) -> dict:
    """Gérants américains les plus présents sur ces valeurs européennes.

    Seule vue gratuite sur des mouvements de gérants identifiés : les dépôts
    SEC couvrent aussi leurs positions européennes. L'écran affiche les
    limites — part américaine seulement, retard trimestriel, trackers exclus.
    """
    symbols = await _symbols_for(scope, name)
    result = await us_managers.managers(symbols, top=top)
    return {"scope": scope, "name": name, **result}
