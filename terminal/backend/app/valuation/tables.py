"""Tableaux de compte de résultat et de valorisation, par exercice.

Deux tableaux à colonnes communes — les exercices — sur le modèle des fiches
de Zonebourse : l'historique publié, puis les exercices estimés par le
consensus.

Deux partis pris méritent d'être explicites.

**Les multiples historiques sont calculés au cours de clôture d'exercice.**
Un PER 2023 rapporté au cours d'aujourd'hui ne voudrait rien dire : il
mélangerait le bénéfice d'alors et la valorisation d'aujourd'hui. Les
colonnes estimées, elles, utilisent le cours actuel — c'est ce qu'on cherche
à savoir : ce que l'on paie aujourd'hui pour les bénéfices à venir.

**Une case vide reste vide.** Le consensus gratuit ne couvre que le chiffre
d'affaires et le bénéfice par action. L'EBITDA, les capitaux propres ou le
dividende à venir ne sont pas estimés : les inventer par extrapolation
donnerait un tableau plein et faux.
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any

import pandas as pd

#: Au-delà, un multiple ne renseigne plus sur rien : un PER de 900 signale un
#: exercice exceptionnel, pas une valorisation. On l'écarte plutôt que de
#: laisser un nombre absurde structurer la lecture du tableau.
MAX_MULTIPLE = 300.0


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first(row: dict, *keys: str) -> float | None:
    """Première valeur exploitable parmi plusieurs intitulés possibles."""
    for key in keys:
        value = _number(row.get(key))
        if value is not None:
            return value
    return None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Multiple, écarté s'il n'est pas interprétable.

    Un dénominateur négatif ou nul — un exercice à perte, un EBITDA négatif —
    ne produit pas un multiple « négatif » lisible : il n'en produit aucun.
    """
    if numerator is None or denominator is None or denominator <= 0:
        return None
    result = numerator / denominator
    if not math.isfinite(result) or result <= 0 or result > MAX_MULTIPLE:
        return None
    return result


def _margin(numerator: float | None, revenue: float | None) -> float | None:
    """Marge, négative comprise : une perte se lit, contrairement à un PER."""
    if numerator is None or not revenue:
        return None
    result = numerator / revenue
    return result if math.isfinite(result) else None


def _year_of(value: Any) -> int | None:
    try:
        return dt.date.fromisoformat(str(value)[:10]).year
    except (ValueError, TypeError):
        return None


def _close_series(history: list[dict]) -> pd.Series:
    """Série des clôtures, indexée par date et triée."""
    rows = [
        (str(row.get("date"))[:10], _number(row.get("close")))
        for row in history
        if row.get("date") is not None and _number(row.get("close")) is not None
    ]
    if not rows:
        return pd.Series(dtype=float)
    frame = pd.Series(
        [value for _, value in rows],
        index=pd.to_datetime([day for day, _ in rows]),
    )
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def _price_at(closes: pd.Series, when: str | None) -> float | None:
    """Dernier cours connu à cette date.

    Une clôture d'exercice tombe souvent un jour férié ; ``asof`` remonte au
    dernier jour coté, ce qui est le comportement voulu.
    """
    if closes.empty or not when:
        return None
    try:
        stamp = pd.Timestamp(str(when)[:10])
    except ValueError:
        return None
    if stamp < closes.index[0]:
        # L'exercice précède l'historique disponible : pas de multiple, plutôt
        # qu'un multiple calculé sur le plus vieux cours connu.
        return None
    value = closes.asof(stamp)
    return _number(value)


class Column:
    """Un exercice, publié ou estimé."""

    def __init__(
        self,
        year: int,
        *,
        estimate: bool,
        period_ending: str | None = None,
        price: float | None = None,
        analysts: int | None = None,
        thin: bool = False,
    ) -> None:
        self.year = year
        self.estimate = estimate
        self.period_ending = period_ending
        self.price = price
        self.analysts = analysts
        self.thin = thin

    def as_dict(self) -> dict:
        return {
            "label": f"{self.year}{'e' if self.estimate else ''}",
            "year": self.year,
            "estimate": self.estimate,
            "period_ending": self.period_ending,
            "price": round(self.price, 4) if self.price is not None else None,
            "analysts": self.analysts,
            "thin": self.thin,
        }


def _row(key: str, label: str, unit: str, values: list, note: str = "") -> dict:
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "values": [
            None if v is None else round(v, 6 if unit in ("percent", "ratio") else 4)
            for v in values
        ],
        "note": note,
    }


def build(
    statements: dict[str, list[dict]],
    history: list[dict],
    consensus: dict,
    *,
    last_price: float | None = None,
) -> dict:
    """Assemble les deux tableaux.

    ``statements`` porte les trois états financiers du plus récent au plus
    ancien, ``consensus`` la sortie du fournisseur d'estimations.
    """
    income = list(statements.get("income") or [])
    balance = {(_year_of(r.get("period_ending"))): r for r in statements.get("balance") or []}
    cash = {(_year_of(r.get("period_ending"))): r for r in statements.get("cash") or []}
    closes = _close_series(history)

    if not income:
        return {"columns": [], "income_rows": [], "valuation_rows": [], "notes": []}

    # Du plus ancien au plus récent : un tableau se lit dans le sens du temps.
    income = sorted(income, key=lambda r: str(r.get("period_ending") or ""))

    columns: list[Column] = []
    published: list[dict] = []
    for row in income:
        year = _year_of(row.get("period_ending"))
        if year is None:
            continue
        # Yahoo renvoie un cinquième exercice réduit à sa date de clôture,
        # sans aucun compte. Une colonne entièrement vide n'apporte rien et
        # laisserait croire à une donnée manquante ponctuelle.
        if not any(
            _first(row, key) is not None
            for key in (
                "total_revenue",
                "operating_revenue",
                "net_income",
                "diluted_earnings_per_share",
            )
        ):
            continue
        columns.append(
            Column(
                year,
                estimate=False,
                period_ending=str(row.get("period_ending"))[:10],
                price=_price_at(closes, row.get("period_ending")),
            )
        )
        published.append(row)

    last_published_year = columns[-1].year if columns else None

    # ---- colonnes estimées -------------------------------------------------
    notes: list[str] = []
    periods = list(consensus.get("periods") or [])
    estimate_data: dict[int, dict] = {}
    if periods and last_published_year is not None:
        # « 0y » désigne le premier exercice non publié. L'ancrage se fait sur
        # la clôture d'exercice annoncée par la source, et non sur le bénéfice :
        # le consensus raisonne en résultat **ajusté** quand les comptes
        # publient un résultat IFRS, et les deux peuvent légitimement s'écarter
        # de beaucoup sans que l'année soit fausse pour autant.
        anchor = last_published_year + 1
        source_year = _year_of(consensus.get("fiscal_year_end"))
        if source_year is not None and abs(source_year - last_published_year) <= 1:
            anchor = source_year + 1
        elif source_year is not None:
            notes.append(
                "Le dernier exercice connu du consensus "
                f"({source_year}) ne correspond pas aux comptes publiés "
                f"({last_published_year}) : les colonnes estimées sont masquées."
            )
            periods = []

        # Écart de base comptable : signalé, pas éliminatoire.
        reported_eps = _first(
            published[-1], "diluted_earnings_per_share", "basic_earnings_per_share"
        )
        year_ago = _number(periods[0].get("year_ago_eps")) if periods else None
        if (
            reported_eps is not None
            and year_ago is not None
            and reported_eps > 0
            and abs(year_ago - reported_eps) / abs(reported_eps) > 0.15
        ):
            notes.append(
                "Le bénéfice de référence du consensus "
                f"({year_ago:,.2f}) s'écarte du bénéfice publié "
                f"({reported_eps:,.2f}) : les analystes raisonnent en résultat "
                "ajusté. Les PER estimés ne se comparent donc pas directement "
                "aux PER historiques de ce tableau."
            )

        for period in periods:
            year = anchor + int(period.get("offset") or 0)
            estimate_data[year] = period
            columns.append(
                Column(
                    year,
                    estimate=True,
                    price=last_price,
                    analysts=period.get("analysts"),
                    thin=bool(period.get("thin")),
                )
            )

    years = [column.year for column in columns]
    by_year = {_year_of(r.get("period_ending")): r for r in published}

    # ---- compte de résultat ------------------------------------------------
    revenue, ebitda, ebit, net_income, eps, shares = [], [], [], [], [], []
    dividend_ps, fcf, net_debt, equity = [], [], [], []

    for year in years:
        estimated = estimate_data.get(year)
        row = by_year.get(year)

        if estimated is not None:
            revenue.append(_number(estimated.get("revenue")))
            eps.append(_number(estimated.get("eps")))
            # Le consensus gratuit s'arrête là ; le reste demeure inconnu.
            ebitda.append(None)
            ebit.append(None)
            shares.append(None)
            dividend_ps.append(None)
            fcf.append(None)
            net_debt.append(None)
            equity.append(None)
            # Le résultat net estimé se déduit du BNPA et du nombre de titres
            # le plus récent : c'est une reconstitution, signalée comme telle.
            latest_shares = next(
                (s for s in reversed(shares[:-1]) if s), None
            ) or _first(
                published[-1],
                "weighted_average_diluted_shares_outstanding",
                "weighted_average_basic_shares_outstanding",
            )
            eps_value = _number(estimated.get("eps"))
            net_income.append(
                eps_value * latest_shares
                if eps_value is not None and latest_shares
                else None
            )
            continue

        if row is None:
            for bucket in (
                revenue, ebitda, ebit, net_income, eps, shares,
                dividend_ps, fcf, net_debt, equity,
            ):
                bucket.append(None)
            continue

        balance_row = balance.get(year) or {}
        cash_row = cash.get(year) or {}

        revenue.append(_first(row, "total_revenue", "operating_revenue"))
        ebitda.append(_first(row, "ebitda", "normalized_ebitda"))
        ebit.append(_first(row, "ebit", "operating_income", "total_operating_income_as_reported"))
        net_income.append(
            _first(row, "net_income", "net_income_attributable_to_common_shareholders")
        )
        eps.append(_first(row, "diluted_earnings_per_share", "basic_earnings_per_share"))
        count = _first(
            balance_row, "ordinary_shares_number", "share_issued"
        ) or _first(
            row,
            "weighted_average_diluted_shares_outstanding",
            "weighted_average_basic_shares_outstanding",
        )
        shares.append(count)

        paid = _first(cash_row, "cash_dividends_paid")
        dividend_ps.append(abs(paid) / count if paid and count else None)
        fcf.append(_first(cash_row, "free_cash_flow"))

        debt = _first(balance_row, "net_debt")
        if debt is None:
            total_debt = _first(balance_row, "total_debt")
            treasury = _first(
                balance_row,
                "cash_cash_equivalents_and_short_term_investments",
                "cash_and_cash_equivalents",
            )
            debt = total_debt - treasury if total_debt is not None and treasury is not None else None
        net_debt.append(debt)
        equity.append(_first(balance_row, "common_stock_equity", "total_common_equity"))

    def growth(values: list[float | None]) -> list[float | None]:
        result: list[float | None] = [None]
        for previous, current in zip(values, values[1:]):
            result.append(
                (current - previous) / abs(previous)
                if previous and current is not None and previous != 0
                else None
            )
        return result

    income_rows = [
        _row("revenue", "Chiffre d'affaires", "currency", revenue),
        _row("revenue_growth", "Croissance du CA", "percent", growth(revenue)),
        _row("ebitda", "EBITDA", "currency", ebitda),
        _row("ebitda_margin", "Marge d'EBITDA", "percent",
             [_margin(a, b) for a, b in zip(ebitda, revenue)]),
        _row("ebit", "Résultat d'exploitation", "currency", ebit),
        _row("ebit_margin", "Marge d'exploitation", "percent",
             [_margin(a, b) for a, b in zip(ebit, revenue)]),
        _row("net_income", "Résultat net", "currency", net_income,
             "Estimé : reconstitué du BNPA consensus et du nombre de titres le plus récent."),
        _row("net_margin", "Marge nette", "percent",
             [_margin(a, b) for a, b in zip(net_income, revenue)]),
        _row("eps", "BNPA dilué", "per_share", eps),
        _row("eps_growth", "Croissance du BNPA", "percent", growth(eps)),
        _row("dividend_ps", "Dividende versé par action", "per_share", dividend_ps,
             "Décaissements de l'exercice rapportés au nombre de titres, "
             "et non le dividende annoncé au titre de l'exercice."),
        _row("free_cash_flow", "Flux de trésorerie disponible", "currency", fcf),
        _row("net_debt", "Dette nette", "currency", net_debt,
             "Négative lorsque la trésorerie excède la dette."),
        _row("shares", "Nombre de titres", "count", shares),
    ]

    # ---- valorisation ------------------------------------------------------
    market_cap, enterprise_value = [], []
    last_known_debt = next((d for d in reversed(net_debt) if d is not None), None)
    used_stale_debt = False

    for index, column in enumerate(columns):
        price = column.price
        count = shares[index]
        if count is None and column.estimate:
            # Le nombre de titres n'est pas estimé : on prolonge le dernier
            # connu, ce qui suppose l'absence de dilution ou de rachat.
            count = next((s for s in reversed(shares[: index + 1]) if s), None)
        cap = price * count if price is not None and count else None
        market_cap.append(cap)

        debt = net_debt[index]
        if debt is None and column.estimate and last_known_debt is not None:
            debt = last_known_debt
            used_stale_debt = True
        enterprise_value.append(cap + debt if cap is not None and debt is not None else None)

    if used_stale_debt:
        notes.append(
            "La valeur d'entreprise estimée retient la dernière dette nette publiée : "
            "aucune source gratuite n'estime l'endettement à venir."
        )

    per = [
        _ratio(column.price, eps[index])
        for index, column in enumerate(columns)
    ]

    valuation_rows = [
        _row("market_cap", "Capitalisation", "currency", market_cap,
             "Historique : cours de clôture d'exercice. Estimé : cours actuel."),
        _row("enterprise_value", "Valeur d'entreprise", "currency", enterprise_value),
        _row("per", "PER", "ratio", per),
        _row("price_to_sales", "Capitalisation / CA", "ratio",
             [_ratio(a, b) for a, b in zip(market_cap, revenue)]),
        _row("ev_to_sales", "VE / CA", "ratio",
             [_ratio(a, b) for a, b in zip(enterprise_value, revenue)]),
        _row("ev_to_ebitda", "VE / EBITDA", "ratio",
             [_ratio(a, b) for a, b in zip(enterprise_value, ebitda)]),
        _row("ev_to_ebit", "VE / Résultat d'exploitation", "ratio",
             [_ratio(a, b) for a, b in zip(enterprise_value, ebit)]),
        _row("price_to_book", "Capitalisation / Capitaux propres", "ratio",
             [_ratio(a, b) for a, b in zip(market_cap, equity)]),
        _row("dividend_yield", "Rendement", "percent",
             [
                 (d / column.price) if d and column.price else None
                 for d, column in zip(dividend_ps, columns)
             ]),
        _row("fcf_yield", "Rendement du flux disponible", "percent",
             [
                 (f / c) if f is not None and c else None
                 for f, c in zip(fcf, market_cap)
             ]),
    ]

    if any(column.thin for column in columns):
        notes.append(
            "Consensus établi sur moins de trois bureaux d'analyse pour au moins "
            "un exercice : à lire comme un ordre de grandeur."
        )

    return {
        "columns": [column.as_dict() for column in columns],
        "income_rows": income_rows,
        "valuation_rows": valuation_rows,
        "notes": notes,
        "price_target": consensus.get("price_target") or {},
    }


__all__ = ["build", "MAX_MULTIPLE"]
