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


class TestFraisDeCession:
    """Ce qui rentre sur le compte est le produit net, pas le produit brut."""

    def test_les_frais_reduisent_la_plus_value(self):
        s = sale(fees=25.0)
        assert s.proceeds == pytest.approx(6000.0)
        assert s.net_proceeds == pytest.approx(5975.0)
        assert s.gain == pytest.approx(975.0)

    def test_le_pourcentage_suit(self):
        assert sale(fees=25.0).gain_percent == pytest.approx(975.0 / 5000.0)

    def test_des_frais_peuvent_annuler_un_gain(self):
        s = sale(sale_price=505.0, fees=100.0)
        assert s.gain == pytest.approx(-50.0)

    def test_sans_frais_le_calcul_est_inchange(self):
        assert sale().gain == pytest.approx(1000.0)
        assert sale().net_proceeds == pytest.approx(sale().proceeds)

    def test_le_produit_brut_reste_lisible(self):
        """Distinguer brut et net permet de vérifier le relevé de courtier."""
        d = sale(fees=25.0).as_dict()
        assert d["proceeds"] == pytest.approx(6000.0)
        assert d["net_proceeds"] == pytest.approx(5975.0)
        assert d["fees"] == pytest.approx(25.0)

    def test_les_cumuls_agregent_les_frais(self):
        result = totals([sale(id="a", fees=25.0), sale(id="b", fees=15.0)])
        assert result["fees"] == pytest.approx(40.0)
        assert result["gain"] == pytest.approx(1000.0 - 25.0 + 1000.0 - 15.0)

    def test_le_rendement_total_part_du_gain_net(self):
        assert sale(fees=25.0, dividends=250.0).as_dict()["total_return"] == pytest.approx(
            1225.0
        )


class TestNoteDeCession:
    def test_la_note_est_conservee(self):
        assert sale(note="arbitrage vers la santé").as_dict()["note"] == (
            "arbitrage vers la santé"
        )

    def test_une_note_absente_ne_vaut_pas_None(self):
        """Le rendu doit pouvoir la traiter comme une chaîne sans test."""
        assert sale().as_dict()["note"] == ""


class TestModificationDUneCession:
    """Le relevé du courtier arrive après coup.

    Pouvoir reprendre le prix exact et les frais réels évite d'annuler puis de
    ressaisir — manœuvre qui remet les titres en portefeuille entre-temps, au
    risque d'oublier de refaire la vente.
    """

    @pytest.fixture
    def magasin(self, tmp_path, monkeypatch):
        from app.portfolio import realized

        monkeypatch.setattr(realized, "_path", lambda: tmp_path / "realized.json")
        realized.save([sale(id="x", fees=0.0, note="")])
        return realized

    def test_correction_du_prix(self, magasin):
        modifiee = magasin.update("x", {"sale_price": 610.0})
        assert modifiee.sale_price == pytest.approx(610.0)
        assert modifiee.gain == pytest.approx(1100.0)

    def test_ajout_de_frais_apres_coup(self, magasin):
        modifiee = magasin.update("x", {"fees": 25.0})
        assert modifiee.gain == pytest.approx(975.0)

    def test_correction_du_prix_de_revient(self, magasin):
        modifiee = magasin.update("x", {"average_cost": 520.0})
        assert modifiee.cost_basis == pytest.approx(5200.0)
        assert modifiee.gain == pytest.approx(800.0)

    def test_correction_des_dates(self, magasin):
        modifiee = magasin.update("x", {"opened_at": "2022-06-01", "closed_at": "2025-06-01"})
        assert modifiee.holding_days == 1096

    def test_ajout_du_motif(self, magasin):
        assert magasin.update("x", {"note": "arbitrage"}).note == "arbitrage"

    def test_les_champs_omis_ne_bougent_pas(self, magasin):
        magasin.update("x", {"fees": 25.0})
        conservee = magasin.get("x")
        assert conservee.sale_price == pytest.approx(600.0)
        assert conservee.quantity == pytest.approx(10.0)

    def test_la_quantite_n_est_pas_modifiable(self, magasin):
        """Elle est liée au portefeuille : la changer désaccorderait les deux."""
        magasin.update("x", {"quantity": 999.0})
        assert magasin.get("x").quantity == pytest.approx(10.0)

    def test_les_dividendes_figes_ne_bougent_pas(self, magasin):
        magasin.update("x", {"dividends": 999.0})
        assert magasin.get("x").dividends == pytest.approx(0.0)

    def test_la_modification_est_persistee(self, magasin):
        magasin.update("x", {"fees": 25.0})
        assert magasin.load()[0].fees == pytest.approx(25.0)

    def test_une_cession_inconnue(self, magasin):
        assert magasin.update("inexistante", {"fees": 10.0}) is None
