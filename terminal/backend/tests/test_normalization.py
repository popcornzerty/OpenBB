"""Tests des normalisations de données.

Le fournisseur mélange les échelles dans une même réponse et exprime les
capitalisations en devise de cotation. Les deux produisent des chiffres faux à
l'écran si on les laisse passer : ces tests verrouillent les corrections.
"""

import pytest

from app.pea.eligibility import country_label
from app.providers.ecb_fx import to_eur
from app.providers.obb_source import _normalize_metrics


class TestEchelleDesRatios:
    def test_le_rendement_passe_en_fraction(self):
        """2,74 chez le fournisseur signifie 2,74 % — donc 0,0274."""
        assert _normalize_metrics({"dividend_yield": 2.74})["dividend_yield"] == pytest.approx(0.0274)

    def test_l_endettement_passe_en_fraction(self):
        assert _normalize_metrics({"debt_to_equity": 53.306})["debt_to_equity"] == pytest.approx(0.53306)

    def test_les_ratios_deja_en_fraction_sont_intacts(self):
        source = {
            "return_on_equity": 0.16586,
            "profit_margin": 0.13658,
            "payout_ratio": 0.5925,
            "dividend_yield_5y_avg": 0.0183,
            "price_to_book": 3.44,
            "pe_ratio": 21.6,
        }
        assert _normalize_metrics(dict(source)) == source

    def test_les_valeurs_absentes_ne_cassent_rien(self):
        assert _normalize_metrics({"dividend_yield": None})["dividend_yield"] is None
        assert _normalize_metrics({})== {}

    def test_une_valeur_non_numerique_est_laissee_telle_quelle(self):
        assert _normalize_metrics({"debt_to_equity": "n.d."})["debt_to_equity"] == "n.d."


class TestConversionEnEuros:
    @pytest.mark.asyncio
    async def test_l_euro_reste_inchange(self):
        assert await to_eur(1000.0, "EUR") == 1000.0

    @pytest.mark.asyncio
    async def test_devise_absente_traitee_comme_euro(self):
        assert await to_eur(1000.0, None) == 1000.0

    @pytest.mark.asyncio
    async def test_montant_absent(self):
        assert await to_eur(None, "DKK") is None

    @pytest.mark.asyncio
    async def test_une_couronne_danoise_vaut_moins_qu_un_euro(self):
        """Novo Nordisk pesait 1 355 Md DKK, soit environ 180 Md € : sans
        conversion, elle passait devant ASML au classement."""
        converted = await to_eur(1_355_000_000_000.0, "DKK")
        assert converted is not None
        assert 150e9 < converted < 220e9

    @pytest.mark.asyncio
    async def test_devise_inconnue_renvoie_rien_plutot_qu_un_faux_montant(self):
        assert await to_eur(1000.0, "XYZ") is None


class TestLibellesDePays:
    def test_pays_de_l_eee(self):
        assert country_label("FR") == "France"
        assert country_label("NL") == "Pays-Bas"
        assert country_label("NO") == "Norvège"

    def test_pays_hors_eee_traduits(self):
        """Sans cela, « Switzerland » s'affichait au milieu d'une liste française."""
        assert country_label("CH") == "Suisse"
        assert country_label("GB") == "Royaume-Uni"
        assert country_label("US") == "États-Unis"

    def test_code_inconnu_retombe_sur_le_repli(self):
        assert country_label("ZZ", "Ruritanie") == "Ruritanie"
        assert country_label("ZZ") == "ZZ"

    def test_sans_code_on_renvoie_le_repli(self):
        assert country_label(None, "quelque part") == "quelque part"
        assert country_label(None) is None
