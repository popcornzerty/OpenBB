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
    dividend_growth,
    fcf_coverage,
    frequency,
    next_ex_date,
    payout_ratio,
    safety,
    trailing_dividend,
    yearly_totals,
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

    def test_dividende_superieur_au_resultat_mais_couvert_en_cash(self):
        """Cas Sanofi : 127 % du bénéfice publié, 66 % du flux libre.

        Le résultat IFRS est bruité par les éléments non récurrents ; le
        dividende, lui, est bien financé. Un « non couvert » écarterait à tort
        un titre qui augmente sa distribution depuis trente ans.
        """
        verdict, reason = safety(payout_ratio=1.27, coverage=0.66, dividend_yield=0.055)
        assert verdict is Safety.STRETCHED
        assert "dépasse le résultat publié" in reason

    def test_dividende_superieur_au_resultat_et_mal_couvert(self):
        verdict, reason = safety(payout_ratio=1.27, coverage=1.20, dividend_yield=0.055)
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


class TestCroissanceDuDividende:
    TODAY = dt.date(2026, 8, 4)

    def _rows(self, per_year: dict[int, list[float]]):
        rows = []
        for year, amounts in per_year.items():
            for i, amount in enumerate(amounts):
                rows.append(
                    {"ex_dividend_date": f"{year}-{(i * 3) + 1:02d}-15", "amount": amount}
                )
        return rows

    def test_agregation_par_annee_civile(self):
        """Quatre acomptes de 1 € valent un versement annuel de 4 €."""
        totals = yearly_totals(self._rows({2024: [1.0, 1.0, 1.0, 1.0]}))
        assert totals[2024] == pytest.approx(4.0)

    def test_croissance_reguliere(self):
        """Cas Sanofi : environ +4,5 % l'an."""
        rows = self._rows(
            {2020: [3.15], 2021: [3.20], 2022: [3.33], 2023: [3.56],
             2024: [3.76], 2025: [3.92]}
        )
        cagr, window = dividend_growth(rows, today=self.TODAY)
        assert cagr == pytest.approx(0.045, abs=0.005)
        assert window == "2020–2025"

    def test_l_annee_en_cours_est_exclue(self):
        """Son total partiel ferait apparaître une chute inexistante."""
        rows = self._rows(
            {2022: [1.0], 2023: [1.1], 2024: [1.2], 2025: [1.3], 2026: [0.4]}
        )
        cagr, window = dividend_growth(rows, today=self.TODAY)
        assert cagr is not None and cagr > 0
        assert window.endswith("2025")

    def test_un_dividende_interrompu_ne_fausse_pas_la_periode(self):
        """Cas Stellantis : rien versé de 2012 à 2020.

        Comparer 2011 à 2025 comme s'il s'agissait de cinq ans annonçait
        +50 % l'an, alors que le dividende a fondu depuis 2021.
        """
        rows = self._rows(
            {2010: [0.123], 2011: [0.090],
             2021: [2.353], 2022: [1.040], 2023: [1.340], 2024: [1.550], 2025: [0.680]}
        )
        cagr, window = dividend_growth(rows, today=self.TODAY)
        assert window == "2021–2025"
        assert cagr is not None and cagr < 0

    def test_la_fenetre_est_bornee(self):
        """Un historique de vingt ans ne donne pas une croissance sur vingt ans."""
        rows = self._rows({year: [1.0 + (year - 2005) * 0.1] for year in range(2005, 2026)})
        _, window = dividend_growth(rows, today=self.TODAY)
        start, end = window.split("–")
        assert int(end) - int(start) == 5

    def test_historique_trop_court(self):
        rows = self._rows({2024: [1.0], 2025: [1.1]})
        assert dividend_growth(rows, today=self.TODAY) == (None, "")

    def test_dividende_arrete_depuis_longtemps(self):
        rows = self._rows({2018: [1.0], 2019: [1.1], 2020: [1.2], 2021: [1.3]})
        assert dividend_growth(rows, today=self.TODAY) == (None, "")

    def test_sans_historique(self):
        assert dividend_growth([], today=self.TODAY) == (None, "")

    def test_croissance_negative_est_rapportee(self):
        rows = self._rows({2021: [2.0], 2022: [1.8], 2023: [1.5], 2024: [1.2], 2025: [1.0]})
        cagr, _ = dividend_growth(rows, today=self.TODAY)
        assert cagr is not None and cagr < 0

    def test_un_point_de_depart_nul_ne_produit_pas_de_taux(self):
        rows = self._rows({2021: [0.0], 2022: [1.0], 2023: [1.1], 2024: [1.2], 2025: [1.3]})
        assert dividend_growth(rows, today=self.TODAY)[0] is None


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


class TestTauxDeDistributionRecalcule:
    """Le champ fourni par la source est parfois faux.

    Deutsche Telekom était annoncé à 105 % de distribution alors que son
    dividende de 1,00 € rapporté à un bénéfice publié de 1,97 € en fait 51 %.
    Une pastille rouge sur une donnée fausse est pire qu'une absence de
    pastille : elle écarte un titre sain.
    """

    TODAY = dt.date(2026, 8, 5)
    DTE = [
        {"ex_dividend_date": dt.date(2026, 4, 2), "amount": 1.00},
        {"ex_dividend_date": dt.date(2025, 4, 10), "amount": 0.90},
        {"ex_dividend_date": dt.date(2024, 4, 11), "amount": 0.77},
    ]

    def test_cas_deutsche_telekom(self):
        assert payout_ratio(self.DTE, 1.97, self.TODAY) == pytest.approx(0.5076, abs=1e-3)

    def test_somme_des_detachements_de_l_annee(self):
        rows = [
            {"ex_dividend_date": dt.date(2026, 3, 2), "amount": 0.30},
            {"ex_dividend_date": dt.date(2026, 6, 2), "amount": 0.30},
            {"ex_dividend_date": dt.date(2025, 12, 2), "amount": 0.30},
        ]
        assert trailing_dividend(rows, self.TODAY) == pytest.approx(0.90)

    def test_un_detachement_trop_ancien_est_exclu(self):
        rows = [{"ex_dividend_date": dt.date(2025, 1, 5), "amount": 2.0}]
        assert trailing_dividend(rows, self.TODAY) is None

    def test_dividende_suspendu_ne_vaut_pas_taux_nul(self):
        """Un taux de 0 % se lirait comme une distribution prudente."""
        assert payout_ratio([], 5.0, self.TODAY) is None

    def test_benefice_negatif_ne_donne_pas_de_taux(self):
        assert payout_ratio(self.DTE, -1.0, self.TODAY) is None

    def test_benefice_absent(self):
        assert payout_ratio(self.DTE, None, self.TODAY) is None

    def test_dates_en_chaine(self):
        rows = [{"ex_dividend_date": "2026-04-02", "amount": 1.00}]
        assert payout_ratio(rows, 2.0, self.TODAY) == pytest.approx(0.50)


class TestPrimauteDuFluxDeTresorerie:
    """Un dividende se paie en trésorerie, pas en résultat comptable.

    Le résultat publié est bruité par les dépréciations, les éléments non
    récurrents et les intérêts minoritaires. Le laisser seul déclencher un
    « non couvert » revenait à sanctionner une écriture comptable.
    """

    def test_resultat_depasse_mais_tresorerie_confortable(self):
        verdict, reason = safety(1.05, 0.30, 3.5)
        assert verdict is Safety.STRETCHED
        assert "financé par la trésorerie" in reason

    def test_resultat_depasse_et_tresorerie_tendue(self):
        verdict, _ = safety(1.05, 0.90, 3.5)
        assert verdict is Safety.UNCOVERED

    def test_resultat_depasse_sans_donnee_de_tresorerie(self):
        """Sans contre-épreuve, le taux de distribution garde son autorité."""
        verdict, _ = safety(1.05, None, 3.5)
        assert verdict is Safety.UNCOVERED

    def test_un_flux_libre_insuffisant_reste_eliminatoire(self):
        verdict, _ = safety(0.30, 1.40, 3.5)
        assert verdict is Safety.UNCOVERED

    def test_un_flux_libre_negatif_reste_eliminatoire(self):
        verdict, _ = safety(0.30, float("inf"), 3.5)
        assert verdict is Safety.UNCOVERED

    def test_distribution_et_tresorerie_saines(self):
        verdict, _ = safety(0.45, 0.35, 3.5)
        assert verdict is Safety.SAFE


class TestBorneDeToleranceDuCash:
    """Une trésorerie confortable ne rachète pas un bénéfice effondré.

    Distribuer plus que son résultat comptable est courant chez les sociétés
    à forts amortissements. Distribuer huit fois son résultat ne relève plus
    de la convention comptable — cas Solvay, dont le bénéfice publié était
    quasi nul.
    """

    def test_juste_sous_la_borne(self):
        verdict, _ = safety(1.90, 0.50, 0.04)
        assert verdict is Safety.STRETCHED

    def test_a_la_borne(self):
        verdict, _ = safety(2.00, 0.50, 0.04)
        assert verdict is Safety.STRETCHED

    def test_au_dela_de_la_borne(self):
        verdict, _ = safety(2.01, 0.50, 0.04)
        assert verdict is Safety.UNCOVERED

    def test_cas_solvay(self):
        verdict, _ = safety(81.0, 0.56, 0.06)
        assert verdict is Safety.UNCOVERED

    def test_cas_deutsche_telekom(self):
        verdict, _ = safety(1.05, 0.30, 0.036)
        assert verdict is Safety.STRETCHED
