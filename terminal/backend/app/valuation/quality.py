"""Score de qualité (« note Q ») d'une société.

Ce score alimente la prime ou la décote appliquée à la juste valeur. Il est
**maison** : la note Q de Baggr est propriétaire et n'est pas reproduite ici.
Chaque axe est explicité et remonté au client, pour que l'utilisateur voie ce
qui produit la prime plutôt qu'un chiffre opaque.

Notation par **seuils absolus** et non par percentile face à un univers de
comparaison. C'est un choix délibéré : un classement relatif ferait bouger la
juste valeur d'une société chaque fois que ses pairs bougent, alors que ses
propres comptes n'ont pas changé. Des seuils fixes donnent une courbe
reproductible et interprétable.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .series import _as_date, _get


@dataclass
class QualityAxis:
    """Un axe du score, avec ce qui l'a produit."""

    key: str
    label: str
    score: float
    weight: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 1),
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class QualityScore:
    """Note Q agrégée, dans [0, 100]."""

    score: float
    axes: list[QualityAxis]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 1),
            "axes": [axis.as_dict() for axis in self.axes],
            "method": (
                "Score maison sur seuils absolus (rentabilité, conversion en cash, "
                "solidité, croissance, stabilité). Ce n'est pas la note Q de Baggr."
            ),
        }


def _band(value: float | None, low: float, high: float, invert: bool = False) -> float | None:
    """Projette ``value`` sur [0, 100] entre les bornes ``low`` et ``high``.

    ``invert=True`` pour les critères où « moins, c'est mieux » (endettement).
    """
    if value is None:
        return None
    if high == low:
        return 50.0
    ratio = (value - low) / (high - low)
    ratio = max(0.0, min(1.0, ratio))
    return (1.0 - ratio) * 100.0 if invert else ratio * 100.0


def _mean(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None


def _series(rows: list[dict], *names: str) -> list[float]:
    """Suite chronologique d'un poste, du plus ancien au plus récent."""
    pairs = []
    for row in rows:
        period = _as_date(row.get("period_ending"))
        value = _get(row, *names)
        if period is not None and value is not None:
            pairs.append((period, value))
    pairs.sort(key=lambda p: p[0])
    return [value for _, value in pairs]


def _cagr(values: list[float]) -> float | None:
    """Taux de croissance annuel moyen, si le point de départ est positif."""
    if len(values) < 2 or values[0] <= 0:
        return None
    periods = len(values) - 1
    try:
        return (values[-1] / values[0]) ** (1 / periods) - 1
    except (ValueError, ZeroDivisionError, OverflowError):
        return None


def _relative_dispersion(values: list[float]) -> float | None:
    """Écart-type rapporté à la moyenne, en valeur absolue."""
    usable = [v for v in values if v is not None]
    if len(usable) < 3:
        return None
    average = statistics.fmean(usable)
    if average == 0:
        return None
    return statistics.pstdev(usable) / abs(average)


def compute(statements: dict[str, list[dict]], metrics: dict) -> QualityScore:
    """Calcule la note Q à partir des états financiers et des ratios courants."""
    income = statements.get("income", [])
    balance = statements.get("balance", [])
    cash = statements.get("cash", [])

    revenues = _series(income, "total_revenue", "operating_revenue")
    net_incomes = _series(income, "net_income_attributable_to_common_shareholders", "net_income")
    operating_incomes = _series(income, "operating_income")
    eps_series = _series(income, "diluted_earnings_per_share", "basic_earnings_per_share")
    free_cash_flows = _series(cash, "free_cash_flow")
    equities = _series(balance, "common_stock_equity", "total_common_equity")

    axes: list[QualityAxis] = []

    # --- Rentabilité ------------------------------------------------------
    roe = metrics.get("return_on_equity")
    if roe is None and net_incomes and equities and equities[-1]:
        roe = net_incomes[-1] / equities[-1]
    net_margin = metrics.get("profit_margin")
    if net_margin is None and revenues and net_incomes and revenues[-1]:
        net_margin = net_incomes[-1] / revenues[-1]
    operating_margin = metrics.get("operating_margin")
    if operating_margin is None and revenues and operating_incomes and revenues[-1]:
        operating_margin = operating_incomes[-1] / revenues[-1]

    profitability = _mean(
        [
            _band(roe, 0.02, 0.25),
            _band(net_margin, 0.0, 0.20),
            _band(operating_margin, 0.0, 0.25),
        ]
    )
    axes.append(
        QualityAxis(
            "profitability",
            "Rentabilité",
            profitability if profitability is not None else 50.0,
            0.25,
            f"ROE {_pct(roe)}, marge nette {_pct(net_margin)}, "
            f"marge opérationnelle {_pct(operating_margin)}",
        )
    )

    # --- Conversion en cash ----------------------------------------------
    conversion = None
    if free_cash_flows and net_incomes:
        recent_fcf = free_cash_flows[-min(3, len(free_cash_flows)):]
        recent_ni = net_incomes[-min(3, len(net_incomes)):]
        total_ni = sum(recent_ni)
        if total_ni > 0:
            conversion = sum(recent_fcf) / total_ni
    axes.append(
        QualityAxis(
            "cash_conversion",
            "Conversion en cash",
            _band(conversion, 0.3, 1.1) if conversion is not None else 50.0,
            0.20,
            f"Flux de trésorerie libre / résultat net : {_pct(conversion)}",
        )
    )

    # --- Solidité financière ---------------------------------------------
    # ``obb_source.metrics`` a déjà ramené ce ratio en fraction ; le garde-fou
    # reste au cas où des métriques brutes seraient passées directement.
    debt_to_equity = metrics.get("debt_to_equity")
    if debt_to_equity is not None and debt_to_equity > 5:
        debt_to_equity = debt_to_equity / 100.0
    current_ratio = metrics.get("current_ratio")
    solidity = _mean(
        [
            _band(debt_to_equity, 0.2, 2.0, invert=True),
            _band(current_ratio, 0.8, 2.0),
        ]
    )
    axes.append(
        QualityAxis(
            "solidity",
            "Solidité financière",
            solidity if solidity is not None else 50.0,
            0.20,
            f"Dette/fonds propres {_num(debt_to_equity)}, "
            f"ratio de liquidité {_num(current_ratio)}",
        )
    )

    # --- Croissance -------------------------------------------------------
    revenue_cagr = _cagr(revenues)
    eps_cagr = _cagr(eps_series)
    growth = _mean([_band(revenue_cagr, -0.02, 0.15), _band(eps_cagr, -0.02, 0.20)])
    axes.append(
        QualityAxis(
            "growth",
            "Croissance",
            growth if growth is not None else 50.0,
            0.20,
            f"TCAM du chiffre d'affaires {_pct(revenue_cagr)}, TCAM du BPA {_pct(eps_cagr)}",
        )
    )

    # --- Stabilité --------------------------------------------------------
    margins = [
        net_incomes[i] / revenues[i]
        for i in range(min(len(net_incomes), len(revenues)))
        if revenues[i]
    ]
    margin_dispersion = _relative_dispersion(margins)
    revenue_dispersion = _relative_dispersion(revenues)
    stability = _mean(
        [
            _band(margin_dispersion, 0.05, 0.60, invert=True),
            _band(revenue_dispersion, 0.03, 0.40, invert=True),
        ]
    )
    axes.append(
        QualityAxis(
            "stability",
            "Stabilité",
            stability if stability is not None else 50.0,
            0.15,
            f"Dispersion des marges {_pct(margin_dispersion)}, "
            f"dispersion du chiffre d'affaires {_pct(revenue_dispersion)}",
        )
    )

    total_weight = sum(axis.weight for axis in axes)
    score = sum(axis.score * axis.weight for axis in axes) / total_weight
    return QualityScore(score=score, axes=axes)


def _pct(value: float | None) -> str:
    return "n.d." if value is None else f"{value * 100:.1f} %"


def _num(value: float | None) -> str:
    return "n.d." if value is None else f"{value:.2f}"
