"""Dividendes du portefeuille : perçus et à venir.

Ne sont comptés que les détachements **postérieurs à l'entrée en position** :
c'est ce que vous avez réellement touché depuis que vous détenez le titre.
Additionner tout l'historique gonflerait le cumul de dividendes versés à des
porteurs qui n'étaient pas vous.
"""

from __future__ import annotations

import datetime as dt

from ..pea.dividends import next_ex_date
from ..providers import obb_source


def _as_date(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def accrued(rows: list[dict], since: dt.date | None, quantity: float) -> dict:
    """Dividendes encaissés depuis ``since``, pour ``quantity`` titres.

    Le calcul suppose la quantité constante sur la période : le terminal ne
    tient pas d'historique de mouvements. Un renforcement en cours d'année
    surestime donc les premiers détachements, ce que l'interface signale.
    """
    if since is None:
        return {"amount": None, "payments": 0, "per_share": None, "last": None}

    per_share = 0.0
    payments = 0
    last: dt.date | None = None
    for row in rows:
        when = _as_date(row.get("ex_dividend_date"))
        amount = row.get("amount")
        if when is None or amount is None or when < since:
            continue
        try:
            per_share += float(amount)
        except (TypeError, ValueError):
            continue
        payments += 1
        last = when if last is None or when > last else last

    return {
        "amount": round(per_share * quantity, 2),
        "per_share": round(per_share, 4),
        "payments": payments,
        "last": last.isoformat() if last else None,
    }


async def for_position(symbol: str, quantity: float, opened_at: str | None) -> dict:
    """Bloc dividende d'une ligne : perçu depuis l'entrée, et prochain à venir."""
    empty = {
        "accrued": {"amount": None, "per_share": None, "payments": 0, "last": None},
        "next_ex_date": None,
        "next_estimated_amount": None,
    }
    try:
        rows = await obb_source.dividends(symbol)
    except Exception:  # noqa: BLE001
        return empty

    since = _as_date(opened_at)
    result = {"accrued": accrued(rows, since, quantity)}

    upcoming = next_ex_date([r.get("ex_dividend_date") for r in rows])
    result["next_ex_date"] = upcoming.isoformat() if upcoming else None

    # Montant attendu : le dernier détachement connu, faute de mieux. Une
    # annonce officielle serait préférable, mais aucune source gratuite ne la
    # publie pour les valeurs européennes.
    last_amount = None
    for row in sorted(
        rows, key=lambda r: str(r.get("ex_dividend_date") or ""), reverse=True
    ):
        try:
            last_amount = float(row.get("amount"))
            break
        except (TypeError, ValueError):
            continue
    result["next_estimated_amount"] = (
        round(last_amount * quantity, 2) if last_amount is not None else None
    )
    return result
