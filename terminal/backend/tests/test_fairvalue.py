"""Tests du moteur de juste valeur, sur données construites.

Aucun appel réseau : les séries sont fabriquées pour que le résultat attendu
soit calculable à la main.
"""

import datetime as dt

import pytest

from app.settings import settings
from app.valuation import fairvalue
from app.valuation.quality import QualityScore
from app.valuation.series import FundamentalPoint, build_points, to_daily_frame

import pandas as pd


def _history(days: int = 1300, price: float = 100.0) -> list[dict]:
    """Historique quotidien à cours constant, terminant aujourd'hui."""
    end = dt.date.today()
    return [
        {"date": (end - dt.timedelta(days=days - i)).isoformat(), "close": price}
        for i in range(days)
    ]


def _points(years: int = 5, **values) -> list[FundamentalPoint]:
    """Fondamentaux annuels constants, publiés dans le passé."""
    end = dt.date.today()
    out = []
    for i in range(years):
        period = dt.date(end.year - years + i, 12, 31)
        out.append(
            FundamentalPoint(
                available_from=period - dt.timedelta(days=400),
                period_ending=period,
                values={
                    "earnings": values.get("earnings", 5.0),
                    "sales": values.get("sales", 50.0),
                    "book_value": values.get("book_value", 25.0),
                    "cash_flow": values.get("cash_flow", 4.0),
                },
            )
        )
    return out


class TestCalculDeBase:
    def test_multiple_median_applique_au_fondamental(self):
        """Cours et fondamentaux constants : la juste valeur égale le cours."""
        result = fairvalue.compute(_history(), _points())
        assert result["fair_value"] == pytest.approx(100.0, rel=1e-3)
        assert result["gap"] == pytest.approx(0.0, abs=1e-3)
        assert result["verdict"] == "correctement valorisé"

    def test_les_quatre_composantes_sont_retenues(self):
        result = fairvalue.compute(_history(), _points())
        assert {c["key"] for c in result["components"]} == {
            "earnings", "sales", "book_value", "cash_flow"
        }

    def test_les_poids_somment_a_un(self):
        result = fairvalue.compute(_history(), _points())
        assert sum(c["weight"] for c in result["components"]) == pytest.approx(1.0)

    def test_fondamental_negatif_ecarte_sa_composante(self):
        """Un exercice à perte ne produit pas de PER exploitable."""
        result = fairvalue.compute(_history(), _points(earnings=-3.0))
        assert "earnings" not in {c["key"] for c in result["components"]}
        assert "earnings" in {e["key"] for e in result["excluded_components"]}


class TestPonderationInverseVolatilite:
    def test_le_multiple_stable_pese_davantage(self):
        """Le cœur de la méthode : moins un multiple varie, plus il compte."""
        history = _history()
        # Bénéfices en dents de scie -> PER instable ; ventes constantes -> P/S stable.
        end = dt.date.today()
        points = []
        for i in range(5):
            period = dt.date(end.year - 5 + i, 12, 31)
            points.append(
                FundamentalPoint(
                    available_from=period - dt.timedelta(days=400),
                    period_ending=period,
                    values={
                        "earnings": 5.0 if i % 2 == 0 else 1.5,
                        "sales": 50.0,
                        "book_value": 25.0,
                        "cash_flow": 4.0,
                    },
                )
            )
        result = fairvalue.compute(history, points)
        weights = {c["key"]: c["weight"] for c in result["components"]}
        dispersions = {c["key"]: c["dispersion"] for c in result["components"]}

        assert dispersions["earnings"] > dispersions["sales"]
        assert weights["sales"] > weights["earnings"]


class TestPrimeDeQualite:
    def test_qualite_maximale_donne_la_prime_plafond(self):
        result = fairvalue.compute(_history(), _points(), QualityScore(100.0, []))
        assert result["quality_factor"] == pytest.approx(1 + settings.valuation_quality_cap)

    def test_qualite_minimale_donne_la_decote_plancher(self):
        result = fairvalue.compute(_history(), _points(), QualityScore(0.0, []))
        assert result["quality_factor"] == pytest.approx(1 - settings.valuation_quality_cap)

    def test_qualite_neutre_ne_modifie_rien(self):
        result = fairvalue.compute(_history(), _points(), QualityScore(50.0, []))
        assert result["quality_factor"] == pytest.approx(1.0)

    def test_le_facteur_reste_borne(self):
        for score in (-50.0, 0.0, 50.0, 100.0, 150.0):
            factor = fairvalue.compute(
                _history(), _points(), QualityScore(score, [])
            )["quality_factor"]
            assert 1 - settings.valuation_quality_cap <= factor <= 1 + settings.valuation_quality_cap


class TestSocietesFinancieres:
    def test_le_cash_flow_est_ecarte_pour_une_banque(self):
        result = fairvalue.compute(
            _history(), _points(), sector="Financial Services"
        )
        assert "cash_flow" not in {c["key"] for c in result["components"]}
        excluded = {e["key"]: e["reason"] for e in result["excluded_components"]}
        assert "cash_flow" in excluded
        assert "financière" in excluded["cash_flow"]

    def test_le_cash_flow_est_conserve_ailleurs(self):
        result = fairvalue.compute(_history(), _points(), sector="Technology")
        assert "cash_flow" in {c["key"] for c in result["components"]}


class TestSerieEtProjection:
    def test_la_courbe_couvre_toute_la_fenetre_affichee(self):
        result = fairvalue.compute(_history(), _points())
        series = result["series"]
        assert len(series["dates"]) == len(series["fair_value"]) == len(series["price"])
        assert all(v is not None for v in series["fair_value"])

    def test_la_projection_couvre_l_horizon_demande(self):
        result = fairvalue.compute(_history(), _points())
        assert len(result["projection"]["dates"]) > 0
        first = dt.date.fromisoformat(result["projection"]["dates"][0])
        last = dt.date.fromisoformat(result["projection"]["dates"][-1])
        months = (last.year - first.year) * 12 + last.month - first.month
        assert months >= settings.valuation_projection_months - 2

    def test_la_projection_est_signalee_comme_illustrative(self):
        result = fairvalue.compute(_history(), _points())
        assert "non prédictif" in result["projection"]["note"]


class TestVerdict:
    @pytest.mark.parametrize(
        ("gap", "attendu"),
        [
            (-0.40, "sous-évalué"),
            (-0.15, "sous-évalué"),
            (-0.05, "correctement valorisé"),
            (0.0, "correctement valorisé"),
            (0.14, "correctement valorisé"),
            (0.15, "surévalué"),
            (0.60, "surévalué"),
            (None, "indeterminé"),
        ],
    )
    def test_seuils(self, gap, attendu):
        assert fairvalue._verdict(gap) == attendu


class TestGardeFous:
    def test_historique_trop_court_est_refuse(self):
        with pytest.raises(fairvalue.ValuationError, match="trop court"):
            fairvalue.compute(_history(days=30), _points())

    def test_aucun_fondamental_exploitable_est_refuse(self):
        points = _points(earnings=-1.0, sales=-1.0, book_value=-1.0, cash_flow=-1.0)
        with pytest.raises(fairvalue.ValuationError, match="Aucun multiple"):
            fairvalue.compute(_history(), points)

    def test_historique_vide_est_refuse(self):
        with pytest.raises(fairvalue.ValuationError):
            fairvalue.compute([], _points())

    def test_confiance_signale_le_manque_d_exercices(self):
        result = fairvalue.compute(_history(), _points(years=4))
        assert result["confidence"]["level"] == "faible"
        assert result["confidence"]["caveats"]


class TestSeriesParAction:
    def test_le_nombre_d_actions_convertit_en_par_action(self):
        statements = {
            "income": [
                {
                    "period_ending": "2025-12-31",
                    "total_revenue": 1000.0,
                    "net_income": 100.0,
                    "diluted_earnings_per_share": 2.0,
                    "weighted_average_diluted_shares_outstanding": 50.0,
                }
            ],
            "balance": [{"period_ending": "2025-12-31", "common_stock_equity": 500.0}],
            "cash": [{"period_ending": "2025-12-31", "free_cash_flow": 150.0}],
        }
        points = build_points(statements)
        assert len(points) == 1
        values = points[0].values
        assert values["earnings"] == 2.0
        assert values["sales"] == 20.0
        assert values["book_value"] == 10.0
        assert values["cash_flow"] == 3.0

    def test_le_decalage_de_publication_est_applique(self):
        """Les comptes ne sont réputés connus qu'après leur publication."""
        statements = {
            "income": [
                {
                    "period_ending": "2025-12-31",
                    "total_revenue": 1000.0,
                    "diluted_earnings_per_share": 2.0,
                    "weighted_average_diluted_shares_outstanding": 50.0,
                }
            ],
            "balance": [],
            "cash": [],
        }
        point = build_points(statements)[0]
        assert point.available_from > point.period_ending

    def test_sans_nombre_d_actions_l_exercice_est_ignore(self):
        statements = {
            "income": [{"period_ending": "2025-12-31", "total_revenue": 1000.0}],
            "balance": [],
            "cash": [],
        }
        assert build_points(statements) == []

    def test_report_amont_signale(self):
        """Le début de fenêtre antérieur à la première publication est signalé."""
        index = pd.date_range("2021-01-01", periods=1200, freq="D")
        points = _points(years=2)
        frame, backfilled_until = to_daily_frame(points, index)
        assert backfilled_until is not None
        assert frame["earnings"].notna().all()
