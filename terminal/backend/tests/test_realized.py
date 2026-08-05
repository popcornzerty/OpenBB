"""Tests des cessions et plus-values réalisées.

Une vente doit laisser une trace exacte : la plus-value encaissée et les
dividendes touchés pendant la détention ne sont pas récupérables une fois la
ligne partie du portefeuille.
"""

import datetime as dt

import pytest

from app.portfolio.realized import Sale, totals


def sale(**kwargs) -> Sale:
    base = {
        "symbol": "MC.PA",
        "quantity": 10.0,
        "average_cost": 500.0,
        "sale_price": 600.0,
        "opened_at": "2023-01-10",
        "closed_at": "2025-01-10",
    }
    return Sale(**{**base, "id": "test", **kwargs})


class TestCalculDUneCession:
    def test_plus_value(self):
        s = sale()
        assert s.cost_basis == pytest.approx(5000.0)
        assert s.proceeds == pytest.approx(6000.0)
        assert s.gain == pytest.approx(1000.0)
        assert s.gain_percent == pytest.approx(0.20)

    def test_moins_value(self):
        s = sale(sale_price=400.0)
        assert s.gain == pytest.approx(-1000.0)
        assert s.gain_percent == pytest.approx(-0.20)

    def test_prix_de_revient_nul_ne_divise_pas_par_zero(self):
        """Une ligne importée sans PRU ne doit pas faire planter le calcul."""
        s = sale(average_cost=0.0)
        assert s.gain == pytest.approx(6000.0)
        assert s.gain_percent is None

    def test_duree_de_detention(self):
        assert sale().holding_days == (
            dt.date(2025, 1, 10) - dt.date(2023, 1, 10)
        ).days

    def test_duree_inconnue_sans_date_d_entree(self):
        assert sale(opened_at="").holding_days is None

    def test_le_rendement_total_ajoute_les_dividendes(self):
        """La plus-value seule sous-estime ce qu'a rapporté la ligne."""
        assert sale(dividends=250.0).as_dict()["total_return"] == pytest.approx(1250.0)


class TestCumuls:
    SALES = [
        sale(id="a", symbol="MC.PA", quantity=10, average_cost=500, sale_price=600),
        sale(id="b", symbol="SAN.PA", quantity=100, average_cost=80, sale_price=70,
             dividends=300.0),
    ]

    def test_gain_net_des_deux_operations(self):
        # +1000 sur la première, -1000 sur la seconde.
        assert totals(self.SALES)["gain"] == pytest.approx(0.0)

    def test_capital_engage(self):
        assert totals(self.SALES)["cost_basis"] == pytest.approx(13000.0)

    def test_pourcentage_rapporte_au_capital_engage(self):
        result = totals([self.SALES[0]])
        assert result["gain_percent"] == pytest.approx(0.20)

    def test_les_dividendes_des_lignes_vendues_sont_conserves(self):
        assert totals(self.SALES)["dividends"] == pytest.approx(300.0)

    def test_rendement_total(self):
        assert totals(self.SALES)["total_return"] == pytest.approx(300.0)

    def test_taux_de_reussite(self):
        assert totals(self.SALES)["win_rate"] == pytest.approx(0.5)

    def test_aucune_cession(self):
        result = totals([])
        assert result["count"] == 0
        assert result["gain"] == 0
        assert result["gain_percent"] is None
        assert result["win_rate"] is None
