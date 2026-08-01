"""Recherche de titres par nom, ticker ou ISIN.

Comble un trou réel d'OpenBB : aucun provider fourni ne permet de rechercher
une action européenne sans clé payante (``intrinio`` exige une clé, ``sec`` ne
couvre que les États-Unis). L'endpoint de recherche Yahoo, lui, résout aussi
bien « LVMH » que « FR0000121014 », ce qui compte pour un terminal PEA : les
brokers français raisonnent en ISIN.
"""

from __future__ import annotations

import re
from typing import Any

import aiohttp

from ..cache import cache
from ..settings import settings

_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

#: Un ISIN : 2 lettres de pays, 9 caractères alphanumériques, 1 chiffre de contrôle.
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")

#: Codes de place Yahoo -> libellé et pays de cotation.
#:
#: Le pays de **cotation** ne détermine pas l'éligibilité PEA (c'est le siège
#: qui compte) mais sert à classer les résultats et à privilégier la ligne
#: européenne d'un titre coté sur plusieurs places.
EXCHANGES: dict[str, tuple[str, str]] = {
    "PAR": ("Euronext Paris", "FR"),
    "AMS": ("Euronext Amsterdam", "NL"),
    "BRU": ("Euronext Bruxelles", "BE"),
    "LIS": ("Euronext Lisbonne", "PT"),
    "DUB": ("Euronext Dublin", "IE"),
    "OSL": ("Euronext Oslo", "NO"),
    "GER": ("XETRA", "DE"),
    "FRA": ("Francfort", "DE"),
    "BER": ("Berlin", "DE"),
    "STU": ("Stuttgart", "DE"),
    "HAM": ("Hambourg", "DE"),
    "DUS": ("Düsseldorf", "DE"),
    "MUN": ("Munich", "DE"),
    "MIL": ("Borsa Italiana", "IT"),
    "MCE": ("BME Madrid", "ES"),
    "CPH": ("Nasdaq Copenhague", "DK"),
    "STO": ("Nasdaq Stockholm", "SE"),
    "HEL": ("Nasdaq Helsinki", "FI"),
    "ICE": ("Nasdaq Reykjavik", "IS"),
    "RIS": ("Nasdaq Riga", "LV"),
    "TAL": ("Nasdaq Tallinn", "EE"),
    "VSE": ("Nasdaq Vilnius", "LT"),
    "VIE": ("Wiener Börse", "AT"),
    "WSE": ("GPW Varsovie", "PL"),
    "PRA": ("Bourse de Prague", "CZ"),
    "BUD": ("Bourse de Budapest", "HU"),
    "ATH": ("Bourse d'Athènes", "GR"),
    # Hors EEE — conservés pour pouvoir écarter explicitement ces lignes.
    "EBS": ("SIX Swiss Exchange", "CH"),
    "LSE": ("London Stock Exchange", "GB"),
    "IOB": ("London International", "GB"),
    "NYQ": ("NYSE", "US"),
    "NMS": ("Nasdaq", "US"),
    "PNK": ("OTC Pink", "US"),
    "NEO": ("NEO Exchange", "CA"),
    "TOR": ("Toronto", "CA"),
}

#: Suffixe de ticker Yahoo -> code de place.
SUFFIX_TO_EXCHANGE = {
    ".PA": "PAR", ".AS": "AMS", ".BR": "BRU", ".LS": "LIS", ".IR": "DUB",
    ".OL": "OSL", ".DE": "GER", ".F": "FRA", ".BE": "BER", ".SG": "STU",
    ".MI": "MIL", ".MC": "MCE", ".CO": "CPH", ".ST": "STO", ".HE": "HEL",
    ".IC": "ICE", ".RG": "RIS", ".TL": "TAL", ".VS": "VSE", ".VI": "VIE",
    ".WA": "WSE", ".PR": "PRA", ".BD": "BUD", ".AT": "ATH", ".SW": "EBS",
    ".L": "LSE",
}

#: Places situées dans l'EEE — sert au classement, pas au verdict PEA.
EEA_EXCHANGE_CODES = {
    code for code, (_, country) in EXCHANGES.items()
    if country not in {"CH", "GB", "US", "CA"}
}


def looks_like_isin(query: str) -> bool:
    return bool(ISIN_RE.match(query.strip().upper()))


def exchange_info(symbol: str, exchange_code: str | None = None) -> tuple[str | None, str | None]:
    """Renvoie ``(libellé de place, pays de cotation)``."""
    code = exchange_code
    if not code:
        for suffix, mapped in SUFFIX_TO_EXCHANGE.items():
            if symbol.upper().endswith(suffix):
                code = mapped
                break
    if not code:
        return None, None
    label, country = EXCHANGES.get(code, (code, None))
    return label, country


def _rank(item: dict) -> tuple:
    """Ordre de tri : lignes EEE d'abord, puis actions, puis pertinence Yahoo."""
    exch = item.get("exchange_code") or ""
    return (
        0 if exch in EEA_EXCHANGE_CODES else 1,
        0 if item.get("quote_type") == "EQUITY" else 1,
        item.get("_position", 99),
    )


async def search(query: str, limit: int = 15) -> list[dict[str, Any]]:
    """Recherche un titre par nom, ticker ou ISIN.

    Les lignes cotées dans l'EEE remontent en tête : un même titre étant
    souvent coté sur plusieurs places, c'est la ligne européenne qui intéresse
    un porteur de PEA.
    """
    query = query.strip()
    if not query:
        return []

    async def produce():
        params = {
            "q": query,
            "quotesCount": str(max(limit, 10)),
            "newsCount": "0",
            "enableFuzzyQuery": "false",
        }
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(_SEARCH_URL, params=params) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)

        results = []
        for position, quote in enumerate(payload.get("quotes", [])):
            symbol = quote.get("symbol")
            if not symbol:
                continue
            code = quote.get("exchange")
            label, country = exchange_info(symbol, code)
            results.append(
                {
                    "symbol": symbol,
                    "name": quote.get("longname") or quote.get("shortname") or symbol,
                    "quote_type": quote.get("quoteType"),
                    "exchange_code": code,
                    "exchange": label or quote.get("exchDisp"),
                    "listing_country": country,
                    "_position": position,
                }
            )
        results.sort(key=_rank)
        for item in results:
            item.pop("_position", None)
        return results[:limit]

    key = f"search:{query.casefold()}:{limit}"
    value, _, _ = await cache.resolve(key, settings.ttl_search, produce)
    return value


async def resolve_isin(isin: str) -> str | None:
    """Retourne le ticker de la ligne principale correspondant à un ISIN."""
    results = await search(isin, limit=5)
    for item in results:
        if item.get("quote_type") == "EQUITY":
            return item["symbol"]
    return results[0]["symbol"] if results else None
