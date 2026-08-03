"""Screener sur l'univers européen."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..pea import registry
from ..pea.eligibility import Eligibility
from ..valuation import ranking

router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.post("/ranking/start")
async def start_ranking(pea_only: bool = True) -> dict:
    """Lance le classement des sociétés de la plus à la moins sous-cotée.

    Le calcul tourne en tâche de fond : compter un quart d'heure pour l'univers
    complet à froid — c'est la source de données qui fixe le rythme, pas le
    calcul — puis quasi instantané pendant 24 h grâce au cache.
    """
    if registry.is_empty:
        raise HTTPException(
            503, "Univers vide : lancez d'abord scripts/build_universe.py."
        )
    return ranking.start(pea_only=pea_only)


@router.get("/ranking")
async def get_ranking() -> dict:
    """Avancement et résultat du classement."""
    return ranking.job.result()

#: ``market_cap`` est délibérément absent : trier sur une capitalisation en
#: devise locale mettrait les valeurs danoises et suédoises en tête pour de
#: simples raisons de change. Seule la version en euros est comparable.
SORT_KEYS = {"symbol", "name", "market_cap_eur", "country_iso", "sector", "index"}


@router.get("/filters")
async def get_filters() -> dict:
    """Valeurs disponibles pour alimenter les listes déroulantes du screener."""
    return {
        "indices": registry.indices(),
        "countries": registry.countries(),
        "sectors": registry.sectors(),
        "total": len(registry.entries),
    }


@router.get("")
async def screen(
    pea_only: bool = Query(True, description="Ne garder que les titres éligibles PEA"),
    index: str | None = None,
    country: str | None = Query(None, description="Code ISO-3166 alpha-2"),
    sector: str | None = None,
    min_market_cap: float | None = Query(None, ge=0, description="En euros"),
    max_market_cap: float | None = Query(None, ge=0, description="En euros"),
    q: str | None = Query(None, description="Filtre texte sur le nom ou le ticker"),
    sort: str = Query("market_cap_eur"),
    descending: bool = True,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Filtre l'univers européen.

    ``pea_only`` est actif par défaut : le terminal est d'abord un outil PEA.
    Les titres au statut indéterminé sont exclus de ce filtre — on ne présume
    jamais l'éligibilité.
    """
    rows = registry.entries

    if pea_only:
        rows = [e for e in rows if e.pea_status == Eligibility.ELIGIBLE.value]
    if index:
        rows = [e for e in rows if e.index == index]
    if country:
        rows = [e for e in rows if e.country_iso == country.upper()]
    if sector:
        rows = [e for e in rows if e.sector == sector]
    if min_market_cap is not None:
        rows = [
            e for e in rows
            if e.market_cap_eur is not None and e.market_cap_eur >= min_market_cap
        ]
    if max_market_cap is not None:
        rows = [
            e for e in rows
            if e.market_cap_eur is not None and e.market_cap_eur <= max_market_cap
        ]
    if q:
        needle = q.casefold()
        rows = [
            e for e in rows
            if needle in e.symbol.casefold() or needle in e.name.casefold()
        ]

    sort_key = sort if sort in SORT_KEYS else "market_cap"

    def missing(entry) -> bool:
        value = getattr(entry, sort_key)
        return value is None or value == ""

    # Les lignes sans valeur sur le critère de tri sont mises de côté puis
    # renvoyées en fin de liste. Les inclure dans le tri les ferait remonter en
    # tête dès que l'ordre est décroissant, ce qui met les fiches les moins
    # renseignées en avant — exactement l'inverse de l'intention.
    present = [e for e in rows if not missing(e)]
    absent = [e for e in rows if missing(e)]
    present.sort(key=lambda e: getattr(e, sort_key), reverse=descending)
    absent.sort(key=lambda e: e.symbol)
    rows = present + absent

    total = len(rows)
    page = rows[offset : offset + limit]

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": [entry.as_dict() for entry in page],
    }
