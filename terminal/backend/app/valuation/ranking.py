"""Classement des sociétés de la plus à la moins sous-cotée.

Classer au seul écart cours/juste valeur ferait remonter en tête les
estimations les moins solides : une décote de 40 % traduit plus souvent un
multiple déformé par un exercice atypique qu'une bonne affaire. Chaque écart
est donc pondéré par un **facteur de fiabilité**, et le classement porte sur
cette décote ajustée.

L'écart brut reste affiché à côté : le score sert à ordonner, pas à cacher.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from ..pea import registry
from ..pea.eligibility import Eligibility
from .fairvalue import ValuationError
from .service import valuation_for

#: Nombre de calculs menés de front.
#:
#: Chaque valorisation déclenche quatre appels à la source de données ; monter
#: plus haut la fait limiter, et le gain de temps se paie en échecs.
CONCURRENCY = 6


def period_factor(periods: int) -> float:
    """Fiabilité tirée du nombre d'exercices publiés.

    Avec quatre exercices, un seul millésime atypique pèse un quart de
    l'échantillon et déplace la médiane. Les sources gratuites plafonnant à
    cinq, ce facteur reste le principal frein — et c'est voulu : il rappelle
    que la profondeur de données est la vraie limite.
    """
    if periods <= 3:
        return 0.3
    if periods == 4:
        return 0.5
    if periods == 5:
        return 0.8
    return 1.0


def breadth_factor(components: int) -> float:
    """Fiabilité tirée du nombre de multiples retenus.

    Une juste valeur assise sur un seul multiple dépend entièrement de lui ;
    quatre multiples concordants se corrigent mutuellement.
    """
    return {0: 0.0, 1: 0.4, 2: 0.7, 3: 0.9}.get(components, 1.0)


def stability_factor(dispersion: float | None) -> float:
    """Fiabilité tirée de la dispersion des multiples.

    Un multiple qui a beaucoup varié dans le passé ne dit pas grand-chose de
    la valeur « normale » du titre.
    """
    if dispersion is None:
        return 0.5
    if dispersion <= 0.20:
        return 1.0
    if dispersion >= 0.60:
        return 0.3
    # Décroissance linéaire entre les deux bornes.
    return 1.0 - (dispersion - 0.20) / 0.40 * 0.7


def reliability(valuation: dict) -> tuple[float, dict]:
    """Facteur de fiabilité dans [0, 1], avec le détail de ses composantes."""
    components = valuation.get("components") or []
    periods = (valuation.get("confidence") or {}).get("periods_used", 0)

    # Dispersion moyenne, pondérée par le poids de chaque multiple : un
    # multiple très dispersé mais faiblement pondéré ne doit pas dominer.
    total_weight = sum(c.get("weight", 0) for c in components)
    if total_weight > 0:
        weighted_dispersion = (
            sum(c.get("dispersion", 0) * c.get("weight", 0) for c in components)
            / total_weight
        )
    else:
        weighted_dispersion = None

    parts = {
        "periods": round(period_factor(periods), 3),
        "breadth": round(breadth_factor(len(components)), 3),
        "stability": round(stability_factor(weighted_dispersion), 3),
    }
    # Produit et non moyenne : une faiblesse sur un axe ne doit pas être
    # compensée par de la force ailleurs.
    score = parts["periods"] * parts["breadth"] * parts["stability"]
    parts["weighted_dispersion"] = (
        round(weighted_dispersion, 3) if weighted_dispersion is not None else None
    )
    return score, parts


def adjusted_discount(gap: float | None, reliability_factor: float) -> float | None:
    """Décote ajustée : l'écart, ramené à ce que la fiabilité permet d'affirmer.

    Positive pour un titre sous-coté. Une décote de 40 % à demi fiable vaut
    une décote de 20 % pleinement fiable — c'est tout l'objet du classement.
    """
    if gap is None:
        return None
    return (-gap) * reliability_factor


@dataclass
class RankingRow:
    """Une ligne du classement."""

    symbol: str
    name: str
    sector: str
    country: str
    index: str
    #: Capitalisation en euros, reprise de l'univers. Seule grandeur
    #: comparable d'une place à l'autre.
    market_cap_eur: float | None
    last_price: float
    fair_value: float | None
    gap: float | None
    reliability: float
    reliability_parts: dict
    adjusted_discount: float | None
    verdict: str
    confidence: str
    periods_used: int
    components: int
    currency: str | None

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sector": self.sector,
            "country": self.country,
            "index": self.index,
            "market_cap_eur": self.market_cap_eur,
            "last_price": self.last_price,
            "fair_value": self.fair_value,
            "gap": self.gap,
            "reliability": round(self.reliability, 3),
            "reliability_parts": self.reliability_parts,
            "adjusted_discount": (
                round(self.adjusted_discount, 4)
                if self.adjusted_discount is not None
                else None
            ),
            "verdict": self.verdict,
            "confidence": self.confidence,
            "periods_used": self.periods_used,
            "components": self.components,
            "currency": self.currency,
        }


JobState = Literal["idle", "running", "done", "error"]


@dataclass
class RankingJob:
    """Calcul du classement, mené en tâche de fond.

    Un seul calcul à la fois : le lancer deux fois en parallèle doublerait la
    charge sur la source de données sans rien apporter.
    """

    state: JobState = "idle"
    total: int = 0
    done: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    rows: list[RankingRow] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    error: str | None = None
    _task: asyncio.Task | None = None

    @property
    def elapsed(self) -> float | None:
        if self.started_at is None:
            return None
        end = self.finished_at or time.time()
        return round(end - self.started_at, 1)

    def status(self) -> dict:
        return {
            "state": self.state,
            "total": self.total,
            "done": self.done,
            "progress": round(self.done / self.total, 3) if self.total else 0.0,
            "elapsed_seconds": self.elapsed,
            "computed": len(self.rows),
            "skipped": len(self.failures),
            "error": self.error,
            "as_of": self.finished_at,
        }

    def result(self) -> dict:
        # Du plus sous-coté au moins : décote ajustée décroissante. Les titres
        # sans estimation exploitable ferment la marche plutôt que d'être
        # écartés silencieusement.
        ranked = sorted(
            self.rows,
            key=lambda r: (
                r.adjusted_discount is None,
                -(r.adjusted_discount or 0),
            ),
        )
        return {
            **self.status(),
            "rows": [row.as_dict() for row in ranked],
            "failures": self.failures[:50],
            "method": (
                "Décote ajustée = écart cours/juste valeur × fiabilité. "
                "La fiabilité combine le nombre d'exercices publiés, le nombre de "
                "multiples retenus et leur dispersion. Une décote de 40 % à demi "
                "fiable vaut une décote de 20 % pleinement fiable."
            ),
        }


#: Instance unique, partagée par les requêtes.
job = RankingJob()


async def _compute_one(symbol: str, entry, semaphore: asyncio.Semaphore) -> None:
    async with semaphore:
        try:
            valuation = await valuation_for(symbol)
        except ValuationError as exc:
            job.failures.append({"symbol": symbol, "reason": str(exc)[:160]})
            return
        except Exception as exc:  # noqa: BLE001
            job.failures.append(
                {"symbol": symbol, "reason": f"{type(exc).__name__}: {str(exc)[:120]}"}
            )
            return
        finally:
            job.done += 1

        factor, parts = reliability(valuation)
        gap = valuation.get("gap")
        job.rows.append(
            RankingRow(
                symbol=symbol,
                name=valuation.get("name") or entry.name,
                sector=entry.sector,
                country=entry.country_label or "",
                index=entry.index,
                market_cap_eur=entry.market_cap_eur,
                last_price=valuation.get("last_price"),
                fair_value=valuation.get("fair_value"),
                gap=gap,
                reliability=factor,
                reliability_parts=parts,
                adjusted_discount=adjusted_discount(gap, factor),
                verdict=valuation.get("verdict", ""),
                confidence=(valuation.get("confidence") or {}).get("level", ""),
                periods_used=(valuation.get("confidence") or {}).get("periods_used", 0),
                components=len(valuation.get("components") or []),
                currency=valuation.get("currency"),
            )
        )


async def _run(symbols: list[tuple[str, object]]) -> None:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    try:
        await asyncio.gather(
            *(_compute_one(symbol, entry, semaphore) for symbol, entry in symbols)
        )
        job.state = "done"
    except Exception as exc:  # noqa: BLE001
        job.state = "error"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished_at = time.time()


def start(pea_only: bool = True) -> dict:
    """Lance le calcul du classement sur l'univers.

    Relancer pendant un calcul en cours ne fait rien : l'état courant est
    renvoyé tel quel.
    """
    if job.state == "running":
        return job.status()

    entries = [
        entry
        for entry in registry.entries
        if not pea_only or entry.pea_status == Eligibility.ELIGIBLE.value
    ]

    job.state = "running"
    job.total = len(entries)
    job.done = 0
    job.rows = []
    job.failures = []
    job.error = None
    job.started_at = time.time()
    job.finished_at = None

    job._task = asyncio.create_task(_run([(e.symbol, e) for e in entries]))
    return job.status()
