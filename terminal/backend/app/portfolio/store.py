"""Positions du portefeuille, tenues par le terminal.

Le terminal est désormais propriétaire des positions : elles sont saisies,
importées ou modifiées ici, et stockées en clair dans un fichier JSON du
dossier d'état. Wealthfolio n'est plus qu'une source d'import initial.

Le format est volontairement lisible et éditable à la main : il s'agit de vos
données, elles ne doivent pas être prisonnières de l'application.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from dataclasses import asdict, dataclass, field
from threading import Lock

from ..settings import settings

_lock = Lock()

#: Nombre écrit avec des virgules de milliers, sans partie décimale.
_THOUSANDS_RE = re.compile(r"^-?\d{1,3}(,\d{3})+$")

#: Colonnes acceptées à l'import, par nom de champ interne.
#:
#: Les intitulés varient d'un courtier à l'autre ; on accepte les plus
#: courants plutôt que d'imposer un gabarit unique.
CSV_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "symbole", "ticker", "code", "isin"),
    "quantity": ("quantity", "quantite", "quantité", "qty", "nombre", "parts"),
    "average_cost": (
        "average_cost", "buyingprice", "prix_de_revient", "pru", "cout_moyen",
        "coût_moyen", "prix_achat", "unitprice",
    ),
    "currency": ("currency", "devise"),
    "opened_at": ("opened_at", "date", "date_achat", "date_entree", "date_entrée"),
    "label": ("label", "name", "nom", "libelle", "libellé"),
}


@dataclass
class Position:
    """Une ligne du portefeuille."""

    symbol: str
    quantity: float
    average_cost: float
    currency: str = "EUR"
    #: Date d'entrée en position. Elle décide des dividendes comptabilisés :
    #: seuls ceux détachés après cette date ont été effectivement perçus.
    opened_at: str = ""
    label: str = ""

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_cost

    def as_dict(self) -> dict:
        return {**asdict(self), "cost_basis": round(self.cost_basis, 2)}


@dataclass
class Portfolio:
    """L'ensemble des positions, plus la date de dernière modification."""

    positions: list[Position] = field(default_factory=list)
    updated_at: str = ""

    def as_dict(self) -> dict:
        return {
            "positions": [p.as_dict() for p in self.positions],
            "updated_at": self.updated_at,
            "count": len(self.positions),
        }


def _path():
    return settings.state_dir / "positions.json"


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def load() -> Portfolio:
    """Charge le portefeuille depuis le disque."""
    path = _path()
    if not path.exists():
        return Portfolio()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un fichier corrompu ne doit pas empêcher le terminal de démarrer ;
        # on repart d'un portefeuille vide plutôt que de planter.
        return Portfolio()

    positions = []
    for item in raw.get("positions", []):
        try:
            positions.append(
                Position(
                    symbol=str(item["symbol"]).upper(),
                    quantity=float(item["quantity"]),
                    average_cost=float(item.get("average_cost") or 0),
                    currency=item.get("currency") or "EUR",
                    opened_at=item.get("opened_at") or "",
                    label=item.get("label") or "",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return Portfolio(positions=positions, updated_at=raw.get("updated_at", ""))


def save(portfolio: Portfolio) -> Portfolio:
    """Écrit le portefeuille sur le disque."""
    portfolio.updated_at = _now()
    _path().write_text(
        json.dumps(
            {
                "positions": [asdict(p) for p in portfolio.positions],
                "updated_at": portfolio.updated_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return portfolio


def upsert(position: Position) -> Portfolio:
    """Ajoute une position, ou remplace celle qui porte le même symbole."""
    with _lock:
        portfolio = load()
        symbol = position.symbol.upper()
        position.symbol = symbol
        portfolio.positions = [p for p in portfolio.positions if p.symbol != symbol]
        portfolio.positions.append(position)
        portfolio.positions.sort(key=lambda p: -p.cost_basis)
        return save(portfolio)


def remove(symbol: str) -> Portfolio:
    """Supprime une position."""
    with _lock:
        portfolio = load()
        target = symbol.upper()
        portfolio.positions = [p for p in portfolio.positions if p.symbol != target]
        return save(portfolio)


def replace_all(positions: list[Position]) -> Portfolio:
    """Remplace l'intégralité du portefeuille."""
    with _lock:
        portfolio = Portfolio(positions=sorted(positions, key=lambda p: -p.cost_basis))
        return save(portfolio)


def _normalize_header(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_").lstrip("﻿")


def _to_number(raw: str | None) -> float | None:
    """Lit un nombre écrit à la française comme à l'anglaise.

    Les exports de courtiers français écrivent « 13 660,00 » : espaces de
    milliers, virgule décimale, parfois entre guillemets.
    """
    if raw is None:
        return None
    text = str(raw).strip().replace(" ", "").replace("\xa0", "").replace(" ", "")
    if not text:
        return None
    # « 1,500 » vaut 1500 en convention anglaise et 1,5 en française. On
    # tranche sur la forme : des groupes de exactement trois chiffres après
    # chaque virgule signent un séparateur de milliers, car une écriture
    # française donnerait « 1,5 » et non « 1,500 ».
    if _THOUSANDS_RE.match(text):
        text = text.replace(",", "")
    elif "," in text and ("." not in text or text.rindex(",") > text.rindex(".")):
        # Virgule décimale ; le point, s'il existe, séparait les milliers.
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def parse_csv(content: str) -> tuple[list[Position], list[str]]:
    """Lit un CSV de positions et renvoie ``(positions, avertissements)``.

    Le séparateur est détecté, les intitulés de colonnes reconnus parmi les
    variantes courantes. Une ligne inexploitable est signalée plutôt
    qu'ignorée en silence : mieux vaut savoir ce qui n'est pas passé.
    """
    warnings: list[str] = []
    text = content.lstrip("﻿")
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        return [], ["Fichier vide ou illisible."]

    headers = {_normalize_header(h): h for h in reader.fieldnames if h}
    mapping: dict[str, str] = {}
    for field_name, aliases in CSV_ALIASES.items():
        for alias in aliases:
            if alias in headers:
                mapping[field_name] = headers[alias]
                break

    missing = [f for f in ("symbol", "quantity") if f not in mapping]
    if missing:
        return [], [
            "Colonnes obligatoires introuvables : "
            + ", ".join(missing)
            + f". Colonnes lues : {', '.join(reader.fieldnames)}."
        ]

    positions: list[Position] = []
    for number, row in enumerate(reader, start=2):
        symbol = (row.get(mapping["symbol"]) or "").strip().upper()
        quantity = _to_number(row.get(mapping["quantity"]))
        if not symbol or quantity is None:
            warnings.append(f"Ligne {number} ignorée : symbole ou quantité manquant.")
            continue
        positions.append(
            Position(
                symbol=symbol,
                quantity=quantity,
                average_cost=_to_number(row.get(mapping.get("average_cost", ""))) or 0.0,
                currency=(row.get(mapping.get("currency", "")) or "EUR").strip() or "EUR",
                opened_at=(row.get(mapping.get("opened_at", "")) or "").strip()[:10],
                label=(row.get(mapping.get("label", "")) or "").strip(),
            )
        )

    if not positions:
        warnings.append("Aucune ligne exploitable dans ce fichier.")
    return positions, warnings
