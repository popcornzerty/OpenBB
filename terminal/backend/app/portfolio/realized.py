"""Cessions et plus-values réalisées.

Vendre une ligne ne doit pas l'effacer de l'histoire du portefeuille : la
plus-value encaissée et les dividendes touchés pendant la détention restent
des résultats acquis. Sans cette trace, un portefeuille bien géré verrait sa
performance fondre à chaque arbitrage réussi.

Une suppression de ligne reste possible par ailleurs, pour corriger une saisie
erronée — c'est une opération différente, qui n'enregistre rien ici.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import asdict, dataclass, field
from threading import Lock

from ..settings import settings

_lock = Lock()


@dataclass
class Sale:
    """Une cession, totale ou partielle."""

    symbol: str
    quantity: float
    average_cost: float
    sale_price: float
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    currency: str = "EUR"
    #: Date d'entrée de la position vendue, reprise telle quelle.
    opened_at: str = ""
    closed_at: str = ""
    label: str = ""
    #: Dividendes encaissés sur les titres vendus pendant la détention,
    #: figés au moment de la vente : la position disparue, ils ne seraient
    #: plus recalculables.
    dividends: float = 0.0
    #: Frais de courtage et taxes acquittés sur l'opération. Ils viennent en
    #: déduction de la plus-value : ce qui rentre sur le compte, c'est le
    #: produit net, pas le produit brut.
    fees: float = 0.0
    #: Motif de l'arbitrage, conservé pour être relu plus tard.
    note: str = ""

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_cost

    @property
    def proceeds(self) -> float:
        """Produit brut, avant frais."""
        return self.quantity * self.sale_price

    @property
    def net_proceeds(self) -> float:
        """Ce qui rentre effectivement sur le compte."""
        return self.proceeds - self.fees

    @property
    def gain(self) -> float:
        return self.net_proceeds - self.cost_basis

    @property
    def gain_percent(self) -> float | None:
        return self.gain / self.cost_basis if self.cost_basis else None

    @property
    def holding_days(self) -> int | None:
        """Durée de détention, quand les deux dates sont connues."""
        try:
            opened = dt.date.fromisoformat(self.opened_at[:10])
            closed = dt.date.fromisoformat(self.closed_at[:10])
        except (ValueError, TypeError):
            return None
        return (closed - opened).days

    def as_dict(self) -> dict:
        return {
            **asdict(self),
            "cost_basis": round(self.cost_basis, 2),
            "proceeds": round(self.proceeds, 2),
            "net_proceeds": round(self.net_proceeds, 2),
            "gain": round(self.gain, 2),
            "gain_percent": (
                round(self.gain_percent, 4) if self.gain_percent is not None else None
            ),
            "holding_days": self.holding_days,
            # Rendement total de l'opération : la plus-value seule ignore ce
            # qu'a rapporté la détention.
            "total_return": round(self.gain + self.dividends, 2),
        }


def _path():
    return settings.state_dir / "realized.json"


def load() -> list[Sale]:
    """Charge les cessions, de la plus récente à la plus ancienne."""
    path = _path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    sales: list[Sale] = []
    for item in raw.get("sales", []):
        try:
            sales.append(
                Sale(
                    id=str(item.get("id") or uuid.uuid4().hex[:12]),
                    symbol=str(item["symbol"]).upper(),
                    quantity=float(item["quantity"]),
                    average_cost=float(item.get("average_cost") or 0),
                    sale_price=float(item.get("sale_price") or 0),
                    currency=item.get("currency") or "EUR",
                    opened_at=item.get("opened_at") or "",
                    closed_at=item.get("closed_at") or "",
                    label=item.get("label") or "",
                    dividends=float(item.get("dividends") or 0),
                    fees=float(item.get("fees") or 0),
                    note=item.get("note") or "",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    sales.sort(key=lambda s: s.closed_at, reverse=True)
    return sales


def save(sales: list[Sale]) -> list[Sale]:
    ordered = sorted(sales, key=lambda s: s.closed_at, reverse=True)
    _path().write_text(
        json.dumps(
            {
                "sales": [asdict(s) for s in ordered],
                "updated_at": dt.datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ordered


def add(sale: Sale) -> list[Sale]:
    with _lock:
        sales = load()
        sales.append(sale)
        return save(sales)


def get(sale_id: str) -> Sale | None:
    return next((s for s in load() if s.id == sale_id), None)


#: Champs modifiables après coup.
#:
#: La quantité en est absente à dessein : les titres ont été retirés du
#: portefeuille au moment de la vente, et la changer ici laisserait les deux
#: registres en désaccord sans que rien ne le signale. Corriger une quantité
#: passe donc par une annulation — qui remet les titres — puis une nouvelle
#: saisie. Les dividendes non plus : ils ont été figés sur la quantité vendue.
EDITABLE = ("sale_price", "fees", "closed_at", "note", "average_cost", "opened_at")


def update(sale_id: str, changes: dict) -> Sale | None:
    """Corrige une cession déjà enregistrée.

    Un relevé de courtier arrive après coup, avec le prix exact et les frais
    réels : pouvoir les reprendre évite d'annuler puis de ressaisir, opération
    qui remet les titres en portefeuille le temps de la manœuvre.
    """
    with _lock:
        sales = load()
        target = next((s for s in sales if s.id == sale_id), None)
        if target is None:
            return None
        for field_name in EDITABLE:
            if field_name in changes and changes[field_name] is not None:
                setattr(target, field_name, changes[field_name])
        save(sales)
        return target


def remove(sale_id: str) -> list[Sale]:
    with _lock:
        sales = [s for s in load() if s.id != sale_id]
        return save(sales)


def totals(sales: list[Sale]) -> dict:
    """Cumuls sur l'ensemble des cessions.

    Le pourcentage rapporte le gain au capital effectivement engagé sur les
    lignes vendues, pas au portefeuille : c'est le rendement des opérations
    closes, pas celui du portefeuille.
    """
    cost = sum(s.cost_basis for s in sales)
    gain = sum(s.gain for s in sales)
    dividends = sum(s.dividends for s in sales)
    fees = sum(s.fees for s in sales)
    winners = [s for s in sales if s.gain > 0]
    return {
        "count": len(sales),
        "cost_basis": round(cost, 2),
        "proceeds": round(sum(s.proceeds for s in sales), 2),
        "net_proceeds": round(sum(s.net_proceeds for s in sales), 2),
        "fees": round(fees, 2),
        "gain": round(gain, 2),
        "gain_percent": round(gain / cost, 4) if cost else None,
        "dividends": round(dividends, 2),
        "total_return": round(gain + dividends, 2),
        "win_rate": round(len(winners) / len(sales), 4) if sales else None,
    }
