"""Construction des séries fondamentales par action, sur grille quotidienne.

Les états financiers sont ponctuels (un point par exercice) alors que le cours
est quotidien. Pour calculer un multiple historique il faut les mettre sur la
même grille : chaque fondamental est propagé jour après jour à partir du
moment où il devient **public**, et non de la date de clôture — sans quoi la
série connaîtrait des comptes avant leur publication, ce qui gonflerait
artificiellement la qualité apparente du modèle.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pandas as pd

from ..providers.obb_source import publication_date

#: Les quatre fondamentaux retenus, dans l'ordre d'affichage.
COMPONENTS = ("earnings", "sales", "book_value", "cash_flow")

COMPONENT_LABELS = {
    "earnings": "Bénéfices",
    "sales": "Ventes",
    "book_value": "Valeur comptable",
    "cash_flow": "Flux de trésorerie",
}

MULTIPLE_LABELS = {
    "earnings": "PER",
    "sales": "P/S",
    "book_value": "P/B",
    "cash_flow": "P/CF",
}


@dataclass
class FundamentalPoint:
    """Un fondamental par action, à une date de publication donnée."""

    available_from: dt.date
    period_ending: dt.date
    values: dict[str, float | None]


def _get(row: dict, *names: str) -> float | None:
    """Premier champ non nul parmi ``names``."""
    for name in names:
        value = row.get(name)
        if value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number == number:  # écarte NaN
                return number
    return None


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


def _index_by_period(rows: list[dict]) -> dict[dt.date, dict]:
    indexed: dict[dt.date, dict] = {}
    for row in rows:
        period = _as_date(row.get("period_ending"))
        if period is not None:
            indexed[period] = row
    return indexed


def build_points(statements: dict[str, list[dict]]) -> list[FundamentalPoint]:
    """Assemble les fondamentaux par action, exercice par exercice.

    Le nombre d'actions retenu est la moyenne pondérée diluée (celle qui sert
    au BPA publié) ; à défaut le nombre d'actions ordinaires du bilan.
    """
    income = _index_by_period(statements.get("income", []))
    balance = _index_by_period(statements.get("balance", []))
    cash = _index_by_period(statements.get("cash", []))

    points: list[FundamentalPoint] = []
    for period in sorted(set(income) | set(balance) | set(cash)):
        inc = income.get(period, {})
        bal = balance.get(period, {})
        cfs = cash.get(period, {})

        shares = _get(
            inc,
            "weighted_average_diluted_shares_outstanding",
            "weighted_average_basic_shares_outstanding",
        ) or _get(bal, "ordinary_shares_number", "share_issued")

        if not shares or shares <= 0:
            continue

        eps = _get(inc, "diluted_earnings_per_share", "basic_earnings_per_share")
        if eps is None:
            net_income = _get(inc, "net_income_attributable_to_common_shareholders", "net_income")
            eps = net_income / shares if net_income is not None else None

        revenue = _get(inc, "total_revenue", "operating_revenue")
        equity = _get(bal, "common_stock_equity", "total_common_equity", "tangible_book_value")
        free_cash_flow = _get(cfs, "free_cash_flow")
        if free_cash_flow is None:
            operating = _get(cfs, "operating_cash_flow")
            capex = _get(cfs, "capital_expenditure")
            if operating is not None and capex is not None:
                # capital_expenditure est déjà négatif dans le tableau de flux.
                free_cash_flow = operating + capex

        points.append(
            FundamentalPoint(
                available_from=publication_date(period),
                period_ending=period,
                values={
                    "earnings": eps,
                    "sales": revenue / shares if revenue is not None else None,
                    "book_value": equity / shares if equity is not None else None,
                    "cash_flow": (
                        free_cash_flow / shares if free_cash_flow is not None else None
                    ),
                },
            )
        )
    return points


def to_daily_frame(
    points: list[FundamentalPoint], index: pd.DatetimeIndex
) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    """Projette les fondamentaux sur la grille quotidienne du cours.

    Propagation en escalier à partir de la **date de publication** : tant que
    les comptes suivants ne sont pas parus, ce sont les derniers connus qui
    s'appliquent. Aucune donnée future n'est ainsi utilisée.

    Reste le début de fenêtre, antérieur à la publication des comptes les plus
    anciens dont on dispose : il serait vide. Plutôt que d'amputer la courbe
    d'un tiers, on y reporte ces plus anciens comptes. C'est le seul endroit du
    calcul où une donnée est utilisée avant sa parution ; la date jusqu'à
    laquelle cela s'applique est remontée au client, qui l'affiche comme telle.

    Renvoie ``(frame, date_de_fin_du_report_amont)``.
    """
    frame = pd.DataFrame(index=index, columns=list(COMPONENTS), dtype="float64")
    if not points:
        return frame, None

    ordered = sorted(points, key=lambda p: p.available_from)
    for point in ordered:
        stamp = pd.Timestamp(point.available_from)
        mask = frame.index >= stamp
        if not mask.any():
            continue
        for component, value in point.values.items():
            if value is not None:
                frame.loc[mask, component] = value

    first_publication = pd.Timestamp(ordered[0].available_from)
    backfilled_until = None
    if len(index) and index[0] < first_publication:
        frame = frame.bfill()
        backfilled_until = min(first_publication, index[-1])

    return frame, backfilled_until
