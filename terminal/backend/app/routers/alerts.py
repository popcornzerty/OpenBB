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
from ..providers import amf_filings, amf_insiders, obb_source, us_managers

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



async def _closes(symbols: set[str], since: str) -> dict[str, dict[str, float]]:
    """Cours de clôture par valeur et par jour, depuis ``since``.

    Un avis de franchissement ne porte aucun prix : il indique une assiette
    atteinte, pas une transaction. Le cours du jour de franchissement est donc
    la seule référence de marché rattachable — calculée, jamais présentée
    comme un prix payé.
    """
    if not symbols or not since:
        return {}

    async def one(symbol: str) -> tuple[str, dict[str, float]]:
        try:
            rows = await obb_source.historical(symbol, start_date=since)
        except Exception:  # noqa: BLE001
            return symbol, {}
        serie = {}
        for row in rows:
            jour = str(row.get("date"))[:10]
            close = row.get("close")
            if jour and close is not None:
                serie[jour] = float(close)
        return symbol, serie

    pairs = await asyncio.gather(*(one(s) for s in symbols), return_exceptions=True)
    return {s: v for pair in pairs if isinstance(pair, tuple) for s, v in [pair]}


def _cours_du_jour(serie: dict[str, float], jour: str | None) -> float | None:
    """Clôture de ce jour, ou du dernier jour coté qui le précède."""
    if not serie or not jour:
        return None
    if jour in serie:
        return serie[jour]
    anterieurs = [d for d in serie if d <= jour]
    return serie[max(anterieurs)] if anterieurs else None


def _nom_complet(symbol: str) -> str | None:
    """Dénomination de l'univers, seule source dont le nom soit vérifié.

    Hors univers — un ETF, une valeur ajoutée à la main — on préfère ne rien
    afficher qu'un nom deviné à partir de la raison sociale de l'avis.
    """
    entry = registry.get(symbol)
    return entry.name if entry and entry.name else None


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

    lignes_c = crossings.get("crossings", [])
    lignes_i = insiders.get("insiders", [])
    depuis = crossings.get("since") or insiders.get("since")

    # Le cours du jour n'a d'intérêt que pour les franchissements : les
    # déclarations de dirigeants portent déjà le prix réellement pratiqué.
    series = await _closes({r["symbol"] for r in lignes_c if r.get("franchi_le")}, depuis)
    for row in lignes_c:
        cours = _cours_du_jour(series.get(row["symbol"], {}), row.get("franchi_le"))
        row["cours"] = round(cours, 4) if cours is not None else None
        actions = row.get("actions")
        # Valeur de la participation atteinte, pas montant d'un achat.
        row["valeur_participation"] = (
            round(actions * cours, 2) if actions and cours is not None else None
        )
        row["name"] = _nom_complet(row["symbol"])

    for row in lignes_i:
        row["name"] = _nom_complet(row["symbol"])

    return {
        "scope": scope,
        "name": name,
        "days": days,
        "symbols": sorted(set(s.upper() for s in symbols)),
        # Ce que la source peut couvrir, indépendamment de ce qu'elle a trouvé.
        "in_scope": sorted(set(s.upper() for s in francais)),
        "out_of_scope": sorted(set(s.upper() for s in symbols) - set(s.upper() for s in francais)),
        "crossings": lignes_c,
        "crossings_scanned": crossings.get("scanned", 0),
        "insiders": lignes_i,
        "since": depuis,
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


@router.get("/insiders/{symbol}")
async def insiders_for(
    symbol: str,
    days: int = Query(365, ge=30, le=1095),
) -> dict:
    """Déclarations de dirigeants pour une seule valeur.

    Sur une fiche société, la fenêtre est plus large que dans l'écran de
    veille : on ne cherche pas ce qui vient de bouger, mais ce que les
    dirigeants ont fait ces derniers mois.
    """
    cible = symbol.upper()
    if not cible.endswith(FRENCH_SUFFIXES):
        # Hors champ de l'AMF : le dire, plutôt que rendre une liste vide qui
        # se lirait comme une absence de mouvement.
        return {
            "symbol": cible,
            "name": _nom_complet(cible),
            "in_scope": False,
            "insiders": [],
            "since": "",
        }

    entry = registry.get(cible)
    nom = _raison_sociale(entry.name) if entry and entry.name else cible.split(".")[0]
    result = await amf_insiders.insiders([(cible, nom)], days=days)
    lignes = result.get("insiders", [])
    for row in lignes:
        row["name"] = _nom_complet(cible)
    return {
        "symbol": cible,
        "name": _nom_complet(cible),
        "in_scope": True,
        "insiders": lignes,
        "since": result.get("since", ""),
    }
