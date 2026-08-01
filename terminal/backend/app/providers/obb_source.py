"""Accès aux données de marché via OpenBB.

Point d'entrée unique vers ``obb.*``. Les appels OpenBB sont synchrones et
bloquants : ils sont déportés dans un thread pour ne pas figer la boucle
asyncio de FastAPI. Chaque résultat passe par le cache à TTL.

Provider par défaut : ``yfinance``, qui couvre les 15 places européennes
visées sans aucune clé d'API. Les cotations Euronext/XETRA en sont différées
d'environ 15 minutes — l'horodatage remonté au client le signale.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
from typing import Any

import pandas as pd
from openbb import obb

from ..cache import cache
from ..settings import settings

obb.user.preferences.output_type = "dataframe"

DEFAULT_PROVIDER = "yfinance"

#: Décalage appliqué entre la clôture d'exercice et la disponibilité publique
#: des comptes. Les grandes capitalisations européennes publient leurs comptes
#: annuels deux à trois mois après la clôture ; utiliser la date de clôture
#: telle quelle introduirait un biais de look-ahead dans les multiples.
PUBLICATION_LAG_DAYS = 90


class DataUnavailable(RuntimeError):
    """Aucune donnée exploitable pour ce symbole."""


def _clean(value: Any) -> Any:
    """Rend une valeur sérialisable en JSON strict (pas de NaN ni d'Infinity)."""
    if value is None:
        return None
    if isinstance(value, float):
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (pd.Timestamp,)):
        return value.to_pydatetime().isoformat()
    if value is pd.NaT:
        return None
    if isinstance(value, (int, str, bool)):
        return value
    if hasattr(value, "item"):  # scalaires numpy
        try:
            return _clean(value.item())
        except Exception:  # noqa: BLE001
            return str(value)
    return str(value)


def _records(df: pd.DataFrame, index_name: str | None = None) -> list[dict]:
    """Convertit un DataFrame OpenBB en liste de dictionnaires propres."""
    if df is None or len(df) == 0:
        return []
    frame = df.reset_index() if index_name else df
    return [
        {str(k): _clean(v) for k, v in row.items()}
        for row in frame.to_dict(orient="records")
    ]


async def _run(fn, *args, **kwargs):
    """Exécute un appel OpenBB bloquant dans un thread."""
    return await asyncio.to_thread(fn, *args, **kwargs)


# ---------------------------------------------------------------------------
# Cotations et historiques
# ---------------------------------------------------------------------------


async def quote(symbol: str, provider: str = DEFAULT_PROVIDER) -> dict:
    """Dernière cotation connue."""

    async def produce():
        df = await _run(obb.equity.price.quote, symbol, provider=provider)
        rows = _records(df)
        if not rows:
            raise DataUnavailable(f"Aucune cotation pour {symbol}")
        return rows[0]

    value, stored_at, _ = await cache.resolve(
        f"quote:{provider}:{symbol}", settings.ttl_quote, produce
    )
    return {**value, "as_of": dt.datetime.fromtimestamp(stored_at).isoformat()}


async def historical(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
    provider: str = DEFAULT_PROVIDER,
) -> list[dict]:
    """Série OHLCV. ``interval`` accepte 1m, 5m, 15m, 1h, 1d, 1W, 1M."""
    ttl = settings.ttl_historical if interval == "1d" else settings.ttl_intraday

    async def produce():
        kwargs: dict[str, Any] = {"provider": provider, "interval": interval}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        df = await _run(obb.equity.price.historical, symbol, **kwargs)
        return _records(df, index_name="date")

    key = f"hist:{provider}:{symbol}:{interval}:{start_date}:{end_date}"
    value, _, _ = await cache.resolve(key, ttl, produce)
    return value


async def index_historical(
    symbol: str,
    start_date: str | None = None,
    provider: str = DEFAULT_PROVIDER,
) -> list[dict]:
    """Série OHLCV d'un indice (``^FCHI``, ``^GDAXI``, ``^STOXX50E``...)."""

    async def produce():
        kwargs: dict[str, Any] = {"provider": provider}
        if start_date:
            kwargs["start_date"] = start_date
        df = await _run(obb.index.price.historical, symbol, **kwargs)
        return _records(df, index_name="date")

    key = f"idx:{provider}:{symbol}:{start_date}"
    value, _, _ = await cache.resolve(key, settings.ttl_historical, produce)
    return value


# ---------------------------------------------------------------------------
# Société
# ---------------------------------------------------------------------------


async def profile(symbol: str, provider: str = DEFAULT_PROVIDER) -> dict:
    """Profil société — porte notamment ``hq_country``, base du verdict PEA."""

    async def produce():
        df = await _run(obb.equity.profile, symbol, provider=provider)
        rows = _records(df)
        if not rows:
            raise DataUnavailable(f"Aucun profil pour {symbol}")
        return rows[0]

    value, _, _ = await cache.resolve(
        f"profile:{provider}:{symbol}", settings.ttl_profile, produce
    )
    return value


#: Ratios que la source exprime en **points de pourcentage** alors que ses
#: autres ratios sont des fractions.
#:
#: Le même objet renvoie ``dividend_yield = 2.74`` (soit 2,74 %) et
#: ``dividend_yield_5y_avg = 0.0183`` (soit 1,83 %), ou encore
#: ``debt_to_equity = 53.3`` face à ``return_on_equity = 0.166``. Laisser
#: passer ce mélange donne un rendement affiché à 274 %. On ramène tout à la
#: fraction, une bonne fois, à l'entrée.
_PERCENT_POINT_FIELDS = ("dividend_yield", "debt_to_equity")


def _normalize_metrics(row: dict) -> dict:
    for field in _PERCENT_POINT_FIELDS:
        value = row.get(field)
        if isinstance(value, (int, float)):
            row[field] = value / 100.0
    return row


async def metrics(symbol: str, provider: str = DEFAULT_PROVIDER) -> dict:
    """Ratios courants (ROE, marges, endettement, PER, P/B...).

    Tous les ratios sortent d'ici exprimés en **fraction** : 0,0274 pour un
    rendement de 2,74 %.
    """

    async def produce():
        df = await _run(obb.equity.fundamental.metrics, symbol, provider=provider)
        rows = _records(df)
        return _normalize_metrics(rows[0]) if rows else {}

    # Le suffixe de version invalide les entrées mises en cache avant que la
    # normalisation n'existe.
    value, _, _ = await cache.resolve(
        f"metrics:v2:{provider}:{symbol}", settings.ttl_fundamentals, produce
    )
    return value


async def _statement(
    kind: str, symbol: str, period: str, limit: int, provider: str
) -> list[dict]:
    fetchers = {
        "income": obb.equity.fundamental.income,
        "balance": obb.equity.fundamental.balance,
        "cash": obb.equity.fundamental.cash,
    }

    async def produce():
        df = await _run(
            fetchers[kind], symbol, provider=provider, period=period, limit=limit
        )
        return _records(df)

    key = f"stmt:{kind}:{provider}:{symbol}:{period}:{limit}"
    value, _, _ = await cache.resolve(key, settings.ttl_fundamentals, produce)
    return value


async def statements(
    symbol: str,
    period: str = "annual",
    limit: int = 5,
    provider: str = DEFAULT_PROVIDER,
) -> dict[str, list[dict]]:
    """Les trois états financiers, récupérés en parallèle.

    ``limit`` est plafonné à 5 : c'est la borne imposée par OpenBB pour
    yfinance, et Yahoo ne publie de toute façon pas davantage d'exercices.
    """
    limit = max(1, min(limit, 5))
    income, balance, cash = await asyncio.gather(
        _statement("income", symbol, period, limit, provider),
        _statement("balance", symbol, period, limit, provider),
        _statement("cash", symbol, period, limit, provider),
        return_exceptions=True,
    )

    def ok(result):
        return result if isinstance(result, list) else []

    return {"income": ok(income), "balance": ok(balance), "cash": ok(cash)}


async def dividends(symbol: str, provider: str = DEFAULT_PROVIDER) -> list[dict]:
    """Historique des dividendes (date de détachement, montant)."""

    async def produce():
        df = await _run(obb.equity.fundamental.dividends, symbol, provider=provider)
        return _records(df)

    value, _, _ = await cache.resolve(
        f"div:{provider}:{symbol}", settings.ttl_fundamentals, produce
    )
    return value


async def news(symbol: str, limit: int = 20, provider: str = DEFAULT_PROVIDER) -> list[dict]:
    """Actualités liées au titre."""

    async def produce():
        df = await _run(obb.news.company, symbol, provider=provider, limit=limit)
        return _records(df, index_name="date")

    value, _, _ = await cache.resolve(
        f"news:{provider}:{symbol}:{limit}", settings.ttl_news, produce
    )
    return value


def publication_date(period_ending: str | dt.date) -> dt.date:
    """Date à partir de laquelle des comptes clos peuvent être réputés publics."""
    if isinstance(period_ending, str):
        period_ending = dt.date.fromisoformat(period_ending[:10])
    return period_ending + dt.timedelta(days=PUBLICATION_LAG_DAYS)
