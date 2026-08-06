"""Tests du branchement d'une source d'estimations payante.

Aucune clé n'étant posée ici, le consensus payant est simulé. Ce qui est
vérifié, c'est le **raccordement** : l'ancrage des exercices reste celui de la
source gratuite, dont on sait qu'il colle aux comptes publiés, et une
défaillance du fournisseur payant ne doit jamais faire perdre les colonnes
déjà obtenues gratuitement.
"""

import pytest

from app.providers.estimates import _merge_premium
from app.valuation import tables
from tests.test_valuation_tables import (
    CLOSES,
    CONSENSUS,
    STATEMENTS,
    row_of,
)

FREE = {
    "periods": [
        {"offset": 0, "eps": 3.0, "revenue": 1200.0, "analysts": 8, "thin": False,
         "year_ago_eps": 2.0},
        {"offset": 1, "eps": 3.5, "revenue": 1300.0, "analysts": 8, "thin": False,
         "year_ago_eps": 3.0},
    ],
    "fiscal_year_end": "2025-12-31",
    "price_target": {"mean": 45.0},
    "trailing_eps": 2.0,
    "dividend_rate": 1.0,
}


class TestFusionDuConsensusPayant:
    def test_ajoute_l_ebitda_sans_toucher_au_reste(self):
        merged = _merge_premium(FREE, [{"year": 2026, "ebitda": 400.0}])
        first = merged["periods"][0]
        assert first["ebitda"] == 400.0
        assert first["eps"] == 3.0
        assert first["revenue"] == 1200.0

    def test_ajoute_des_exercices_plus_lointains(self):
        merged = _merge_premium(
            FREE, [{"year": 2028, "eps": 4.2, "ebitda": 500.0}]
        )
        assert [p["offset"] for p in merged["periods"]] == [0, 1, 2]
        assert merged["periods"][2]["eps"] == 4.2

    def test_la_source_gratuite_prime_sur_les_champs_communs(self):
        """Son ancrage est vérifié contre les comptes publiés, pas celui-ci."""
        merged = _merge_premium(FREE, [{"year": 2026, "eps": 9.9}])
        assert merged["periods"][0]["eps"] == 3.0

    def test_un_exercice_deja_publie_est_ignore(self):
        merged = _merge_premium(FREE, [{"year": 2024, "eps": 1.0}])
        assert all(p["offset"] >= 0 for p in merged["periods"])
        assert len(merged["periods"]) == 2

    def test_un_consensus_payant_vide_ne_change_rien(self):
        assert _merge_premium(FREE, []) == FREE

    def test_sans_exercice_de_reference_rien_n_est_fusionne(self):
        """Sans ancrage fiable, mieux vaut le consensus gratuit seul."""
        free = {**FREE, "fiscal_year_end": None}
        assert _merge_premium(free, [{"year": 2026, "ebitda": 400.0}]) == free


class TestTableauAvecConsensusElargi:
    """Le tableau ne fait aucune différence entre gratuit et payant."""

    ELARGI = {
        **CONSENSUS,
        "fiscal_year_end": "2025-12-31",
        "periods": [
            {**CONSENSUS["periods"][0], "ebitda": 400.0, "net_debt": 350.0},
            {**CONSENSUS["periods"][1], "ebitda": 450.0, "net_debt": 300.0},
        ],
    }

    def test_l_ebitda_estime_remplit_sa_ligne(self):
        result = tables.build(STATEMENTS, CLOSES, self.ELARGI, last_price=30.0)
        values = row_of(result["income_rows"], "ebitda")["values"]
        assert values[3] == pytest.approx(400.0)
        assert values[4] == pytest.approx(450.0)

    def test_le_multiple_d_ebitda_estime_suit(self):
        result = tables.build(STATEMENTS, CLOSES, self.ELARGI, last_price=30.0)
        values = row_of(result["valuation_rows"], "ev_to_ebitda")["values"]
        # 30 € × 50 titres + 350 de dette nette estimée, sur 400 d'EBITDA.
        assert values[3] == pytest.approx((1500.0 + 350.0) / 400.0)

    def test_la_marge_estimee_se_calcule(self):
        result = tables.build(STATEMENTS, CLOSES, self.ELARGI, last_price=30.0)
        values = row_of(result["income_rows"], "ebitda_margin")["values"]
        assert values[3] == pytest.approx(400.0 / 1200.0)

    def test_la_dette_nette_estimee_remplace_le_report(self):
        result = tables.build(STATEMENTS, CLOSES, self.ELARGI, last_price=30.0)
        assert not any("dernière dette nette publiée" in n for n in result["notes"])


class TestDividendeAnnonce:
    """Le montant indicatif ne vaut que pour le premier exercice estimé."""

    ANNONCE = {**CONSENSUS, "dividend_rate": 2.0}

    def test_il_remplit_le_premier_exercice_estime(self):
        result = tables.build(STATEMENTS, CLOSES, self.ANNONCE, last_price=30.0)
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[3] == pytest.approx(2.0)

    def test_les_exercices_suivants_restent_vides(self):
        """Le reconduire afficherait une stabilité que personne n'a prévue."""
        result = tables.build(STATEMENTS, CLOSES, self.ANNONCE, last_price=30.0)
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[4] is None

    def test_le_rendement_estime_en_decoule(self):
        result = tables.build(STATEMENTS, CLOSES, self.ANNONCE, last_price=30.0)
        values = row_of(result["valuation_rows"], "dividend_yield")["values"]
        assert values[3] == pytest.approx(2.0 / 30.0, abs=1e-6)

    def test_l_origine_du_montant_est_signalee(self):
        result = tables.build(STATEMENTS, CLOSES, self.ANNONCE, last_price=30.0)
        assert any("montant indicatif" in n for n in result["notes"])

    def test_un_consensus_par_exercice_prime(self):
        """Une vraie estimation payante ne doit pas être écrasée."""
        consensus = {
            **self.ANNONCE,
            "periods": [
                {**CONSENSUS["periods"][0], "dividend": 2.5},
                CONSENSUS["periods"][1],
            ],
        }
        result = tables.build(STATEMENTS, CLOSES, consensus, last_price=30.0)
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[3] == pytest.approx(2.5)

    def test_sans_dividende_annonce_la_ligne_reste_vide(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[3] is None
