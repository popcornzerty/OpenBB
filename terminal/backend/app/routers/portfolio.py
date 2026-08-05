"""Portefeuille : positions, dividendes, répartition et cibles.

Le terminal est propriétaire des positions. Wealthfolio reste disponible en
**source d'import initial**, pour ne pas ressaisir un portefeuille déjà tenu
ailleurs, mais n'alimente plus l'affichage.
"""

from __future__ import annotations

import asyncio
import datetime as dt

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..pea import registry
from ..pea.eligibility import Eligibility, assess
from ..portfolio import allocation, dividends, realized, store, targets
from ..portfolio.realized import Sale
from ..portfolio.store import Position
from ..providers import obb_source, wealthfolio_db, yahoo_search
from ..providers.wealthfolio_db import PortfolioUnavailable

router = APIRouter(prefix="/api/portfolio", tags=["portefeuille"])


class PositionPayload(BaseModel):
    """Une position saisie ou modifiée à la main."""

    symbol: str = Field(min_length=1)
    quantity: float
    average_cost: float = 0.0
    currency: str = "EUR"
    opened_at: str = ""
    label: str = ""


class TargetsPayload(BaseModel):
    sectors: dict[str, float] = Field(default_factory=dict)
    regions: dict[str, float] = Field(default_factory=dict)


async def _enrich(position: Position, with_dividends: bool) -> dict:
    """Complète une position : cotation, éligibilité PEA, secteur, dividendes."""
    row = position.as_dict()

    try:
        quote = await obb_source.quote(position.symbol)
        price = quote.get("last_price")
        row["price_source"] = "last"
        if price is None:
            price = quote.get("prev_close")
            row["price_source"] = "prev_close" if price is not None else "none"
        row["price"] = price
        row["name"] = row.get("label") or quote.get("name")
        row["market_value"] = price * position.quantity if price is not None else None
        row["as_of"] = quote.get("as_of")
    except Exception:  # noqa: BLE001
        row["price"] = row["market_value"] = row["as_of"] = None
        row["price_source"] = "none"
        row["name"] = row.get("label") or position.symbol

    cost = position.cost_basis
    if row["market_value"] is not None and cost:
        row["gain"] = row["market_value"] - cost
        row["gain_percent"] = row["gain"] / cost
    else:
        row["gain"] = row["gain_percent"] = None

    entry = registry.get(position.symbol)
    if entry is not None:
        row["sector"] = entry.sector or None
        row["country_label"] = entry.country_label or None
        row["pea_status"] = entry.pea_status
        row["pea_reason"] = entry.pea_reason
    else:
        # Hors univers — un ETF le plus souvent : on interroge son profil.
        try:
            profile = await obb_source.profile(position.symbol)
            verdict = assess(position.symbol, profile.get("hq_country"))
            row["sector"] = profile.get("sector") or None
            row["country_label"] = verdict.country_label
            row["pea_status"] = verdict.status.value
            row["pea_reason"] = verdict.reason
            row["name"] = row.get("label") or profile.get("name") or row["name"]
        except Exception:  # noqa: BLE001
            row["sector"] = row["country_label"] = None
            row["pea_status"] = Eligibility.UNKNOWN.value
            row["pea_reason"] = "Profil indisponible : éligibilité non établie."

    if with_dividends:
        row["dividend"] = await dividends.for_position(
            position.symbol, position.quantity, position.opened_at or None
        )
    return row


async def _resolve_isins(positions: list[Position]) -> tuple[list[Position], list[str]]:
    """Remplace les ISIN par leur ticker, en signalant les échecs."""
    unresolved: list[str] = []

    async def resolve(position: Position) -> Position:
        if not yahoo_search.looks_like_isin(position.symbol):
            return position
        try:
            ticker = await yahoo_search.resolve_isin(position.symbol)
        except Exception:  # noqa: BLE001
            ticker = None
        if not ticker:
            unresolved.append(position.symbol)
            return position
        # L'ISIN d'origine devient le libellé si aucun n'était fourni, pour
        # que la correspondance reste traçable.
        position.label = position.label or position.symbol
        position.symbol = ticker
        return position

    return list(await asyncio.gather(*(resolve(p) for p in positions))), unresolved


@router.get("/positions")
async def list_positions() -> dict:
    """Positions brutes, sans interrogation du marché."""
    return store.load().as_dict()


@router.put("/positions/{symbol}")
async def upsert_position(symbol: str, payload: PositionPayload) -> dict:
    """Crée ou remplace une position."""
    if payload.quantity <= 0:
        raise HTTPException(422, "La quantité doit être strictement positive.")
    position = Position(
        symbol=symbol.upper(),
        quantity=payload.quantity,
        average_cost=payload.average_cost,
        currency=payload.currency or "EUR",
        opened_at=payload.opened_at[:10],
        label=payload.label,
    )
    return store.upsert(position).as_dict()


@router.delete("/positions/{symbol}")
async def delete_position(symbol: str) -> dict:
    """Retire une position **sans rien enregistrer**.

    À réserver aux saisies erronées. Une vente passe par ``/sell``, qui
    conserve la plus-value réalisée et les dividendes encaissés.
    """
    return store.remove(symbol).as_dict()


class SalePayload(BaseModel):
    """Une cession, totale ou partielle."""

    quantity: float | None = None  # None ⇒ toute la ligne
    price: float = Field(gt=0)
    date: str = ""
    note: str = ""


@router.post("/positions/{symbol}/sell")
async def sell_position(symbol: str, payload: SalePayload) -> dict:
    """Vend tout ou partie d'une ligne et enregistre la plus-value réalisée.

    Le prix de revient unitaire ne bouge pas lors d'une vente partielle : ce
    qui reste a été payé au même prix moyen qu'avant.
    """
    target = symbol.upper()
    portfolio = store.load()
    position = next((p for p in portfolio.positions if p.symbol == target), None)
    if position is None:
        raise HTTPException(404, f"{target} n'est pas en portefeuille.")

    quantity = position.quantity if payload.quantity is None else payload.quantity
    if quantity <= 0:
        raise HTTPException(422, "La quantité vendue doit être strictement positive.")
    if quantity > position.quantity + 1e-9:
        raise HTTPException(
            422,
            f"Vous détenez {position.quantity:g} titre(s) de {target}, "
            f"impossible d'en vendre {quantity:g}.",
        )

    closed_at = (payload.date or dt.date.today().isoformat())[:10]

    # Les dividendes perçus sur les titres vendus sont figés maintenant : une
    # fois la ligne partie, plus rien ne permettrait de les recalculer.
    collected = 0.0
    try:
        block = await dividends.for_position(target, quantity, position.opened_at or None)
        collected = (block.get("accrued") or {}).get("amount") or 0.0
    except Exception:  # noqa: BLE001
        collected = 0.0

    sale = Sale(
        symbol=target,
        quantity=quantity,
        average_cost=position.average_cost,
        sale_price=payload.price,
        currency=position.currency,
        opened_at=position.opened_at,
        closed_at=closed_at,
        label=position.label,
        dividends=round(collected, 2),
        note=payload.note,
    )
    realized.add(sale)

    remaining = position.quantity - quantity
    if remaining <= 1e-9:
        store.remove(target)
    else:
        position.quantity = remaining
        store.upsert(position)

    return {"sale": sale.as_dict(), "remaining": round(max(remaining, 0.0), 6)}


@router.get("/realized")
async def list_realized() -> dict:
    """Historique des cessions et cumuls."""
    sales = realized.load()
    return {
        "sales": [s.as_dict() for s in sales],
        "totals": realized.totals(sales),
    }


@router.delete("/realized/{sale_id}")
async def cancel_sale(
    sale_id: str,
    restore: bool = Query(True, description="Remettre les titres en portefeuille"),
) -> dict:
    """Annule une cession saisie par erreur.

    Par défaut les titres reviennent en portefeuille au prix de revient
    d'origine — c'est le sens d'une annulation.
    """
    sale = realized.get(sale_id)
    if sale is None:
        raise HTTPException(404, "Cession introuvable.")

    realized.remove(sale_id)
    if restore:
        portfolio = store.load()
        existing = next((p for p in portfolio.positions if p.symbol == sale.symbol), None)
        if existing is None:
            store.upsert(
                Position(
                    symbol=sale.symbol,
                    quantity=sale.quantity,
                    average_cost=sale.average_cost,
                    currency=sale.currency,
                    opened_at=sale.opened_at,
                    label=sale.label,
                )
            )
        else:
            # La ligne existe encore : on remet les titres en conservant un
            # prix de revient moyen cohérent entre les deux lots.
            total_quantity = existing.quantity + sale.quantity
            existing.average_cost = (
                existing.cost_basis + sale.cost_basis
            ) / total_quantity
            existing.quantity = total_quantity
            store.upsert(existing)

    return {"cancelled": sale.as_dict(), "restored": restore}


class CsvPayload(BaseModel):
    content: str
    replace: bool = True


@router.post("/positions/import-csv")
async def import_csv(payload: CsvPayload) -> dict:
    """Importe des positions depuis un CSV.

    ``replace`` remplace tout le portefeuille ; sinon les lignes complètent
    l'existant, une même valeur écrasant la précédente.
    """
    positions, warnings = store.parse_csv(payload.content)
    if not positions:
        raise HTTPException(422, " ".join(warnings) or "Fichier inexploitable.")

    # Les relevés de courtiers français identifient les titres par ISIN. Les
    # enregistrer tels quels donnerait un portefeuille sans aucune cotation :
    # on les résout en tickers, et on signale ceux qui résistent.
    resolved, unresolved = await _resolve_isins(positions)
    positions = resolved
    if unresolved:
        warnings.append(
            "ISIN non résolus, conservés tels quels : " + ", ".join(unresolved) + "."
        )

    if payload.replace:
        portfolio = store.replace_all(positions)
    else:
        for position in positions:
            portfolio = store.upsert(position)

    return {**portfolio.as_dict(), "imported": len(positions), "warnings": warnings}


@router.post("/positions/import-wealthfolio")
async def import_from_wealthfolio(replace: bool = True) -> dict:
    """Reprend les positions tenues dans Wealthfolio.

    Import ponctuel : le terminal reste ensuite maître de ses positions, et
    une modification ici ne remonte jamais vers Wealthfolio.
    """
    try:
        source = await asyncio.to_thread(wealthfolio_db.read_positions)
    except PortfolioUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    positions = [
        Position(
            symbol=p.symbol,
            quantity=p.quantity,
            average_cost=p.average_cost,
            currency=p.currency,
            opened_at=p.snapshot_date,
            label=p.name,
        )
        for p in source
    ]
    if not positions:
        raise HTTPException(404, "Aucune position trouvée dans Wealthfolio.")

    if replace:
        portfolio = store.replace_all(positions)
    else:
        for position in positions:
            portfolio = store.upsert(position)
    return {**portfolio.as_dict(), "imported": len(positions)}


@router.get("/holdings")
async def holdings(
    with_dividends: bool = Query(True, description="Joindre les dividendes"),
) -> dict:
    """Positions valorisées, avec dividendes perçus et à venir."""
    portfolio = store.load()
    if not portfolio.positions:
        return {
            "rows": [],
            "summary": None,
            "updated_at": portfolio.updated_at,
            "empty": True,
        }

    rows = list(
        await asyncio.gather(*(_enrich(p, with_dividends) for p in portfolio.positions))
    )
    rows.sort(key=lambda r: -(r.get("market_value") or 0))

    total_value = sum(r.get("market_value") or 0 for r in rows)
    total_cost = sum(r.get("cost_basis") or 0 for r in rows)
    eligible = sum(
        r.get("market_value") or 0 for r in rows if r.get("pea_status") == "eligible"
    )
    collected = sum(
        (r.get("dividend") or {}).get("accrued", {}).get("amount") or 0 for r in rows
    )

    sales = realized.load()
    closed = realized.totals(sales)
    # Les dividendes des lignes vendues restent acquis : les oublier ferait
    # reculer le cumul à chaque arbitrage.
    collected += closed["dividends"]

    upcoming = [
        {
            "symbol": r["symbol"],
            "date": (r.get("dividend") or {}).get("next_ex_date"),
            "amount": (r.get("dividend") or {}).get("next_estimated_amount"),
        }
        for r in rows
        if (r.get("dividend") or {}).get("next_ex_date")
    ]
    upcoming.sort(key=lambda x: x["date"])

    return {
        "rows": rows,
        "updated_at": portfolio.updated_at,
        "empty": False,
        "summary": {
            "positions": len(rows),
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain": round(total_value - total_cost, 2),
            "total_gain_percent": (
                round((total_value - total_cost) / total_cost, 4) if total_cost else None
            ),
            "confirmed_pea_value": round(eligible, 2),
            "confirmed_pea_share": round(eligible / total_value, 4) if total_value else None,
            # Cumul des dividendes détachés depuis l'entrée en position, à
            # quantité supposée constante.
            "dividends_collected": round(collected, 2),
            "dividend_yield_on_cost": (
                round(collected / total_cost, 4) if total_cost else None
            ),
            "realized": closed,
            # Ce que le portefeuille a rapporté au total : la plus-value
            # latente seule ignore les arbitrages déjà encaissés.
            "overall_gain": round(
                (total_value - total_cost) + closed["gain"] + collected, 2
            ),
            "upcoming": upcoming[:8],
        },
    }


@router.get("/allocation")
async def get_allocation() -> dict:
    """Répartition sectorielle et géographique, confrontée aux cibles."""
    data = await holdings(with_dividends=False)
    if data["empty"]:
        raise HTTPException(404, "Portefeuille vide.")

    breakdown = await allocation.compute(data["rows"])
    saved = targets.load()
    return {
        **breakdown,
        "targets": saved,
        "sector_comparison": targets.compare(breakdown["sectors"], saved["sectors"]),
        "region_comparison": targets.compare(breakdown["regions"], saved["regions"]),
        "targets_total": {
            "sectors": targets.total(saved["sectors"]),
            "regions": targets.total(saved["regions"]),
        },
    }


@router.get("/targets")
async def get_targets() -> dict:
    saved = targets.load()
    return {
        **saved,
        "totals": {
            "sectors": targets.total(saved["sectors"]),
            "regions": targets.total(saved["regions"]),
        },
    }


@router.put("/targets")
async def put_targets(payload: TargetsPayload) -> dict:
    """Enregistre vos pondérations cibles.

    La somme n'est pas contrainte à 100 % : une cible partielle, portant sur
    quelques secteurs seulement, reste utile.
    """
    saved = targets.save({"sectors": payload.sectors, "regions": payload.regions})
    return {
        **saved,
        "totals": {
            "sectors": targets.total(saved["sectors"]),
            "regions": targets.total(saved["regions"]),
        },
    }


@router.get("/status")
async def status() -> dict:
    """État du portefeuille et disponibilité de l'import Wealthfolio."""
    portfolio = store.load()
    path = wealthfolio_db.database_path()
    available = path.exists()
    count = 0
    if available:
        try:
            count = len(await asyncio.to_thread(wealthfolio_db.read_positions))
        except PortfolioUnavailable:
            available = False
    return {
        "positions": len(portfolio.positions),
        "updated_at": portfolio.updated_at,
        "today": dt.date.today().isoformat(),
        "wealthfolio": {
            "available": available,
            "database": str(path),
            "positions": count,
        },
    }
