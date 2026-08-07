"""Tests de la lecture des avis de franchissement de seuils.

Le nom du déclarant n'existe que dans le PDF : tout repose donc sur
l'extraction. Une erreur ici ne se voit pas — elle produit un nom plausible
mais faux, attribuant à Goldman Sachs un mouvement qu'il n'a pas fait. Les
formulations réellement rencontrées sont donc figées ici.

Aucun appel réseau : l'analyse porte sur du texte.
"""

import pytest

from app.providers.amf_filings import parse


def avis(corps: str) -> str:
    """Reconstitue la forme d'un avis AMF autour du corps déclaratif."""
    return (
        "IL EST RAPPELE QUE LA PRESENTE DECLARATION EST ETABLIE SOUS LA "
        "RESPONSABILITE DU DECLARANT. VALEO (Euronext Paris) 1. " + corps
    )


GOLDMAN = avis(
    "Par un courrier reçu le 29 juillet 2026, la société The Goldman Sachs "
    "Group, Inc (Corporation Trust Center, 1209 Orange Street, Wilmington, DE "
    "19801, USA) a déclaré avoir franchi en hausse, le 23 juillet 2026, "
    "indirectement, le seuil de 5% des droits de vote de la société VALEO"
)


class TestNomDuDeclarant:
    def test_raison_sociale_avec_virgule(self):
        """« The Goldman Sachs Group, Inc » ne se coupe pas à la virgule."""
        assert parse(GOLDMAN)["declarant"] == "The Goldman Sachs Group, Inc"

    def test_forme_juridique_elaguee(self):
        texte = avis(
            "Par courrier reçu le 30 juillet 2026, la société par actions "
            "simplifiée Rock Investment (40 rue Ampère, Paris) a déclaré"
        )
        assert parse(texte)["declarant"] == "Rock Investment"

    def test_forme_juridique_etrangere(self):
        texte = avis(
            "Par courrier reçu le 6 juillet 2026, la société anonyme de droit "
            "belge SITAM Belgique (Bruxelles) a déclaré"
        )
        assert parse(texte)["declarant"] == "SITAM Belgique"

    def test_appel_de_note_retire(self):
        texte = avis(
            "Par courrier reçu le 28 juillet 2026, la société Janus Henderson "
            "Investors UK Limited1 (201 Bishopsgate, Londres) a déclaré"
        )
        assert parse(texte)["declarant"] == "Janus Henderson Investors UK Limited"

    def test_un_texte_sans_declaration_ne_produit_pas_de_nom(self):
        """Mieux vaut aucun nom qu'un nom inventé."""
        assert parse("226C1175-FR0013176526-FS0683 page 2")["declarant"] is None

    def test_document_vide(self):
        assert parse("")["declarant"] is None


class TestNatureDuDeclarant:
    def test_personne_morale(self):
        assert parse(GOLDMAN)["declarant_nature"] == "morale"

    @pytest.mark.parametrize("civilite", ["M.", "Mme", "Monsieur", "Madame"])
    def test_personne_physique(self, civilite):
        """Un actionnaire familial ou fondateur ne se lit pas comme un gérant."""
        texte = avis(
            f"Par courrier reçu le 12 juin 2026, {civilite} Jean Dupont "
            "(Paris) a déclaré avoir franchi en hausse"
        )
        resultat = parse(texte)
        assert resultat["declarant_nature"] == "physique"
        assert resultat["declarant"] == "Jean Dupont"

    def test_forme_absente(self):
        texte = avis(
            "Par courrier reçu le 1 mai 2026, Berkshire Hathaway Inc. "
            "(Omaha) a déclaré"
        )
        assert parse(texte)["declarant_nature"] == "inconnue"


class TestSensEtSeuil:
    def test_franchissement_en_hausse(self):
        assert parse(GOLDMAN)["sens"] == "hausse"

    def test_franchissement_en_baisse(self):
        texte = avis(
            "Par courrier reçu le 27 juillet 2026, la société JP Morgan Chase "
            "& Co. (Wilmington) a déclaré avoir franchi en baisse, le 22 "
            "juillet 2026, le seuil de 10% du capital"
        )
        resultat = parse(texte)
        assert resultat["sens"] == "baisse"
        assert resultat["seuil"] == pytest.approx(10.0)

    def test_seuil_et_sa_nature(self):
        resultat = parse(GOLDMAN)
        assert resultat["seuil"] == pytest.approx(5.0)
        assert resultat["seuil_nature"] == "droits de vote"

    def test_seuil_en_capital(self):
        texte = avis(
            "Par courrier reçu le 1 juin 2026, la société Amundi (Paris) a "
            "déclaré avoir franchi en hausse, le 28 mai 2026, le seuil de 5% "
            "du capital"
        )
        assert parse(texte)["seuil_nature"] == "capital"

    def test_seuil_decimal(self):
        texte = avis(
            "Par courrier reçu le 1 juin 2026, la société X (Paris) a déclaré "
            "avoir franchi en hausse, le 28 mai 2026, le seuil de 2,5% du capital"
        )
        assert parse(texte)["seuil"] == pytest.approx(2.5)


class TestDateDeFranchissement:
    def test_date_convertie(self):
        """La date du franchissement, pas celle de publication de l'avis."""
        assert parse(GOLDMAN)["franchi_le"] == "2026-07-23"

    def test_mois_accentue(self):
        texte = avis(
            "Par courrier reçu le 5 janvier 2026, la société X (Paris) a "
            "déclaré avoir franchi en hausse, le 30 décembre 2025, le seuil "
            "de 5% du capital"
        )
        assert parse(texte)["franchi_le"] == "2025-12-30"

    def test_date_absente(self):
        texte = avis(
            "Par courrier reçu le 5 janvier 2026, la société X (Paris) a "
            "déclaré avoir franchi le seuil de 5% du capital"
        )
        assert parse(texte)["franchi_le"] is None

    def test_date_invalide(self):
        texte = avis(
            "Par courrier reçu le 5 janvier 2026, la société X (Paris) a "
            "déclaré avoir franchi en hausse, le 32 juillet 2026, le seuil "
            "de 5% du capital"
        )
        assert parse(texte)["franchi_le"] is None


class TestStructureDeSortie:
    def test_toutes_les_cles_sont_presentes(self):
        """Le rendu ne doit pas avoir à tester l'existence de chaque champ."""
        attendues = {
            "declarant", "declarant_nature", "sens", "seuil",
            "seuil_nature", "franchi_le",
        }
        assert set(parse("")) == attendues
