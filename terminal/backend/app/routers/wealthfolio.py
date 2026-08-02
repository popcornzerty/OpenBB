"""Pont vers Wealthfolio.

Wealthfolio sait consommer n'importe quelle source de marché déclarée comme
« fournisseur personnalisé » : une URL à gabarit et des chemins JSONPath, sans
code à écrire côté Rust. Ces routes exposent donc les données du Terminal PEA
dans une forme **plate et stable**, taillée pour ce mode de consommation.

Pourquoi ne pas réutiliser les routes existantes ? Parce qu'un JSONPath est un
couplage : `$.last_price` gravé dans la configuration de Wealthfolio casserait
au premier renommage interne. Ce namespace est un contrat public, versionné à
part du reste de l'API.

Valeur ajoutée par rapport à un branchement direct sur Yahoo : le symbole
accepté peut être un **ISIN**, et chaque réponse porte le verdict d'éligibilité
PEA du titre.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Query

from ..pea import registry
from ..pea.eligibility import Eligibility, assess
from ..providers import obb_source, yahoo_search

router = APIRouter(prefix="/api/wf", tags=["wealthfolio"])


async def _resolve(symbol: str) -> str:
    """Accepte un ticker ou un ISIN et renvoie toujours un ticker.

    Les relevés de brokers français désignent les titres par ISIN ; pouvoir en
    coller un directement dans Wealthfolio évite une conversion manuelle.
    """
    candidate = symbol.strip().upper()
    if not yahoo_search.looks_like_isin(candidate):
        return candidate
    resolved = await yahoo_search.resolve_isin(candidate)
    if not resolved:
        raise HTTPException(404, f"ISIN non résolu : {candidate}")
    return resolved


def _num(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


@router.get("/quote/{symbol}")
async def quote(symbol: str) -> dict:
    """Dernier cours connu, en champs plats.

    Chemins JSONPath : ``$.price``, ``$.date``, ``$.currency``, ``$.open``,
    ``$.high``, ``$.low``, ``$.volume``.
    """
    ticker = await _resolve(symbol)
    try:
        data = await obb_source.quote(ticker)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Cotation indisponible pour {ticker}") from exc

    entry = registry.get(ticker)
    if entry is not None:
        status = entry.pea_status
    else:
        try:
            profile = await obb_source.profile(ticker)
            status = assess(ticker, profile.get("hq_country")).status.value
        except Exception:  # noqa: BLE001
            status = Eligibility.UNKNOWN.value

    as_of = data.get("as_of") or dt.datetime.now().isoformat()

    # Certains instruments — les ETF en particulier — remontent sans dernier
    # cours alors que l'ouverture et la clôture précédente sont présentes.
    # Renvoyer `null` priverait Wealthfolio de toute valorisation ; on se
    # rabat sur la clôture précédente en le signalant.
    price = _num(data.get("last_price"))
    price_source = "last"
    if price is None:
        price = _num(data.get("prev_close"))
        price_source = "prev_close" if price is not None else "none"

    return {
        "symbol": ticker,
        "name": data.get("name"),
        "price": price,
        "price_source": price_source,
        # Wealthfolio attend une date de séance, pas un horodatage de collecte.
        "date": as_of[:10],
        "currency": data.get("currency"),
        "open": _num(data.get("open")),
        "high": _num(data.get("high")),
        "low": _num(data.get("low")),
        "volume": _num(data.get("volume")),
        "previous_close": _num(data.get("prev_close")),
        "pea_status": status,
        # Les cotations Euronext et XETRA passant par une source gratuite sont
        # différées : le signaler évite de les prendre pour du temps réel.
        "delayed": True,
        "as_of": as_of,
    }


@router.get("/history/{symbol}")
async def history(
    symbol: str,
    start: str | None = Query(None, alias="from", description="AAAA-MM-JJ"),
    end: str | None = Query(None, alias="to", description="AAAA-MM-JJ"),
) -> dict:
    """Série quotidienne, sous forme de tableau d'objets.

    Chemins JSONPath : ``$.rows[*].close``, ``$.rows[*].date``,
    ``$.rows[*].open``, ``$.rows[*].high``, ``$.rows[*].low``,
    ``$.rows[*].volume``.
    """
    ticker = await _resolve(symbol)
    try:
        rows = await obb_source.historical(ticker, start_date=start, end_date=end)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Historique indisponible pour {ticker}") from exc

    currency = None
    entry = registry.get(ticker)
    if entry is not None and entry.currency:
        currency = entry.currency

    return {
        "symbol": ticker,
        "currency": currency,
        "rows": [
            {
                "date": str(row.get("date"))[:10],
                "open": _num(row.get("open")),
                "high": _num(row.get("high")),
                "low": _num(row.get("low")),
                "close": _num(row.get("close")),
                "volume": _num(row.get("volume")),
            }
            for row in rows
        ],
    }


@router.get("/pea/{symbol}")
async def pea_status(symbol: str) -> dict:
    """Verdict d'éligibilité PEA d'un titre, avec sa justification.

    C'est ce que Wealthfolio ne peut pas déduire seul : l'éligibilité dépend du
    pays du **siège social**, pas de la place de cotation.
    """
    ticker = await _resolve(symbol)

    entry = registry.get(ticker)
    if entry is not None:
        return {
            "symbol": ticker,
            "name": entry.name,
            "eligible": entry.pea_status == Eligibility.ELIGIBLE.value,
            "status": entry.pea_status,
            "country_iso": entry.country_iso or None,
            "country_label": entry.country_label or None,
            "reason": entry.pea_reason,
            "source": "univers",
        }

    try:
        profile = await obb_source.profile(ticker)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, f"Titre introuvable : {ticker}") from exc

    verdict = assess(ticker, profile.get("hq_country"))
    return {
        "symbol": ticker,
        "name": profile.get("name"),
        "eligible": verdict.is_eligible,
        "status": verdict.status.value,
        "country_iso": verdict.country_iso,
        "country_label": verdict.country_label,
        "reason": verdict.reason,
        "source": "profil",
    }
