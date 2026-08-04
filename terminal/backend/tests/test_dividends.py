"""Tests de la sûreté du dividende et de la prochaine échéance.

Ce module produit une pastille verte, orange ou rouge sur laquelle une
décision se prend. Les seuils et les cas limites sont donc verrouillés, en
particulier ceux où résultat et trésorerie racontent deux histoires
différentes.
"""

import datetime as dt

import pytest

from app.pea.dividends import (
    Safety,
    fcf_coverage,
    frequency,
    next_ex_date,
    safety,
)


class TestCouvertureParLeCash:
    def test_couverture_normale(self):
        assert fcf_coverage(1000.0, -600.0) == pytest.approx(0.6)

    def test_le_signe_du_tableau_de_flux_est_absorbe(self):
        """Les dividendes versés y figurent en négatif."""
        assert fcf_coverage(1000.0, -600.0) == fcf_coverage(1000.0, 600.0)

    def test_un_flux_libre_negatif_ne_couvre_rien(self):
        """Cas Engie : résultat positif mais trésorerie libre négative."""
        assert fcf_coverage(-8743.0, -4529.0) == float("inf")

    def test_absence_de_dividende(self):
        assert fcf_coverage(1000.0, 0.0) == 0.0

    def test_donnees_manquantes(self):
        assert fcf_coverage(None, -600.0) is None
        assert fcf_coverage(1000.0, None) is None


class TestVerdictDeSurete:
    def test_dividende_confortable(self):
        verdict, _ = safety(payout_ratio=0.35, coverage=0.40, dividend_yield=0.03)
        assert verdict is Safety.SAFE

    def test_distribution_elevee_mais_couverte(self):
        verdict, _ = safety(payout_ratio=0.75, coverage=0.50, dividend_yield=0.04)
        assert verdict is Safety.STRETCHED

    def test_dividende_superieur_au_resultat(self):
        """Cas Sanofi : 127 % du bénéfice distribué."""
        verdict, reason = safety(payout_ratio=1.27, coverage=0.66, dividend_yield=0.055)
        assert verdict is Safety.UNCOVERED
        assert "dépasse le résultat" in reason

    def test_le_cash_prime_sur_un_resultat_flatteur(self):
        """Cas Engie : payout acceptable mais flux de trésorerie libre négatif.

        C'est le cas qui justifie de regarder les deux angles.
        """
        verdict, _ = safety(
            payout_ratio=0.83, coverage=float("inf"), dividend_yield=0.05
        )
        assert verdict is Safety.UNCOVERED

    def test_le_plus_defavorable_des_deux_angles_l_emporte(self):
        verdict, _ = safety(payout_ratio=0.20, coverage=1.40, dividend_yield=0.03)
        assert verdict is Safety.UNCOVERED

    def test_absence_de_dividende(self):
        verdict, reason = safety(payout_ratio=None, coverage=None, dividend_yield=0.0)
        assert verdict is Safety.NONE
        assert "ne verse pas" in reason

    def test_un_taux_de_distribution_nul_ne_vaut_pas_feu_vert(self):
        """Cas Adyen : aucune distribution, donc rien à qualifier de sûr."""
        verdict, _ = safety(payout_ratio=0.0, coverage=None, dividend_yield=None)
        assert verdict is Safety.NONE

    def test_rendement_inconnu_mais_distribution_reelle(self):
        """Le rendement peut manquer alors que la société distribue bien."""
        verdict, _ = safety(payout_ratio=0.45, coverage=0.5, dividend_yield=None)
        assert verdict is Safety.SAFE

    def test_donnees_absentes_ne_valent_pas_feu_vert(self):
        verdict, _ = safety(payout_ratio=None, coverage=None, dividend_yield=0.04)
        assert verdict is Safety.UNKNOWN

    @pytest.mark.parametrize(
        ("payout", "attendu"),
        [
            (0.59, Safety.SAFE),
            (0.60, Safety.SAFE),
            (0.61, Safety.STRETCHED),
            (1.00, Safety.STRETCHED),
            (1.01, Safety.UNCOVERED),
        ],
    )
    def test_seuils_du_taux_de_distribution(self, payout, attendu):
        verdict, _ = safety(payout_ratio=payout, coverage=None, dividend_yield=0.03)
        assert verdict is attendu

    def test_la_justification_est_toujours_fournie(self):
        for payout in (0.3, 0.8, 1.5, None):
            _, reason = safety(payout, 0.5, 0.03)
            assert reason


class TestRythmeDeVersement:
    def test_trimestriel(self):
        """Cas TotalEnergies : environ 91 jours entre détachements."""
        dates = ["2025-03-26", "2025-06-19", "2025-10-01", "2025-12-31", "2026-03-31"]
        label, median = frequency(dates)
        assert label == "trimestriel"
        assert 80 <= median <= 110

    def test_annuel(self):
        dates = ["2022-05-06", "2023-05-30", "2024-05-13", "2025-05-12", "2026-05-05"]
        label, median = frequency(dates)
        assert label == "annuel"
        assert 350 <= median <= 380

    def test_semestriel(self):
        dates = ["2024-01-15", "2024-07-15", "2025-01-15", "2025-07-15"]
        assert frequency(dates)[0] == "semestriel"

    def test_historique_trop_court(self):
        assert frequency(["2026-05-05"]) == ("inconnu", None)

    def test_seuls_les_derniers_versements_comptent(self):
        """Un changement de politique ancien ne doit pas fausser le rythme."""
        anciens = [f"20{y:02d}-06-01" for y in range(0, 10)]
        recents = ["2025-03-01", "2025-06-01", "2025-09-01", "2025-12-01", "2026-03-01"]
        assert frequency(anciens + recents)[0] == "trimestriel"


class TestProchaineEcheance:
    TODAY = dt.date(2026, 8, 3)

    def test_projection_a_partir_du_rythme(self):
        dates = ["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
        result = next_ex_date(dates, today=self.TODAY)
        assert result is not None
        # Environ un trimestre après le dernier détachement.
        assert dt.date(2026, 9, 1) <= result <= dt.date(2026, 10, 15)

    def test_une_date_future_deja_publiee_est_reprise_telle_quelle(self):
        """La source publie parfois le détachement dès son annonce."""
        dates = ["2025-05-05", "2026-05-05", "2026-11-20"]
        assert next_ex_date(dates, today=self.TODAY) == dt.date(2026, 11, 20)

    def test_projection_annuelle(self):
        dates = ["2023-05-30", "2024-05-13", "2025-05-12", "2026-05-05"]
        result = next_ex_date(dates, today=self.TODAY)
        assert result is not None
        assert result.year == 2027

    def test_toujours_dans_le_futur(self):
        dates = ["2024-05-30", "2025-05-13", "2026-05-12"]
        result = next_ex_date(dates, today=self.TODAY)
        assert result is None or result > self.TODAY

    def test_historique_interrompu_de_longue_date(self):
        """Un dividende suspendu depuis des années ne produit pas de date."""
        dates = ["2015-05-30", "2016-05-13", "2017-05-12"]
        assert next_ex_date(dates, today=self.TODAY) is None

    def test_sans_historique(self):
        assert next_ex_date([], today=self.TODAY) is None

    def test_historique_trop_court_pour_un_rythme(self):
        assert next_ex_date(["2026-05-05"], today=self.TODAY) is None
