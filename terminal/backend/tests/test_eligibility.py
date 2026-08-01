"""Tests d'éligibilité PEA.

Le critère est le pays du **siège social**, jamais la place de cotation : ces
tests verrouillent précisément les cas où les deux divergent.
"""

from app.pea.eligibility import Eligibility, assess, normalize_country


class TestNormalizeCountry:
    def test_libelles_anglais(self):
        assert normalize_country("France") == "FR"
        assert normalize_country("Netherlands") == "NL"
        assert normalize_country("Germany") == "DE"

    def test_libelles_francais(self):
        assert normalize_country("Pays-Bas") == "NL"
        assert normalize_country("Allemagne") == "DE"

    def test_insensible_a_la_casse(self):
        assert normalize_country("  NETHERLANDS  ") == "NL"

    def test_code_iso_deja_normalise(self):
        assert normalize_country("nl") == "NL"

    def test_valeur_absente(self):
        assert normalize_country(None) is None
        assert normalize_country("") is None
        assert normalize_country("   ") is None

    def test_libelle_inconnu(self):
        assert normalize_country("Wakanda") is None


class TestEligibilite:
    def test_societe_francaise(self):
        result = assess("OR.PA", "France")
        assert result.status is Eligibility.ELIGIBLE
        assert result.country_iso == "FR"

    def test_siege_hors_place_de_cotation(self):
        """Airbus est cotée à Paris mais de droit néerlandais : éligible."""
        result = assess("AIR.PA", "Netherlands")
        assert result.status is Eligibility.ELIGIBLE
        assert result.country_iso == "NL"

    def test_suisse_non_eligible(self):
        """La Suisse est AELE mais pas EEE."""
        result = assess("NESN.SW", "Switzerland")
        assert result.status is Eligibility.NON_ELIGIBLE
        assert result.country_iso == "CH"

    def test_royaume_uni_non_eligible(self):
        """Sorti de l'EEE avec le Brexit."""
        assert assess("SHEL.L", "United Kingdom").status is Eligibility.NON_ELIGIBLE

    def test_etats_unis_non_eligible(self):
        assert assess("AAPL", "United States").status is Eligibility.NON_ELIGIBLE

    def test_norvege_eligible(self):
        """Hors UE mais membre de l'EEE."""
        assert assess("EQNR.OL", "Norway").status is Eligibility.ELIGIBLE

    def test_islande_et_liechtenstein_eligibles(self):
        assert assess("X.IC", "Iceland").status is Eligibility.ELIGIBLE
        assert assess("Y.SW", "Liechtenstein").status is Eligibility.ELIGIBLE

    def test_pays_inconnu_ne_presume_rien(self):
        """Sans pays, on ne conclut pas — surtout pas à l'éligibilité."""
        result = assess("XYZ.PA", None)
        assert result.status is Eligibility.UNKNOWN
        assert not result.is_eligible

    def test_pays_non_reconnu_reste_indetermine(self):
        assert assess("XYZ.PA", "Ruritanie").status is Eligibility.UNKNOWN


class TestExceptions:
    def test_override_corrige_un_faux_negatif(self):
        """IAG est de droit espagnol, le provider annonce le Royaume-Uni."""
        result = assess("IAG.MC", "United Kingdom")
        assert result.status is Eligibility.ELIGIBLE
        assert result.country_iso == "ES"

    def test_override_corrige_un_faux_positif(self):
        """DSM-Firmenich est cotée à Amsterdam mais de droit suisse."""
        result = assess("DSFIR.AS", "Netherlands")
        assert result.status is Eligibility.NON_ELIGIBLE
        assert result.country_iso == "CH"

    def test_override_comble_un_pays_manquant(self):
        result = assess("ML.PA", None)
        assert result.status is Eligibility.ELIGIBLE
        assert result.country_iso == "FR"

    def test_override_insensible_a_la_casse_du_symbole(self):
        assert assess("iag.mc", "United Kingdom").status is Eligibility.ELIGIBLE

    def test_la_raison_est_toujours_renseignee(self):
        for symbol, country in [("OR.PA", "France"), ("AAPL", "United States"), ("X", None)]:
            assert assess(symbol, country).reason
