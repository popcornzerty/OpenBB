"""Univers d'actions européennes et verdict PEA associé.

Le fichier ``data/universe_eu.csv`` est l'univers **validé** : il est produit
par ``scripts/build_universe.py``, qui part du seed d'indices
(``universe_eu_seed.csv``), interroge réellement chaque ticker et ne conserve
que ceux qui répondent. Aucun symbole n'y figure sur la seule foi d'une liste
recopiée.

Un titre hors univers reste accessible : la recherche libre le résout à la
volée et son éligibilité est évaluée de la même manière.
"""

from __future__ import annotations

import asyncio
import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from ..providers import ecb_fx, estimates, obb_source
from ..settings import DATA_DIR
from .dividends import (
    Safety,
    dividend_growth,
    fcf_coverage,
    frequency,
    next_ex_date,
    payout_ratio,
    safety,
)
from .eligibility import Eligibility, assess

UNIVERSE_PATH = DATA_DIR / "universe_eu.csv"
SEED_PATH = DATA_DIR / "universe_eu_seed.csv"

_FIELDS = [
    "symbol",
    "name",
    "index",
    "exchange",
    "currency",
    "country_iso",
    "country_label",
    "sector",
    "industry",
    "market_cap",
    "market_cap_eur",
    "dividend_yield",
    "dividend_cagr",
    "dividend_cagr_window",
    "payout_ratio",
    "fcf_coverage",
    "dividend_safety",
    "dividend_safety_reason",
    "dividend_frequency",
    "next_ex_date",
    "pea_status",
    "pea_reason",
]


@dataclass
class UniverseEntry:
    """Une ligne de l'univers."""

    symbol: str
    name: str
    index: str = ""
    exchange: str = ""
    currency: str = ""
    country_iso: str = ""
    country_label: str = ""
    sector: str = ""
    industry: str = ""
    #: Capitalisation dans la devise de cotation.
    market_cap: float | None = None
    #: Capitalisation ramenée en euros — seule grandeur comparable d'une place
    #: à l'autre, et donc la seule sur laquelle trier ou filtrer.
    market_cap_eur: float | None = None
    #: Rendement du dividende, en fraction (0,047 pour 4,7 %).
    dividend_yield: float | None = None
    #: Croissance annualisée du dividende sur la dernière période continue.
    dividend_cagr: float | None = None
    #: Période retenue, par exemple « 2020–2025 ».
    dividend_cagr_window: str = ""
    payout_ratio: float | None = None
    #: Part du flux de trésorerie libre absorbée par le dividende.
    fcf_coverage: float | None = None
    dividend_safety: str = Safety.UNKNOWN.value
    dividend_safety_reason: str = ""
    dividend_frequency: str = ""
    #: Prochain détachement **estimé** à partir du rythme passé.
    next_ex_date: str = ""
    pea_status: str = Eligibility.UNKNOWN.value
    pea_reason: str = ""

    @property
    def is_pea_eligible(self) -> bool:
        return self.pea_status == Eligibility.ELIGIBLE.value

    def as_dict(self) -> dict:
        return asdict(self)


def _to_float(value) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_or_none(value) -> float | None:
    """Comme ``_to_float``, mais une valeur nulle ou négative vaut absence.

    Utilisé à la relecture du fichier d'univers, pour que les entrées écrites
    avant ce garde-fou soient corrigées au chargement.
    """
    number = _to_float(value)
    return number if number is not None and number > 0 else None


def load_universe(path: Path | None = None) -> list[UniverseEntry]:
    """Charge l'univers validé depuis le disque."""
    target = path or UNIVERSE_PATH
    if not target.exists():
        return []
    entries: list[UniverseEntry] = []
    # ``utf-8-sig`` : un fichier édité sous Windows peut porter un BOM, qui
    # sinon se retrouve collé au premier nom de colonne.
    with target.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            entries.append(
                UniverseEntry(
                    symbol=row.get("symbol", ""),
                    name=row.get("name", ""),
                    index=row.get("index", ""),
                    exchange=row.get("exchange", ""),
                    currency=row.get("currency", ""),
                    country_iso=row.get("country_iso", ""),
                    country_label=row.get("country_label", ""),
                    sector=row.get("sector", ""),
                    industry=row.get("industry", ""),
                    market_cap=_positive_or_none(row.get("market_cap")),
                    market_cap_eur=_positive_or_none(row.get("market_cap_eur")),
                    dividend_yield=_to_float(row.get("dividend_yield")),
                    dividend_cagr=_to_float(row.get("dividend_cagr")),
                    dividend_cagr_window=row.get("dividend_cagr_window", ""),
                    payout_ratio=_to_float(row.get("payout_ratio")),
                    fcf_coverage=_to_float(row.get("fcf_coverage")),
                    dividend_safety=row.get("dividend_safety") or Safety.UNKNOWN.value,
                    dividend_safety_reason=row.get("dividend_safety_reason", ""),
                    dividend_frequency=row.get("dividend_frequency", ""),
                    next_ex_date=row.get("next_ex_date", ""),
                    pea_status=row.get("pea_status", Eligibility.UNKNOWN.value),
                    pea_reason=row.get("pea_reason", ""),
                )
            )
    return entries


def save_universe(entries: list[UniverseEntry], path: Path | None = None) -> Path:
    """Écrit l'univers validé sur le disque."""
    target = path or UNIVERSE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS)
        writer.writeheader()
        for entry in sorted(entries, key=lambda e: (e.index, e.symbol)):
            writer.writerow(entry.as_dict())
    return target


def load_seed(path: Path | None = None) -> list[tuple[str, str, str]]:
    """Charge le seed brut : ``(symbole, nom, indice)``."""
    target = path or SEED_PATH
    rows: list[tuple[str, str, str]] = []
    with target.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("symbol") or "").strip()
            if symbol:
                rows.append(
                    (symbol, (row.get("name") or "").strip(), (row.get("index") or "").strip())
                )
    return rows


async def _dividend_facts(symbol: str) -> dict:
    """Rendement, sûreté et prochaine échéance d'un titre.

    Chaque source est interrogée séparément et son échec toléré : un titre sans
    tableau de flux exploitable doit conserver son rendement, quitte à ce que
    la sûreté reste indéterminée.
    """
    facts: dict = {
        "dividend_yield": None,
        "dividend_cagr": None,
        "dividend_cagr_window": "",
        "payout_ratio": None,
        "fcf_coverage": None,
        "dividend_safety": Safety.UNKNOWN.value,
        "dividend_safety_reason": "",
        "dividend_frequency": "",
        "next_ex_date": "",
    }

    try:
        metrics = await obb_source.metrics(symbol)
        facts["dividend_yield"] = metrics.get("dividend_yield")
    except Exception:  # noqa: BLE001
        metrics = {}

    try:
        statements = await obb_source.statements(symbol, period="annual", limit=1)
        cash = (statements.get("cash") or [{}])[0]
        coverage = fcf_coverage(
            cash.get("free_cash_flow"), cash.get("cash_dividends_paid")
        )
        facts["fcf_coverage"] = coverage
    except Exception:  # noqa: BLE001
        coverage = None

    # Le bénéfice doit être libellé dans la devise des dividendes. Celui des
    # états financiers ne l'est pas toujours — Aker BP verse en couronnes et
    # publie en dollars — d'où le BNPA des douze derniers mois, exprimé en
    # devise de cotation.
    eps = None
    try:
        eps = (await estimates.consensus(symbol)).get("trailing_eps")
    except Exception:  # noqa: BLE001
        eps = None

    # L'historique des détachements sert au taux de distribution comme au
    # rythme : il doit donc être lu avant de rendre le verdict de sûreté.
    rows: list[dict] = []
    try:
        rows = await obb_source.dividends(symbol)
    except Exception:  # noqa: BLE001
        rows = []

    computed = payout_ratio(rows, eps)
    facts["payout_ratio"] = (
        computed if computed is not None else metrics.get("payout_ratio")
    )

    verdict, reason = safety(
        facts["payout_ratio"], facts["fcf_coverage"], facts["dividend_yield"]
    )
    facts["dividend_safety"] = verdict.value
    facts["dividend_safety_reason"] = reason

    if verdict is not Safety.NONE and rows:
        try:
            dates = [row.get("ex_dividend_date") for row in rows]
            facts["dividend_frequency"] = frequency(dates)[0]
            upcoming = next_ex_date(dates)
            facts["next_ex_date"] = upcoming.isoformat() if upcoming else ""
            cagr, window = dividend_growth(rows)
            facts["dividend_cagr"] = cagr
            facts["dividend_cagr_window"] = window
        except Exception:  # noqa: BLE001
            pass

    return facts


async def describe(symbol: str, name_hint: str = "", index: str = "") -> UniverseEntry:
    """Construit une entrée d'univers à partir du profil live d'un titre."""
    profile = await obb_source.profile(symbol)
    status = assess(symbol, profile.get("hq_country"))
    dividend = await _dividend_facts(symbol)
    # Une capitalisation nulle n'existe pas : c'est une donnée manquante que la
    # source habille en nombre. La traiter comme absente évite qu'elle se place
    # en tête d'un tri croissant et qu'elle s'affiche « 0 € ».
    market_cap = _to_float(profile.get("market_cap"))
    if market_cap is not None and market_cap <= 0:
        market_cap = None
    currency = profile.get("currency") or ""
    return UniverseEntry(
        symbol=symbol,
        name=profile.get("name") or name_hint or symbol,
        index=index,
        exchange=profile.get("stock_exchange") or "",
        currency=currency,
        country_iso=status.country_iso or "",
        country_label=status.country_label or "",
        sector=profile.get("sector") or "",
        industry=profile.get("industry_category") or "",
        market_cap=market_cap,
        market_cap_eur=await ecb_fx.to_eur(market_cap, currency),
        **dividend,
        pea_status=status.status.value,
        pea_reason=status.reason,
    )


class UniverseRegistry:
    """Index mémoire de l'univers, chargé une fois au démarrage."""

    def __init__(self) -> None:
        self._entries: list[UniverseEntry] = []
        self._by_symbol: dict[str, UniverseEntry] = {}
        self._lock = asyncio.Lock()

    def load(self) -> None:
        self._entries = load_universe()
        self._by_symbol = {e.symbol.upper(): e for e in self._entries}

    @property
    def entries(self) -> list[UniverseEntry]:
        return self._entries

    @property
    def is_empty(self) -> bool:
        return not self._entries

    def get(self, symbol: str) -> UniverseEntry | None:
        return self._by_symbol.get(symbol.upper())

    async def get_or_describe(self, symbol: str) -> UniverseEntry:
        """Renvoie l'entrée connue, sinon la construit à la volée."""
        known = self.get(symbol)
        if known is not None:
            return known
        async with self._lock:
            known = self.get(symbol)
            if known is not None:
                return known
            entry = await describe(symbol)
            self._by_symbol[symbol.upper()] = entry
            return entry

    def indices(self) -> list[str]:
        return sorted({e.index for e in self._entries if e.index})

    def countries(self) -> list[dict]:
        seen: dict[str, str] = {}
        for entry in self._entries:
            if entry.country_iso:
                seen[entry.country_iso] = entry.country_label
        return [{"iso": k, "label": v} for k, v in sorted(seen.items())]

    def sectors(self) -> list[str]:
        return sorted({e.sector for e in self._entries if e.sector})


registry = UniverseRegistry()
