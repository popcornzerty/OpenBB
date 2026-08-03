"""Tests du classement par décote ajustée.

Le point délicat n'est pas le calcul mais l'ordre qu'il produit : le
classement doit refuser de mettre en tête une décote spectaculaire mais
fragile. Ces tests verrouillent précisément ce comportement.
"""

import pytest

from app.valuation.ranking import (
    RankingRow,
    adjusted_discount,
    breadth_factor,
    period_factor,
    reliability,
    stability_factor,
)


def valuation(periods=5, components=None, gap=-0.2):
    """Fabrique un résultat de valorisation minimal."""
    if components is None:
        components = [
            {"key": "earnings", "dispersion": 0.15, "weight": 0.5},
            {"key": "sales", "dispersion": 0.15, "weight": 0.5},
        ]
    return {
        "gap": gap,
        "components": components,
        "confidence": {"periods_used": periods, "level": "moyenne"},
    }


class TestFacteurExercices:
    def test_plus_d_exercices_vaut_plus_de_fiabilite(self):
        assert period_factor(3) < period_factor(4) < period_factor(5) < period_factor(6)

    def test_quatre_exercices_est_fortement_penalise(self):
        """Un exercice atypique y pèse un quart de l'échantillon."""
        assert period_factor(4) == 0.5

    def test_le_plafond_des_sources_gratuites_reste_penalise(self):
        assert period_factor(5) == 0.8

    def test_plateau_au_dela_de_six(self):
        assert period_factor(6) == period_factor(10) == 1.0


class TestFacteurNombreDeMultiples:
    def test_un_seul_multiple_est_fragile(self):
        assert breadth_factor(1) == 0.4

    def test_quatre_multiples_concordants_valent_pleine_confiance(self):
        assert breadth_factor(4) == 1.0

    def test_croissance_monotone(self):
        values = [breadth_factor(n) for n in range(5)]
        assert values == sorted(values)

    def test_aucun_multiple_annule_la_fiabilite(self):
        assert breadth_factor(0) == 0.0


class TestFacteurStabilite:
    def test_multiples_stables_valent_pleine_confiance(self):
        assert stability_factor(0.10) == 1.0

    def test_multiples_tres_disperses_sont_penalises(self):
        assert stability_factor(0.80) == 0.3

    def test_decroissance_entre_les_bornes(self):
        assert stability_factor(0.20) > stability_factor(0.40) > stability_factor(0.60)

    def test_dispersion_inconnue_prend_une_valeur_mediane(self):
        assert stability_factor(None) == 0.5


class TestFiabiliteGlobale:
    def test_les_axes_se_multiplient_au_lieu_de_se_compenser(self):
        """Une faiblesse sur un axe ne doit pas être rattrapée ailleurs."""
        fragile = valuation(periods=4, components=[{"dispersion": 0.15, "weight": 1.0}])
        score, _ = reliability(fragile)
        # 0.5 (exercices) × 0.4 (un seul multiple) × 1.0 (stable) = 0.2
        assert score == pytest.approx(0.2)

    def test_la_dispersion_est_ponderee_par_le_poids_du_multiple(self):
        """Un multiple très dispersé mais peu pondéré ne doit pas dominer."""
        components = [
            {"dispersion": 0.10, "weight": 0.9},
            {"dispersion": 2.00, "weight": 0.1},
        ]
        _, parts = reliability(valuation(components=components))
        # Moyenne pondérée : 0.10×0.9 + 2.00×0.1 = 0.29, loin de la moyenne
        # arithmétique qui vaudrait 1.05.
        assert parts["weighted_dispersion"] == pytest.approx(0.29)

    def test_le_detail_est_remonte(self):
        _, parts = reliability(valuation())
        assert set(parts) >= {"periods", "breadth", "stability", "weighted_dispersion"}

    def test_fiabilite_bornee_entre_zero_et_un(self):
        for periods in (0, 4, 5, 12):
            for count in (0, 1, 4):
                components = [{"dispersion": 0.3, "weight": 1.0}] * count
                score, _ = reliability(valuation(periods=periods, components=components))
                assert 0.0 <= score <= 1.0


class TestDecoteAjustee:
    def test_une_sous_cote_donne_une_decote_positive(self):
        assert adjusted_discount(-0.40, 1.0) == pytest.approx(0.40)

    def test_une_survalorisation_donne_une_valeur_negative(self):
        assert adjusted_discount(0.30, 1.0) == pytest.approx(-0.30)

    def test_la_fiabilite_ramene_la_decote_a_ce_qu_on_peut_affirmer(self):
        """40 % à demi fiable vaut 20 % pleinement fiable — le cœur du classement."""
        assert adjusted_discount(-0.40, 0.5) == pytest.approx(adjusted_discount(-0.20, 1.0))

    def test_sans_ecart_pas_de_decote(self):
        assert adjusted_discount(None, 1.0) is None


class TestOrdreDuClassement:
    def _row(self, symbol, discount):
        return RankingRow(
            symbol=symbol, name=symbol, sector="", country="", index="",
            last_price=100.0, fair_value=120.0, gap=-0.2, reliability=1.0,
            reliability_parts={}, adjusted_discount=discount, verdict="",
            confidence="", periods_used=5, components=3, currency="EUR",
        )

    def test_une_grosse_decote_fragile_passe_derriere_une_petite_solide(self):
        """C'est exactement le piège que le classement doit éviter."""
        fragile = adjusted_discount(-0.45, 0.3)   # 13,5 %
        solide = adjusted_discount(-0.20, 1.0)    # 20 %
        assert solide > fragile

    def test_les_titres_sans_estimation_ferment_la_marche(self):
        rows = [self._row("A", None), self._row("B", 0.1), self._row("C", -0.3)]
        ordered = sorted(
            rows,
            key=lambda r: (r.adjusted_discount is None, -(r.adjusted_discount or 0)),
        )
        assert [r.symbol for r in ordered] == ["B", "C", "A"]

    def test_ordre_decroissant_de_decote(self):
        rows = [self._row("A", 0.05), self._row("B", 0.30), self._row("C", 0.15)]
        ordered = sorted(
            rows,
            key=lambda r: (r.adjusted_discount is None, -(r.adjusted_discount or 0)),
        )
        assert [r.symbol for r in ordered] == ["B", "C", "A"]
