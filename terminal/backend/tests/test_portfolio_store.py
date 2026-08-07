"""Tests du magasin de positions et de l'import CSV.

L'import doit avaler des exports de courtiers français : séparateur
point-virgule, virgule décimale, espaces de milliers, intitulés variables.
Une ligne mal lue fausserait silencieusement tout le portefeuille.
"""

import datetime as dt

import pytest

from app.portfolio.dividends import accrued
from app.portfolio.store import Position, parse_csv
from app.portfolio.targets import compare, total


class TestLecturaDesNombres:
    def test_format_francais_avec_espaces_et_virgule(self):
        positions, _ = parse_csv(
            'symbol;quantity;buyingPrice\nWPEA.PA;"24 750,00";7,42\n'
        )
        assert positions[0].quantity == pytest.approx(24750.0)
        assert positions[0].average_cost == pytest.approx(7.42)

    def test_format_anglais(self):
        positions, _ = parse_csv("symbol,quantity,average_cost\nAAPL,1500.50,12.75\n")
        assert positions[0].quantity == pytest.approx(1500.50)
        assert positions[0].average_cost == pytest.approx(12.75)

    def test_separateur_de_milliers_anglais(self):
        positions, _ = parse_csv('symbol,quantity,average_cost\nX,"1,500",10\n')
        assert positions[0].quantity == pytest.approx(1500.0)


class TestImportCsv:
    def test_intitules_alternatifs(self):
        """Les exports de courtiers ne nomment pas les colonnes pareil."""
        positions, _ = parse_csv("Symbole;Quantite;PRU;Devise\nSAN.PA;110;81,51;EUR\n")
        assert positions[0].symbol == "SAN.PA"
        assert positions[0].quantity == 110
        assert positions[0].average_cost == pytest.approx(81.51)
        assert positions[0].currency == "EUR"

    def test_detection_du_separateur(self):
        for text in ("symbol;quantity\nA;1\n", "symbol,quantity\nA,1\n"):
            positions, _ = parse_csv(text)
            assert positions and positions[0].symbol == "A"

    def test_le_symbole_est_normalise(self):
        positions, _ = parse_csv("symbol;quantity\n mc.pa ;10\n")
        assert positions[0].symbol == "MC.PA"

    def test_colonnes_obligatoires_manquantes(self):
        positions, warnings = parse_csv("nom;prix\nSanofi;81\n")
        assert positions == []
        assert any("obligatoires" in w for w in warnings)

    def test_ligne_incomplete_signalee_et_non_avalee(self):
        """Une ligne ignorée en silence fausserait le portefeuille."""
        positions, warnings = parse_csv("symbol;quantity\nA;10\n;5\nB;\n")
        assert [p.symbol for p in positions] == ["A"]
        assert len(warnings) == 2

    def test_date_d_entree_reprise(self):
        positions, _ = parse_csv(
            "symbol;quantity;date\nMC.PA;10;2024-03-15T00:00:00\n"
        )
        assert positions[0].opened_at == "2024-03-15"

    def test_fichier_vide(self):
        assert parse_csv("")[0] == []

    def test_bom_en_tete_de_fichier(self):
        """Excel préfixe volontiers ses exports d'un BOM."""
        positions, _ = parse_csv("﻿symbol;quantity\nA;10\n")
        assert positions and positions[0].symbol == "A"


class TestPosition:
    def test_prix_de_revient(self):
        assert Position("A", 10, 5.5).cost_basis == pytest.approx(55.0)


class TestDividendesPercus:
    ROWS = [
        {"ex_dividend_date": "2023-05-10", "amount": 2.0},
        {"ex_dividend_date": "2024-05-10", "amount": 2.5},
        {"ex_dividend_date": "2025-05-10", "amount": 3.0},
    ]

    def test_seuls_les_detachements_posterieurs_comptent(self):
        """Compter tout l'historique créditerait des dividendes versés à
        d'autres porteurs avant l'achat."""
        result = accrued(self.ROWS, dt.date(2024, 1, 1), quantity=100)
        assert result["per_share"] == pytest.approx(5.5)
        assert result["amount"] == pytest.approx(550.0)
        assert result["payments"] == 2

    def test_entree_anterieure_a_tout_l_historique(self):
        result = accrued(self.ROWS, dt.date(2020, 1, 1), quantity=10)
        assert result["payments"] == 3
        assert result["per_share"] == pytest.approx(7.5)

    def test_entree_posterieure_a_tout(self):
        result = accrued(self.ROWS, dt.date(2026, 1, 1), quantity=10)
        assert result["payments"] == 0
        assert result["amount"] == 0

    def test_sans_date_d_entree_on_ne_compte_rien(self):
        """Mieux vaut aucun chiffre qu'un cumul faux."""
        assert accrued(self.ROWS, None, quantity=10)["amount"] is None

    def test_dernier_detachement_rapporte(self):
        result = accrued(self.ROWS, dt.date(2020, 1, 1), quantity=1)
        assert result["last"] == "2025-05-10"


class TestComparaisonAuxCibles:
    SLICES = [
        {"label": "Technology", "share": 0.40, "value": 4000.0},
        {"label": "Healthcare", "share": 0.10, "value": 1000.0},
    ]

    def test_ecart_calcule(self):
        rows = compare(self.SLICES, {"Technology": 0.25, "Healthcare": 0.15})
        tech = next(r for r in rows if r["label"] == "Technology")
        assert tech["gap"] == pytest.approx(0.15)

    def test_une_cible_non_pourvue_apparait_quand_meme(self):
        """C'est précisément ce qu'on cherche à voir."""
        rows = compare(self.SLICES, {"Energy": 0.10})
        energy = next(r for r in rows if r["label"] == "Energy")
        assert energy["share"] == 0.0
        assert energy["gap"] == pytest.approx(-0.10)

    def test_une_exposition_sans_cible_apparait_aussi(self):
        rows = compare(self.SLICES, {})
        assert {r["label"] for r in rows} == {"Technology", "Healthcare"}
        assert all(r["gap"] is None for r in rows)

    def test_les_plus_gros_ecarts_en_tete(self):
        rows = compare(self.SLICES, {"Technology": 0.38, "Healthcare": 0.30})
        assert rows[0]["label"] == "Healthcare"

    def test_somme_des_cibles(self):
        assert total({"A": 0.3, "B": 0.7}) == pytest.approx(1.0)


class TestResolutionDesIsin:
    """Les relevés de courtiers désignent les titres par ISIN.

    Enregistrés tels quels, ils donneraient un portefeuille sans cotation :
    la résolution en ticker est ce qui rend l'export brut exploitable.
    """

    @staticmethod
    def _resolve(positions, mapping):
        """Exécute la résolution en court-circuitant le réseau."""
        import asyncio

        from app.providers import yahoo_search
        from app.routers import portfolio as router

        async def fake(isin):
            return mapping.get(isin)

        original = yahoo_search.resolve_isin
        yahoo_search.resolve_isin = fake
        try:
            return asyncio.run(router._resolve_isins(positions))
        finally:
            yahoo_search.resolve_isin = original

    def test_isin_remplace_par_le_ticker(self):
        positions = [Position(symbol="FR0000121014", quantity=10, average_cost=500.0)]
        resolved, unresolved = self._resolve(positions, {"FR0000121014": "MC.PA"})
        assert resolved[0].symbol == "MC.PA"
        assert unresolved == []

    def test_l_isin_devient_le_libelle_pour_rester_tracable(self):
        positions = [Position(symbol="FR0000121014", quantity=10, average_cost=500.0)]
        resolved, _ = self._resolve(positions, {"FR0000121014": "MC.PA"})
        assert resolved[0].label == "FR0000121014"

    def test_un_libelle_existant_n_est_pas_ecrase(self):
        positions = [
            Position(symbol="FR0000121014", quantity=10, average_cost=500.0, label="LVMH")
        ]
        resolved, _ = self._resolve(positions, {"FR0000121014": "MC.PA"})
        assert resolved[0].label == "LVMH"

    def test_un_ticker_n_est_pas_touche(self):
        positions = [Position(symbol="SAN.PA", quantity=10, average_cost=80.0)]
        resolved, unresolved = self._resolve(positions, {})
        assert resolved[0].symbol == "SAN.PA"
        assert unresolved == []

    def test_isin_introuvable_signale_et_conserve(self):
        """Perdre la ligne serait pire que la garder inexploitable."""
        positions = [Position(symbol="XX0000000000", quantity=10, average_cost=1.0)]
        resolved, unresolved = self._resolve(positions, {})
        assert resolved[0].symbol == "XX0000000000"
        assert unresolved == ["XX0000000000"]

    def test_l_ordre_des_positions_est_conserve(self):
        positions = [
            Position(symbol="FR0000121014", quantity=1, average_cost=1.0),
            Position(symbol="SAN.PA", quantity=2, average_cost=2.0),
            Position(symbol="NL0000235190", quantity=3, average_cost=3.0),
        ]
        resolved, _ = self._resolve(
            positions, {"FR0000121014": "MC.PA", "NL0000235190": "AIR.PA"}
        )
        assert [p.symbol for p in resolved] == ["MC.PA", "SAN.PA", "AIR.PA"]
