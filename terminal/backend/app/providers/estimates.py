"""Consensus des analystes, via yfinance.

Aucun fournisseur OpenBB ne publie d'estimations européennes sans clé
payante. yfinance expose en revanche le consensus Refinitiv relayé par Yahoo,
vérifié disponible sur l'ensemble de l'univers visé — grandes valeurs comme
petites capitalisations.

**Deux exercices seulement.** Yahoo publie l'exercice en cours et le suivant,
là où un Zonebourse en affiche trois ou quatre. C'est la limite de la source
gratuite, pas un choix : les colonnes au-delà resteraient vides.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
from typing import Any

from ..cache import cache
from ..settings import settings

#: Les estimations bougent lentement — une révision de consensus se compte en
#: jours. Un TTL long évite de marteler Yahoo sans rien perdre d'utile.
TTL_SECONDS = 6 * 3600

#: Nombre minimal d'analystes pour qu'une estimation soit publiée telle
#: quelle. En dessous, la moyenne est celle d'une poignée de bureaux et le
#: consensus n'en est pas un : l'information reste affichée, mais signalée.
THIN_COVERAGE = 3


def _number(value: Any) -> float | None:
    """Convertit en flottant fini, sinon ``None``."""
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _row(frame, period: str, column: str) -> float | None:
    """Lit une cellule du tableau d'estimations, absente ou vide comprise."""
    try:
        if frame is None or period not in frame.index or column not in frame.columns:
            return None
        return _number(frame.loc[period, column])
    except Exception:  # noqa: BLE001
        return None


def _fetch(symbol: str) -> dict:
    """Interroge yfinance. Synchrone : appelé dans un thread."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    eps = ticker.earnings_estimate
    revenue = ticker.revenue_estimate

    # L'exercice de référence de Yahoo est l'exercice fiscal en cours. Sans
    # sa date de clôture on ne saurait pas à quelle année rattacher « 0y ».
    fiscal_year_end = None
    try:
        info = ticker.info or {}
        raw = info.get("lastFiscalYearEnd")
        if raw:
            fiscal_year_end = dt.date.fromtimestamp(int(raw))
    except Exception:  # noqa: BLE001
        info = {}

    targets = {}
    try:
        targets = ticker.analyst_price_targets or {}
    except Exception:  # noqa: BLE001
        targets = {}

    periods = []
    for offset, key in ((0, "0y"), (1, "+1y")):
        eps_avg = _row(eps, key, "avg")
        revenue_avg = _row(revenue, key, "avg")
        if eps_avg is None and revenue_avg is None:
            continue
        analysts = _row(eps, key, "numberOfAnalysts") or _row(
            revenue, key, "numberOfAnalysts"
        )
        periods.append(
            {
                "offset": offset,
                "eps": eps_avg,
                "eps_low": _row(eps, key, "low"),
                "eps_high": _row(eps, key, "high"),
                "eps_growth": _row(eps, key, "growth"),
                # Le bénéfice de l'exercice précédent sert d'ancrage : il doit
                # coïncider avec le dernier exercice publié, faute de quoi les
                # colonnes estimées seraient décalées d'un an.
                "year_ago_eps": _row(eps, key, "yearAgoEps"),
                "revenue": revenue_avg,
                "revenue_growth": _row(revenue, key, "growth"),
                "analysts": int(analysts) if analysts else None,
                "thin": bool(analysts and analysts < THIN_COVERAGE),
            }
        )

    return {
        "periods": periods,
        "fiscal_year_end": fiscal_year_end.isoformat() if fiscal_year_end else None,
        # Bénéfice par action des douze derniers mois, exprimé dans la devise
        # de **cotation** — donc directement comparable aux dividendes
        # détachés. Les états financiers, eux, sont libellés dans la devise de
        # publication : Aker BP verse en couronnes et publie en dollars, et
        # rapporter l'un à l'autre donnait un taux de distribution de 12 000 %.
        "trailing_eps": _number(info.get("trailingEps")),
        "listing_currency": info.get("currency"),
        # Dividende annuel indicatif à douze mois, en devise de cotation. Ce
        # n'est pas un consensus par exercice — la source n'en publie pas —
        # mais le montant que la société a annoncé ou vient de détacher. Il ne
        # vaut donc que pour le premier exercice estimé.
        "dividend_rate": _number(info.get("dividendRate")),
        "price_target": {
            "mean": _number(targets.get("mean")),
            "median": _number(targets.get("median")),
            "low": _number(targets.get("low")),
            "high": _number(targets.get("high")),
            "current": _number(targets.get("current")),
        },
        "currency": (info.get("financialCurrency") or info.get("currency") or None),
    }


def _premium_periods(symbol: str, provider: str) -> list[dict]:
    """Consensus élargi, quand une clé payante est configurée.

    FMP et Intrinio publient les estimations de bénéfice et d'EBITDA sur
    plusieurs exercices ; Intrinio y ajoute le chiffre d'affaires. Les clés
    ``eps``, ``revenue`` et ``ebitda`` alimentent les mêmes colonnes que le
    consensus gratuit — le tableau ne fait aucune différence entre les deux.

    Toute défaillance renvoie une liste vide : l'appelant retombe alors sur la
    source gratuite plutôt que de perdre ses colonnes estimées.
    """
    from openbb import obb

    by_year: dict[int, dict] = {}

    def absorb(route, field: str) -> None:
        try:
            rows = route(symbol, provider=provider).results
        except Exception:  # noqa: BLE001
            return
        for row in rows:
            data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
            stamp = data.get("date") or data.get("fiscal_year") or data.get("period_ending")
            year = None
            if isinstance(stamp, int):
                year = stamp
            elif stamp is not None:
                try:
                    year = dt.date.fromisoformat(str(stamp)[:10]).year
                except ValueError:
                    year = None
            if year is None:
                continue
            value = _number(
                data.get("mean")
                or data.get("estimated_eps_avg")
                or data.get("estimated_ebitda_avg")
                or data.get("estimated_revenue_avg")
                or data.get("value")
            )
            if value is None:
                continue
            bucket = by_year.setdefault(year, {"year": year})
            bucket[field] = value
            count = _number(
                data.get("number_of_analysts") or data.get("analyst_count")
            )
            if count:
                bucket["analysts"] = int(count)

    estimates_router = obb.equity.estimates
    absorb(estimates_router.forward_eps, "eps")
    absorb(estimates_router.forward_ebitda, "ebitda")
    if hasattr(estimates_router, "forward_sales"):
        absorb(estimates_router.forward_sales, "revenue")

    ordered = sorted(by_year.values(), key=lambda b: b["year"])
    return [b for b in ordered if b.get("eps") is not None or b.get("revenue") is not None]


def _merge_premium(free: dict, premium: list[dict]) -> dict:
    """Complète les périodes gratuites avec les agrégats payants.

    L'ancrage des colonnes reste celui de la source gratuite, dont on sait
    qu'il se raccorde aux comptes publiés. Le consensus payant n'apporte que
    des agrégats supplémentaires et des exercices plus lointains.
    """
    if not premium:
        return free

    periods = list(free.get("periods") or [])
    anchor_year = None
    if periods and free.get("fiscal_year_end"):
        try:
            anchor_year = dt.date.fromisoformat(free["fiscal_year_end"][:10]).year + 1
        except ValueError:
            anchor_year = None
    if anchor_year is None:
        return free

    by_offset = {int(p.get("offset") or 0): p for p in periods}
    for bucket in premium:
        offset = bucket["year"] - anchor_year
        if offset < 0:
            continue
        target = by_offset.setdefault(offset, {"offset": offset})
        for key in ("eps", "revenue", "ebitda", "analysts"):
            if bucket.get(key) is not None and target.get(key) is None:
                target[key] = bucket[key]

    return {**free, "periods": [by_offset[k] for k in sorted(by_offset)]}


async def consensus(symbol: str) -> dict:
    """Estimations de bénéfice et de chiffre d'affaires, et cible de cours.

    Renvoie toujours une structure exploitable : un titre non suivi donne une
    liste de périodes vide, pas une exception. L'écran doit pouvoir afficher
    l'historique même sans consensus.

    Une clé payante configurée enrichit le résultat — EBITDA estimé, exercices
    plus lointains — sans changer la forme des données ni le comportement en
    cas d'échec.
    """

    async def produce():
        try:
            free = await asyncio.to_thread(_fetch, symbol)
        except Exception:  # noqa: BLE001
            free = None
        if free is None:
            return {
                "periods": [],
                "fiscal_year_end": None,
                "price_target": {},
                "currency": None,
                "trailing_eps": None,
                "listing_currency": None,
                "dividend_rate": None,
            }

        provider = settings.premium_provider
        if provider is None:
            return free
        try:
            premium = await asyncio.to_thread(_premium_periods, symbol, provider)
        except Exception:  # noqa: BLE001
            premium = []
        return _merge_premium(free, premium)

    # La clé de cache porte le fournisseur : poser ou retirer une clé d'API
    # doit invalider les estimations, non ressortir celles de l'autre source.
    key = f"estimates:v3:{settings.premium_provider or 'free'}:{symbol}"
    value, _, _ = await cache.resolve(key, TTL_SECONDS, produce)
    return value


__all__ = ["consensus", "TTL_SECONDS", "THIN_COVERAGE"]
