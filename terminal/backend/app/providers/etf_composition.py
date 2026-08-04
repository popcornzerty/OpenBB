"""Composition sectorielle des ETF.

Sans elle, une répartition sectorielle serait trompeuse : un portefeuille dont
les trois quarts sont logés dans deux ETF verrait 74 % de son encours classé
« secteur inconnu ». Regarder à travers l'enveloppe est la seule façon de dire
quelque chose de vrai sur l'exposition réelle.

OpenBB expose bien ``etf.sectors``, mais uniquement via des fournisseurs
payants. La bibliothèque yfinance, elle, publie ces pondérations sans clé —
d'où cet accès direct, en marge du reste du terminal qui passe par OpenBB.
"""

from __future__ import annotations

import asyncio

from ..cache import cache

#: Clés yfinance -> libellés de secteur, alignés sur ceux des actions.
#:
#: yfinance nomme les secteurs différemment selon qu'il décrit une action
#: (« Financial Services ») ou un fonds (« financial_services ») ; sans cette
#: table, une même exposition apparaîtrait dans deux lignes distinctes.
SECTOR_LABELS = {
    "realestate": "Real Estate",
    "consumer_cyclical": "Consumer Cyclical",
    "basic_materials": "Basic Materials",
    "consumer_defensive": "Consumer Defensive",
    "technology": "Technology",
    "communication_services": "Communication Services",
    "financial_services": "Financial Services",
    "utilities": "Utilities",
    "industrials": "Industrials",
    "energy": "Energy",
    "healthcare": "Healthcare",
}

#: Zone géographique visée par un fonds, déduite de son mandat.
#:
#: Aucune source gratuite ne publie la répartition par pays d'un ETF —
#: ``top_holdings`` revient vide et il n'existe pas de ventilation
#: géographique. Le mandat du fonds, lui, est explicite dans son nom. Cette
#: table est donc tenue à la main, et l'interface annonce l'approximation.
MANDATE_REGIONS: list[tuple[tuple[str, ...], str]] = [
    (("msci world", "world swap", "monde"), "Monde développé"),
    (("emerging asia", "asie émergente", "asie emergente"), "Asie émergente"),
    (("emerging markets", "marchés émergents", "marches emergents"), "Émergents"),
    (("s&p 500", "sp 500", "usa", "united states", "amérique du nord"), "Amérique du Nord"),
    (("japan", "japon", "topix", "nikkei"), "Japon"),
    (("europe", "stoxx", "euro"), "Europe"),
    (("france", "cac"), "France"),
]

_TTL = 7 * 86_400  # la composition d'un fonds bouge lentement


def region_from_mandate(name: str | None) -> str | None:
    """Zone déduite du nom du fonds, ou ``None`` si aucun mandat reconnu."""
    if not name:
        return None
    lowered = name.casefold()
    for keywords, region in MANDATE_REGIONS:
        if any(keyword in lowered for keyword in keywords):
            return region
    return None


def _read_sector_weightings(symbol: str) -> dict[str, float]:
    """Appel bloquant à yfinance, à exécuter dans un thread."""
    import yfinance as yf  # import local : la bibliothèque est lourde à charger

    ticker = yf.Ticker(symbol)
    raw = getattr(ticker.funds_data, "sector_weightings", None) or {}
    weights: dict[str, float] = {}
    for key, value in raw.items():
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if weight > 0:
            weights[SECTOR_LABELS.get(key, key.replace("_", " ").title())] = weight

    total = sum(weights.values())
    # Les pondérations publiées ne somment pas toujours exactement à 1 ; on
    # renormalise pour qu'une part de portefeuille ne se perde pas en route.
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    return weights


async def sector_weightings(symbol: str) -> dict[str, float]:
    """Pondérations sectorielles d'un fonds, entre 0 et 1.

    Renvoie un dictionnaire vide pour un titre vif ou un fonds sans données —
    l'appelant décide alors quoi faire de cette absence.
    """

    async def produce():
        try:
            return await asyncio.to_thread(_read_sector_weightings, symbol)
        except Exception:  # noqa: BLE001
            return {}

    value, _, _ = await cache.resolve(f"etf:sectors:{symbol}", _TTL, produce)
    return value or {}


def _read_fund_name(symbol: str) -> str | None:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    return info.get("longName") or info.get("shortName")


async def is_fund(symbol: str) -> bool:
    """Le titre est-il un fonds ? Déduit de la présence de pondérations."""
    return bool(await sector_weightings(symbol))
