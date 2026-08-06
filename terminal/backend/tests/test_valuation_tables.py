"""Tests des tableaux par exercice et de l'évolution des multiples.

Un tableau de valorisation faux est pire qu'absent : il se lit comme un fait.
Les cas verrouillés ici sont ceux où une valeur plausible mais fausse
pourrait passer inaperçue — multiple calculé au mauvais cours, colonne
estimée décalée d'un an, dénominateur négatif produisant un « PER » négatif.
"""

import datetime as dt

import pandas as pd
import pytest

from app.valuation import multiples_history, tables
from app.valuation.series import FundamentalPoint


def income(year: int, revenue=1000.0, eps=2.0, **extra) -> dict:
    base = {
        "period_ending": f"{year}-12-31",
        "total_revenue": revenue,
        "ebitda": 300.0,
        "ebit": 200.0,
        "net_income": 100.0,
        "diluted_earnings_per_share": eps,
        "weighted_average_diluted_shares_outstanding": 50.0,
    }
    base.update(extra)
    return base


def balance(year: int, **extra) -> dict:
    base = {
        "period_ending": f"{year}-12-31",
        "ordinary_shares_number": 50.0,
        "net_debt": 400.0,
        "common_stock_equity": 800.0,
    }
    base.update(extra)
    return base


def cash(year: int, **extra) -> dict:
    base = {
        "period_ending": f"{year}-12-31",
        "free_cash_flow": 150.0,
        "cash_dividends_paid": -50.0,
    }
    base.update(extra)
    return base


def history(prices: dict[str, float]) -> list[dict]:
    return [{"date": day, "close": value} for day, value in prices.items()]


CLOSES = history(
    {
        "2023-12-29": 40.0,
        "2024-12-31": 60.0,
        "2025-12-31": 50.0,
        "2026-08-03": 30.0,
    }
)

STATEMENTS = {
    "income": [income(2025), income(2024), income(2023)],
    "balance": [balance(2025), balance(2024), balance(2023)],
    "cash": [cash(2025), cash(2024), cash(2023)],
}

CONSENSUS = {
    "periods": [
        {"offset": 0, "eps": 3.0, "revenue": 1200.0, "analysts": 8,
         "thin": False, "year_ago_eps": 2.0},
        {"offset": 1, "eps": 3.5, "revenue": 1300.0, "analysts": 8,
         "thin": False, "year_ago_eps": 3.0},
    ],
    "price_target": {"mean": 45.0},
}


def row_of(rows: list[dict], key: str) -> dict:
    return next(r for r in rows if r["key"] == key)


class TestColonnes:
    def test_exercices_du_plus_ancien_au_plus_recent(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        assert [c["label"] for c in result["columns"]] == [
            "2023", "2024", "2025", "2026e", "2027e"
        ]

    def test_un_exercice_sans_aucun_compte_est_ecarte(self):
        """Yahoo renvoie un cinquième exercice réduit à sa date de clôture."""
        statements = {
            **STATEMENTS,
            "income": [*STATEMENTS["income"], {"period_ending": "2022-12-31"}],
        }
        result = tables.build(statements, CLOSES, CONSENSUS, last_price=30.0)
        assert "2022" not in [c["label"] for c in result["columns"]]

    def test_les_colonnes_publiees_portent_le_cours_de_cloture(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        prices = {c["label"]: c["price"] for c in result["columns"]}
        assert prices["2024"] == 60.0
        assert prices["2025"] == 50.0

    def test_les_colonnes_estimees_portent_le_cours_actuel(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        prices = {c["label"]: c["price"] for c in result["columns"]}
        assert prices["2026e"] == 30.0
        assert prices["2027e"] == 30.0

    def test_exercice_anterieur_a_l_historique_de_cours(self):
        """Sans cours de référence, pas de multiple plutôt qu'un multiple faux."""
        result = tables.build(
            STATEMENTS, history({"2025-12-31": 50.0}), CONSENSUS, last_price=30.0
        )
        prices = {c["label"]: c["price"] for c in result["columns"]}
        assert prices["2023"] is None


class TestRaccordementDuConsensus:
    def test_les_estimations_suivent_le_dernier_exercice_publie(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        estimated = [c for c in result["columns"] if c["estimate"]]
        assert [c["year"] for c in estimated] == [2026, 2027]

    def test_un_exercice_source_decale_ecarte_les_estimations(self):
        """Un exercice de référence trop ancien rendrait les colonnes fausses."""
        consensus = {
            **CONSENSUS,
            "fiscal_year_end": "2021-12-31",  # comptes publiés jusqu'en 2025
        }
        result = tables.build(STATEMENTS, CLOSES, consensus, last_price=30.0)
        assert not any(c["estimate"] for c in result["columns"])
        assert any("ne correspond pas aux comptes publiés" in n for n in result["notes"])

    def test_l_exercice_source_prime_sur_le_dernier_publie(self):
        consensus = {**CONSENSUS, "fiscal_year_end": "2025-12-31"}
        result = tables.build(STATEMENTS, CLOSES, consensus, last_price=30.0)
        estimated = [c["year"] for c in result["columns"] if c["estimate"]]
        assert estimated == [2026, 2027]

    def test_un_benefice_ajuste_divergent_est_signale_sans_masquer(self):
        """Le consensus raisonne en résultat ajusté : l'écart n'invalide rien."""
        consensus = {
            "periods": [
                {"offset": 0, "eps": 3.0, "revenue": 1200.0, "analysts": 8,
                 "thin": False, "year_ago_eps": 9.9},
            ],
            "price_target": {},
        }
        result = tables.build(STATEMENTS, CLOSES, consensus, last_price=30.0)
        assert any(c["estimate"] for c in result["columns"])
        assert any("résultat ajusté" in note for note in result["notes"])

    def test_absence_de_consensus_laisse_l_historique(self):
        result = tables.build(
            STATEMENTS, CLOSES, {"periods": [], "price_target": {}}, last_price=30.0
        )
        assert [c["label"] for c in result["columns"]] == ["2023", "2024", "2025"]

    def test_couverture_etroite_signalee(self):
        consensus = {
            "periods": [
                {"offset": 0, "eps": 3.0, "revenue": 1200.0, "analysts": 2,
                 "thin": True, "year_ago_eps": 2.0},
            ],
            "price_target": {},
        }
        result = tables.build(STATEMENTS, CLOSES, consensus, last_price=30.0)
        assert any("moins de trois bureaux" in note for note in result["notes"])


class TestCompteDeResultat:
    def test_croissance_du_chiffre_d_affaires(self):
        statements = {
            **STATEMENTS,
            "income": [income(2025, revenue=1100.0), income(2024, revenue=1000.0),
                       income(2023, revenue=900.0)],
        }
        result = tables.build(statements, CLOSES, CONSENSUS, last_price=30.0)
        growth = row_of(result["income_rows"], "revenue_growth")["values"]
        assert growth[0] is None  # aucun exercice antérieur
        # Les valeurs transmises sont arrondies au millionième.
        assert growth[1] == pytest.approx(1000 / 900 - 1, abs=1e-6)
        assert growth[2] == pytest.approx(0.10)

    def test_une_marge_negative_reste_affichee(self):
        """Une perte est une information, pas une valeur à écarter."""
        statements = {
            **STATEMENTS,
            "income": [income(2025, net_income=-200.0), income(2024), income(2023)],
        }
        result = tables.build(statements, CLOSES, CONSENSUS, last_price=30.0)
        margins = row_of(result["income_rows"], "net_margin")["values"]
        assert margins[2] == pytest.approx(-0.20)

    def test_dividende_par_action_depuis_les_decaissements(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        dividends = row_of(result["income_rows"], "dividend_ps")["values"]
        assert dividends[0] == pytest.approx(1.0)  # 50 versés / 50 titres

    def test_le_resultat_net_estime_est_reconstitue(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        net = row_of(result["income_rows"], "net_income")["values"]
        assert net[3] == pytest.approx(3.0 * 50.0)

    def test_ni_ebitda_ni_dividende_estimes(self):
        """Le consensus gratuit ne couvre que le CA et le BNPA."""
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        assert row_of(result["income_rows"], "ebitda")["values"][3] is None
        assert row_of(result["income_rows"], "dividend_ps")["values"][3] is None


class TestValorisation:
    def test_per_au_cours_de_cloture(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        per = row_of(result["valuation_rows"], "per")["values"]
        assert per[1] == pytest.approx(30.0)  # 60 / 2
        assert per[2] == pytest.approx(25.0)  # 50 / 2

    def test_per_estime_au_cours_actuel(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        per = row_of(result["valuation_rows"], "per")["values"]
        assert per[3] == pytest.approx(10.0)  # 30 / 3

    def test_capitalisation_et_valeur_d_entreprise(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        cap = row_of(result["valuation_rows"], "market_cap")["values"]
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        assert cap[2] == pytest.approx(50.0 * 50.0)
        assert ev[2] == pytest.approx(2500.0 + 400.0)

    def test_un_benefice_negatif_ne_donne_pas_de_per(self):
        statements = {
            **STATEMENTS,
            "income": [income(2025, eps=-1.0), income(2024), income(2023)],
        }
        result = tables.build(statements, CLOSES, CONSENSUS, last_price=30.0)
        assert row_of(result["valuation_rows"], "per")["values"][2] is None

    def test_un_multiple_absurde_est_ecarte(self):
        statements = {
            **STATEMENTS,
            "income": [income(2025, eps=0.001), income(2024), income(2023)],
        }
        result = tables.build(statements, CLOSES, CONSENSUS, last_price=30.0)
        assert row_of(result["valuation_rows"], "per")["values"][2] is None

    def test_la_dette_nette_estimee_est_reprise_et_signalee(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        assert ev[3] == pytest.approx(30.0 * 50.0 + 400.0)
        assert any("dernière dette nette publiée" in n for n in result["notes"])

    def test_rendement_et_flux_disponible(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        assert row_of(result["valuation_rows"], "dividend_yield")["values"][2] == pytest.approx(
            1.0 / 50.0
        )
        assert row_of(result["valuation_rows"], "fcf_yield")["values"][2] == pytest.approx(
            150.0 / 2500.0
        )

    def test_aucun_etat_financier(self):
        result = tables.build({"income": []}, CLOSES, CONSENSUS, last_price=30.0)
        assert result["columns"] == []


def points_from(year_of_first: int, count: int, eps: float) -> list[FundamentalPoint]:
    return [
        FundamentalPoint(
            available_from=dt.date(year_of_first + i, 3, 31),
            period_ending=dt.date(year_of_first + i - 1, 12, 31),
            values={"earnings": eps, "sales": 10.0, "book_value": 5.0, "cash_flow": 3.0},
        )
        for i in range(count)
    ]


def daily_history(start: str, days: int, price: float) -> list[dict]:
    index = pd.date_range(start, periods=days, freq="D")
    return [{"date": d.date().isoformat(), "close": price} for d in index]


class TestEvolutionDuMultiple:
    def test_moyenne_et_ecart(self):
        result = multiples_history.compute(
            daily_history("2022-01-01", 1200, 20.0), points_from(2022, 4, 2.0)
        )
        assert result["current"] == pytest.approx(10.0)
        assert result["average"] == pytest.approx(10.0)
        assert result["gap_to_average"] == pytest.approx(0.0)

    def test_serie_trop_courte(self):
        assert (
            multiples_history.compute(
                daily_history("2026-01-01", 30, 20.0), points_from(2022, 1, 2.0)
            )
            is None
        )

    def test_la_fenetre_est_bornee(self):
        result = multiples_history.compute(
            daily_history("2018-01-01", 3000, 20.0),
            points_from(2018, 8, 2.0),
            window_years=5,
        )
        assert result["years"] <= 5.05

    def test_la_moyenne_ignore_la_periode_reportee_en_amont(self):
        """Comparer à une référence en partie fabriquée n'aurait aucun sens."""
        history_rows = daily_history("2022-01-01", 1500, 20.0)
        points = points_from(2023, 3, 2.0)  # premier point publié en 2023-03-31
        result = multiples_history.compute(history_rows, points)
        assert result["reference_from"] > result["from"]
        assert result["stats_backfilled"] is False

    def test_composante_inconnue(self):
        with pytest.raises(ValueError):
            multiples_history.compute(
                daily_history("2022-01-01", 600, 20.0), points_from(2022, 3, 2.0), "inconnue"
            )


class TestInteretsMinoritaires:
    """La valeur d'entreprise mesure l'ensemble consolidé.

    Le compte de résultat et le tableau de flux rendent compte de la totalité
    du groupe ; la capitalisation, elle, ne couvre que la maison mère. Omettre
    les minoritaires sous-estimait la valeur d'entreprise de Deutsche Telekom
    de 30 Md€, et donc tous ses multiples de VE.
    """

    STATEMENTS = {
        **STATEMENTS,
        "balance": [
            balance(2025, minority_interest=300.0),
            balance(2024, minority_interest=280.0),
            balance(2023, minority_interest=260.0),
        ],
    }

    def test_la_valeur_d_entreprise_les_inclut(self):
        result = tables.build(self.STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        # 50 € × 50 titres + 400 de dette nette + 300 de minoritaires
        assert ev[2] == pytest.approx(2500.0 + 400.0 + 300.0)

    def test_sans_minoritaires_la_valeur_est_inchangee(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        assert ev[2] == pytest.approx(2500.0 + 400.0)

    def test_les_colonnes_estimees_prolongent_les_minoritaires(self):
        result = tables.build(self.STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        assert ev[3] == pytest.approx(30.0 * 50.0 + 400.0 + 300.0)

    def test_le_biais_de_perimetre_est_signale(self):
        result = tables.build(self.STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        assert any("intérêts minoritaires significatifs" in n for n in result["notes"])

    def test_aucun_signalement_sans_minoritaires(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        assert not any("minoritaires significatifs" in n for n in result["notes"])


class TestDeuxRendementsDuFlux:
    def test_rapporte_a_la_capitalisation(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        values = row_of(result["valuation_rows"], "fcf_yield")["values"]
        assert values[2] == pytest.approx(150.0 / 2500.0)

    def test_rapporte_a_la_valeur_d_entreprise(self):
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        values = row_of(result["valuation_rows"], "fcf_yield_ev")["values"]
        assert values[2] == pytest.approx(150.0 / 2900.0, abs=1e-6)

    def test_le_rendement_sur_ve_est_toujours_le_plus_bas_si_endette(self):
        """Une dette nette positive ne peut qu'abaisser le rendement."""
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        cap = row_of(result["valuation_rows"], "fcf_yield")["values"]
        ev = row_of(result["valuation_rows"], "fcf_yield_ev")["values"]
        for a, b in zip(cap, ev):
            if a is not None and b is not None:
                assert b <= a


class TestMaterialiteDesMinoritaires:
    """Presque toute société consolidante porte des minoritaires.

    LVMH en a pour 0,4 % de sa capitalisation, ce qui ne change rien à la
    lecture de ses ratios ; Deutsche Telekom en porte 22 %. Signaler les deux
    reviendrait à ne rien signaler.
    """

    def _with(self, amount: float) -> dict:
        return {
            **STATEMENTS,
            "balance": [
                balance(2025, minority_interest=amount),
                balance(2024, minority_interest=amount),
                balance(2023, minority_interest=amount),
            ],
        }

    def test_minoritaires_negligeables_non_signales(self):
        # 10 pour une capitalisation de 2 500, soit 0,4 %.
        result = tables.build(self._with(10.0), CLOSES, CONSENSUS, last_price=30.0)
        assert not any("minoritaires significatifs" in n for n in result["notes"])

    def test_minoritaires_significatifs_signales(self):
        # 500 pour 2 500, soit 20 %.
        result = tables.build(self._with(500.0), CLOSES, CONSENSUS, last_price=30.0)
        assert any("minoritaires significatifs" in n for n in result["notes"])

    def test_ils_entrent_dans_la_valeur_d_entreprise_meme_negligeables(self):
        """Le seuil ne porte que sur l'avertissement, pas sur le calcul."""
        result = tables.build(self._with(10.0), CLOSES, CONSENSUS, last_price=30.0)
        ev = row_of(result["valuation_rows"], "enterprise_value")["values"]
        assert ev[2] == pytest.approx(2500.0 + 400.0 + 10.0)

    def test_le_poids_se_juge_sur_un_exercice_publie(self):
        """Une colonne estimée porte le cours du jour, pas une capitalisation
        constatée : fonder le seuil dessus le rendrait dépendant du marché."""
        result = tables.build(self._with(500.0), CLOSES, CONSENSUS, last_price=1.0)
        assert any("minoritaires significatifs" in n for n in result["notes"])


class TestDividendeDetache:
    """Les détachements réels priment sur les décaissements du groupe.

    Le tableau de flux consolidé de Deutsche Telekom inclut ce que T-Mobile US
    verse à ses propres minoritaires : 1,33 € par action en 2025 pour un
    dividende réel de 0,90 €. Rapprochée du montant annoncé pour l'exercice
    suivant, cette base gonflée faisait apparaître une coupe inexistante.
    """

    DETACHEMENTS = [
        {"ex_dividend_date": "2025-04-10", "amount": 0.90},
        {"ex_dividend_date": "2024-04-11", "amount": 0.77},
        {"ex_dividend_date": "2023-04-06", "amount": 0.70},
    ]

    def test_les_detachements_de_l_exercice_sont_sommes(self):
        result = tables.build(
            STATEMENTS, CLOSES, CONSENSUS, last_price=30.0, dividends=self.DETACHEMENTS
        )
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[2] == pytest.approx(0.90)  # exercice 2025
        assert values[1] == pytest.approx(0.77)  # exercice 2024

    def test_plusieurs_acomptes_dans_l_exercice(self):
        rows = [
            {"ex_dividend_date": "2025-03-15", "amount": 0.30},
            {"ex_dividend_date": "2025-09-15", "amount": 0.30},
            {"ex_dividend_date": "2025-12-15", "amount": 0.30},
        ]
        result = tables.build(
            STATEMENTS, CLOSES, CONSENSUS, last_price=30.0, dividends=rows
        )
        assert row_of(result["income_rows"], "dividend_ps")["values"][2] == pytest.approx(0.90)

    def test_un_exercice_decale_retient_la_bonne_fenetre(self):
        """Alstom clôture en mars : l'exercice ne suit pas l'année civile."""
        statements = {
            "income": [income(2026) | {"period_ending": "2026-03-31"}],
            "balance": [balance(2026) | {"period_ending": "2026-03-31"}],
            "cash": [cash(2026) | {"period_ending": "2026-03-31"}],
        }
        rows = [
            {"ex_dividend_date": "2025-07-10", "amount": 0.08},  # dans l'exercice
            {"ex_dividend_date": "2026-07-10", "amount": 0.12},  # exercice suivant
        ]
        result = tables.build(
            statements, CLOSES, {"periods": [], "price_target": {}},
            last_price=30.0, dividends=rows,
        )
        assert row_of(result["income_rows"], "dividend_ps")["values"][0] == pytest.approx(0.08)

    def test_sans_historique_les_decaissements_prennent_le_relais(self):
        """Une ligne biaisée vaut mieux qu'une ligne vide."""
        result = tables.build(STATEMENTS, CLOSES, CONSENSUS, last_price=30.0)
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        assert values[2] == pytest.approx(1.0)  # 50 versés / 50 titres

    def test_un_exercice_sans_detachement_reste_vide(self):
        rows = [{"ex_dividend_date": "2019-04-10", "amount": 0.50}]
        result = tables.build(
            STATEMENTS, CLOSES, CONSENSUS, last_price=30.0, dividends=rows
        )
        values = row_of(result["income_rows"], "dividend_ps")["values"]
        # Aucun détachement dans la fenêtre : on retombe sur les décaissements.
        assert values[2] == pytest.approx(1.0)


class TestRythmeDeDetachement:
    """Les dates de détachement glissent d'une année sur l'autre.

    TotalEnergies a connu cinq détachements en 2025 et quatre en 2023, ses
    versements trimestriels franchissant le 1er janvier. Compter par fenêtre
    calendaire faisait osciller son rendement affiché entre 4,6 % et 7,4 %
    alors qu'il n'avait pas bougé. On retient donc un nombre fixe de
    versements, déduit du rythme observé.
    """

    TTE = [
        {"ex_dividend_date": d, "amount": a}
        for d, a in [
            ("2024-01-02", 0.74), ("2024-03-20", 0.74), ("2024-06-19", 0.79),
            ("2024-09-25", 0.79), ("2025-01-02", 0.79), ("2025-03-26", 0.79),
            ("2025-06-19", 0.85), ("2025-10-01", 0.85), ("2025-12-31", 0.85),
        ]
    ]

    def test_le_rythme_trimestriel_est_reconnu(self):
        rows = tables._detachments(self.TTE)
        assert tables._payments_per_year(rows) == 4

    def test_quatre_versements_malgre_cinq_detachements_dans_l_annee(self):
        rows = tables._detachments(self.TTE)
        total = tables._dividend_per_year(rows, 4, "2025-12-31")
        # Les quatre derniers : 0,79 + 0,85 × 3.
        assert total == pytest.approx(3.34)

    def test_un_versement_annuel(self):
        rows = tables._detachments([
            {"ex_dividend_date": "2024-04-11", "amount": 0.77},
            {"ex_dividend_date": "2025-04-10", "amount": 0.90},
            {"ex_dividend_date": "2026-04-02", "amount": 1.00},
        ])
        assert tables._payments_per_year(rows) == 1
        assert tables._dividend_per_year(rows, 1, "2025-12-31") == pytest.approx(0.90)

    def test_deux_acomptes_inegaux(self):
        """LVMH verse un acompte en décembre et le solde en avril."""
        rows = tables._detachments([
            {"ex_dividend_date": "2024-12-04", "amount": 5.50},
            {"ex_dividend_date": "2025-04-24", "amount": 7.50},
            {"ex_dividend_date": "2025-12-03", "amount": 5.50},
        ])
        assert tables._payments_per_year(rows) == 2
        assert tables._dividend_per_year(rows, 2, "2025-12-31") == pytest.approx(13.00)

    def test_un_detachement_juste_apres_la_cloture_est_rattache(self):
        rows = tables._detachments([
            {"ex_dividend_date": "2025-01-06", "amount": 1.00},
        ])
        assert tables._dividend_per_year(rows, 1, "2024-12-31") == pytest.approx(1.00)

    def test_un_dividende_interrompu_ne_se_reporte_pas(self):
        """Un versement isolé et ancien n'appartient à aucun exercice récent."""
        rows = tables._detachments([{"ex_dividend_date": "2019-04-10", "amount": 0.50}])
        assert tables._dividend_per_year(rows, 1, "2025-12-31") is None
