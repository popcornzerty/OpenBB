"""Lecture du portefeuille Wealthfolio.

Wealthfolio est local-first : ses données vivent dans un SQLite sur la machine.
On l'ouvre en **lecture seule**, jamais en écriture — le terminal observe le
portefeuille, il ne le modifie pas. C'est Wealthfolio qui reste maître de ses
données, et une corruption de sa base ne peut pas venir d'ici.

Le couplage au schéma de Wealthfolio est assumé mais contenu : une seule
requête, et toute erreur remonte comme « portefeuille indisponible » plutôt
que de casser le terminal.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from ..settings import settings

#: Identifiant applicatif de Wealthfolio, qui nomme son dossier de données.
APP_IDENTIFIER = "com.teymz.wealthfolio"

#: Code de place (MIC) -> suffixe de ticker Yahoo.
#:
#: Wealthfolio range le symbole nu (« SAN ») et la place séparément, alors que
#: Yahoo attend un ticker suffixé (« SAN.PA »). Sans cette table, aucune des
#: deux applications ne parle du même titre.
MIC_TO_SUFFIX = {
    "XPAR": ".PA", "XAMS": ".AS", "XBRU": ".BR", "XLIS": ".LS", "XDUB": ".IR",
    "XETR": ".DE", "XFRA": ".F", "XBER": ".BE", "XSTU": ".SG", "XMUN": ".MU",
    "XMIL": ".MI", "MTAA": ".MI", "XMAD": ".MC", "BMEX": ".MC",
    "XCSE": ".CO", "XSTO": ".ST", "XHEL": ".HE", "XICE": ".IC",
    "XOSL": ".OL", "XWBO": ".VI", "XWAR": ".WA", "XPRA": ".PR",
    "XBUD": ".BD", "XATH": ".AT", "XLON": ".L", "XSWX": ".SW", "XVTX": ".SW",
    # Les places américaines n'ont pas de suffixe chez Yahoo.
    "XNAS": "", "XNYS": "", "ARCX": "", "BATS": "",
}


class PortfolioUnavailable(RuntimeError):
    """Wealthfolio n'est pas installé, ou sa base est illisible."""


@dataclass
class Position:
    """Une ligne du portefeuille Wealthfolio."""

    symbol: str
    raw_symbol: str
    name: str
    exchange_mic: str
    currency: str
    quantity: float
    average_cost: float
    cost_basis: float
    account_id: str
    account_name: str
    snapshot_date: str

    def as_dict(self) -> dict:
        return asdict(self)


def database_path() -> Path:
    """Emplacement de la base Wealthfolio.

    ``PEATERM_WEALTHFOLIO_DB`` permet de pointer une autre installation.
    """
    override = os.environ.get("PEATERM_WEALTHFOLIO_DB")
    if override:
        return Path(override)

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_IDENTIFIER / "app.db"

    # macOS et Linux, pour mémoire.
    home = Path.home()
    mac = home / "Library" / "Application Support" / APP_IDENTIFIER / "app.db"
    if mac.exists():
        return mac
    return home / ".local" / "share" / APP_IDENTIFIER / "app.db"


def is_available() -> bool:
    return database_path().exists()


def _connect() -> sqlite3.Connection:
    path = database_path()
    if not path.exists():
        raise PortfolioUnavailable(
            f"Base Wealthfolio introuvable ({path}). "
            "Installez Wealthfolio, ou définissez PEATERM_WEALTHFOLIO_DB."
        )
    # `mode=ro` garantit qu'aucune écriture ne peut partir d'ici, même par
    # erreur de programmation.
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def to_yahoo_symbol(raw_symbol: str, mic: str | None) -> str:
    """Compose le ticker Yahoo à partir du symbole nu et de la place."""
    symbol = (raw_symbol or "").strip().upper()
    if not symbol:
        return ""
    # Un symbole déjà suffixé est laissé tel quel.
    if "." in symbol:
        return symbol
    suffix = MIC_TO_SUFFIX.get((mic or "").strip().upper())
    return f"{symbol}{suffix}" if suffix else symbol


#: Positions du dernier instantané de chaque compte.
#:
#: Un compte peut compter plusieurs instantanés ; seul le plus récent décrit le
#: portefeuille actuel, d'où la sous-requête sur la date maximale.
_QUERY = """
SELECT
    a.name              AS account_name,
    a.id                AS account_id,
    s.snapshot_date     AS snapshot_date,
    p.quantity          AS quantity,
    p.average_cost      AS average_cost,
    p.total_cost_basis  AS cost_basis,
    p.currency          AS currency,
    ast.instrument_symbol       AS raw_symbol,
    ast.instrument_exchange_mic AS mic,
    ast.name                    AS asset_name
FROM snapshot_positions p
JOIN holdings_snapshots s ON s.id = p.snapshot_id
JOIN accounts a           ON a.id = s.account_id
JOIN assets ast           ON ast.id = p.asset_id
WHERE a.is_active = 1
  AND a.is_archived = 0
  AND s.snapshot_date = (
        SELECT MAX(s2.snapshot_date)
        FROM holdings_snapshots s2
        WHERE s2.account_id = s.account_id
  )
ORDER BY a.name, CAST(p.total_cost_basis AS REAL) DESC
"""


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_positions() -> list[Position]:
    """Positions courantes, tous comptes actifs confondus."""
    con = _connect()
    try:
        rows = con.execute(_QUERY).fetchall()
    except sqlite3.Error as exc:
        raise PortfolioUnavailable(
            f"Base Wealthfolio illisible : {exc}. Le schéma a peut-être changé."
        ) from exc
    finally:
        con.close()

    positions: list[Position] = []
    for row in rows:
        raw = row["raw_symbol"] or ""
        symbol = to_yahoo_symbol(raw, row["mic"])
        if not symbol:
            continue
        positions.append(
            Position(
                symbol=symbol,
                raw_symbol=raw,
                name=row["asset_name"] or raw,
                exchange_mic=row["mic"] or "",
                currency=row["currency"] or "EUR",
                quantity=_to_float(row["quantity"]),
                average_cost=_to_float(row["average_cost"]),
                cost_basis=_to_float(row["cost_basis"]),
                account_id=row["account_id"],
                account_name=row["account_name"],
                snapshot_date=str(row["snapshot_date"]),
            )
        )
    return positions


def read_accounts() -> list[dict]:
    """Comptes actifs, avec leur mode de suivi."""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT id, name, currency, account_type, tracking_mode"
            " FROM accounts WHERE is_active = 1 AND is_archived = 0 ORDER BY name"
        ).fetchall()
    except sqlite3.Error as exc:
        raise PortfolioUnavailable(f"Base Wealthfolio illisible : {exc}") from exc
    finally:
        con.close()
    return [dict(row) for row in rows]


#: Le portefeuille change rarement dans la journée ; inutile de rouvrir la base
#: à chaque affichage.
CACHE_TTL = settings.ttl_quote * 5
