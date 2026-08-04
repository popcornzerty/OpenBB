"""Répartition sectorielle et géographique du portefeuille.

Les fonds sont traités en **transparence** : leur valeur est ventilée selon la
composition sectorielle publiée, et non rangée dans une case « ETF ». Sans
cela, un portefeuille dont les trois quarts sont logés dans deux ETF verrait
74 % de son encours classé « inconnu », ce qui ne renseigne sur rien.

La géographie est plus fragile : aucune source gratuite ne ventile un ETF par
pays. Les titres vifs sont classés par pays du siège, les fonds par mandat —
« Monde développé » pour un MSCI World. L'interface annonce cette différence
de nature.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..providers import etf_composition

#: Exposition dont on ne sait rien.
UNKNOWN = "Non classé"


@dataclass
class Slice:
    """Une part de l'encours attribuée à un secteur ou une zone."""

    label: str
    value: float
    share: float
    #: Symboles contribuant à cette part, du plus au moins important.
    contributors: list[str]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "value": round(self.value, 2),
            "share": round(self.share, 4),
            "contributors": self.contributors,
        }


def _to_slices(buckets: dict[str, float], sources: dict[str, dict[str, float]]) -> list[dict]:
    total = sum(buckets.values())
    slices = []
    for label, value in buckets.items():
        contributors = sorted(
            sources.get(label, {}), key=lambda s: -sources[label][s]
        )
        slices.append(
            Slice(
                label=label,
                value=value,
                share=value / total if total else 0.0,
                contributors=contributors[:6],
            )
        )
    # Le non classé ferme la marche, quelle que soit sa taille : il n'est pas
    # une exposition mais un aveu d'ignorance.
    slices.sort(key=lambda s: (s.label == UNKNOWN, -s.value))
    return [s.as_dict() for s in slices]


async def compute(rows: list[dict]) -> dict:
    """Répartitions sectorielle et géographique, fonds inclus en transparence.

    ``rows`` porte au minimum ``symbol``, ``market_value``, et éventuellement
    ``sector``, ``country_label`` et ``name``.
    """
    priced = [r for r in rows if (r.get("market_value") or 0) > 0]
    total = sum(r["market_value"] for r in priced)

    # Une seule interrogation par symbole, menée en parallèle.
    weightings = dict(
        zip(
            [r["symbol"] for r in priced],
            await asyncio.gather(
                *(etf_composition.sector_weightings(r["symbol"]) for r in priced)
            ),
            strict=True,
        )
    )

    sectors: dict[str, float] = {}
    sector_sources: dict[str, dict[str, float]] = {}
    regions: dict[str, float] = {}
    region_sources: dict[str, dict[str, float]] = {}
    fund_value = 0.0

    def add(bucket, sources, label, symbol, value):
        bucket[label] = bucket.get(label, 0.0) + value
        sources.setdefault(label, {})
        sources[label][symbol] = sources[label].get(symbol, 0.0) + value

    for row in priced:
        symbol = row["symbol"]
        value = row["market_value"]
        composition = weightings.get(symbol) or {}

        if composition:
            fund_value += value
            for sector, weight in composition.items():
                add(sectors, sector_sources, sector, symbol, value * weight)
            region = etf_composition.region_from_mandate(row.get("name")) or UNKNOWN
            add(regions, region_sources, region, symbol, value)
        else:
            add(sectors, sector_sources, row.get("sector") or UNKNOWN, symbol, value)
            add(regions, region_sources, row.get("country_label") or UNKNOWN, symbol, value)

    classified = total - sectors.get(UNKNOWN, 0.0)
    return {
        "total": round(total, 2),
        "sectors": _to_slices(sectors, sector_sources),
        "regions": _to_slices(regions, region_sources),
        "look_through_value": round(fund_value, 2),
        "look_through_share": round(fund_value / total, 4) if total else 0.0,
        "classified_share": round(classified / total, 4) if total else 0.0,
        "note": (
            "Les fonds sont ventilés selon leur composition sectorielle publiée. "
            "Faute de ventilation géographique disponible, ils sont classés par "
            "mandat — « Monde développé » pour un MSCI World — là où les titres "
            "vifs le sont par pays du siège."
        ),
    }
