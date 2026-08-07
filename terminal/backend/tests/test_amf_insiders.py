"""Tests de la lecture des déclarations de dirigeants.

Ces avis nomment une personne et chiffrent son opération. Une erreur
d'extraction n'échoue pas bruyamment : elle attribue une vente à quelqu'un
qui a acheté, ou décale un montant d'un facteur mille. Les formes réellement
rencontrées dans la BDIF sont donc figées ici.

Aucun appel réseau : l'analyse porte sur du texte.
"""

import pytest

from app.providers.amf_insiders import parse

ENTETE = (
    "INFORMATION Déclaration individuelle relative aux opérations des "
    "personnes mentionnées à l’article L.621-18-2 du Code monétaire et "
    "financier LA PRESENTE NOTIFICATION N’A PAS FAIT L’OBJET D’UN CONTROLE "
    "DE L’AMF. NOM /FONCTION DE LA PERSONNE EXERCANT DES RESPONSABILITES "
    "DIRIGEANTES OU DE LA PERSONNE ETROITEMENT LIEE : "
)


def avis(
    declarant: str,
    nature: str = "Acquisition",
    emetteur: str = "VINCI",
    instrument: str = "Action",
    isin: str = "FR0000125486",
    date: str = "10 juin 2026",
    prix: str = "123.2409",
    volume: str = "7 077.0000",
) -> str:
    return (
        ENTETE + declarant + " NOTIFICATION INITIALE / MODIFICATION: Notification "
        f"initiale COORDONNEES DE L’EMETTEUR NOM : {emetteur} LEI : 969500XYZ "
        f"DETAIL DE LA TRANSACTION DATE DE LA TRANSACTION : {date} "
        "LIEU DE LA TRANSACTION : Euronext Paris "
        f"NATURE DE LA TRANSACTION : {nature} "
        f"DESCRIPTION DE L’INSTRUMENT FINANCIER : {instrument} "
        f"CODE D’IDENTIFICATION DE L’INSTRUMENT FINANCIER : {isin} "
        f"INFORMATIONS AGREGEES PRIX : {prix} Euro VOLUME : {volume} "
        "TRANSACTION LIEE A L’EXERCICE DE PROGRAMMES D’OPTIONS : NON"
    )


class TestIdentiteDuDeclarant:
    def test_nom_et_fonction_separes(self):
        resultat = parse(avis("XAVIER HUILLARD, Président"))
        assert resultat["declarant"] == "XAVIER HUILLARD"
        assert resultat["fonction"] == "Président"

    def test_fonction_composee(self):
        resultat = parse(
            avis("SYLVAIN MONTCOUQUIOL, Directeur Général et membre du Directoire")
        )
        assert resultat["fonction"] == "Directeur Général et membre du Directoire"

    def test_personne_morale_liee(self):
        """Une holding familiale déclare pour le compte d'un dirigeant."""
        resultat = parse(
            avis("GEST INVEST société civile personne morale liée à Philippe ROSIO, "
                 "Président Directeur Général de l'Emetteur")
        )
        assert resultat["declarant"].startswith("GEST INVEST")
        assert "Philippe ROSIO" in resultat["declarant"]

    def test_sans_fonction(self):
        resultat = parse(avis("JEAN DUPONT"))
        assert resultat["declarant"] == "JEAN DUPONT"
        assert resultat["fonction"] is None

    def test_emetteur_lu(self):
        assert parse(avis("X, Président", emetteur="FONCIERE INEA"))["emetteur"] == (
            "FONCIERE INEA"
        )


class TestSensDeLOperation:
    @pytest.mark.parametrize(
        "nature", ["Acquisition", "Souscription", "Achat", "Attribution d'actions"]
    )
    def test_natures_acheteuses(self, nature):
        assert parse(avis("X, Président", nature=nature))["sens"] == "achat"

    @pytest.mark.parametrize("nature", ["Cession", "Vente", "Apport de titres"])
    def test_natures_vendeuses(self, nature):
        assert parse(avis("X, Président", nature=nature))["sens"] == "vente"

    def test_nature_inclassable_reste_sans_sens(self):
        """Mieux vaut ne rien conclure que de trancher au hasard."""
        resultat = parse(avis("X, Président", nature="Nantissement"))
        assert resultat["nature"] == "Nantissement"
        assert resultat["sens"] is None

    def test_la_nature_exacte_est_conservee(self):
        """Souscrire à un plan d'épargne salariale n'est pas acheter en bourse."""
        assert parse(avis("X, Président", nature="Souscription"))["nature"] == (
            "Souscription"
        )


class TestChiffresDeLOperation:
    def test_prix_volume_et_montant(self):
        resultat = parse(avis("X, Président", prix="123.2409", volume="7 077.0000"))
        assert resultat["prix"] == pytest.approx(123.2409)
        assert resultat["volume"] == pytest.approx(7077.0)
        assert resultat["montant"] == pytest.approx(872175.85, abs=0.01)

    def test_espace_insecable_dans_le_volume(self):
        """Les PDF de l'AMF séparent les milliers par une espace."""
        assert parse(avis("X, Président", volume="1 565.8029"))["volume"] == (
            pytest.approx(1565.8029)
        )

    def test_virgule_decimale(self):
        assert parse(avis("X, Président", prix="15,71"))["prix"] == pytest.approx(15.71)

    def test_devise(self):
        assert parse(avis("X, Président"))["devise"] == "Euro"

    def test_chiffres_absents(self):
        resultat = parse(ENTETE + "X, Président NOTIFICATION")
        assert resultat["prix"] is None
        assert resultat["volume"] is None
        assert resultat["montant"] is None


class TestIdentifiantsEtDates:
    def test_isin(self):
        assert parse(avis("X, Président", isin="FR0010341032"))["isin"] == "FR0010341032"

    def test_date_de_transaction(self):
        assert parse(avis("X, Président", date="05 août 2026"))["transaction_le"] == (
            "2026-08-05"
        )

    def test_date_invalide(self):
        assert parse(avis("X, Président", date="32 juillet 2026"))["transaction_le"] is None

    def test_instrument(self):
        assert parse(avis("X, Président", instrument="Action"))["instrument"] == "Action"

    def test_lieu(self):
        assert parse(avis("X, Président"))["lieu"] == "Euronext Paris"


class TestRobustesse:
    def test_document_vide(self):
        resultat = parse("")
        assert resultat["declarant"] is None
        assert resultat["sens"] is None

    def test_toutes_les_cles_sont_presentes(self):
        """Le rendu ne doit pas tester l'existence de chaque champ."""
        attendues = {
            "declarant", "fonction", "emetteur", "nature", "sens", "instrument",
            "isin", "lieu", "transaction_le", "prix", "devise", "volume", "montant",
        }
        assert set(parse("")) == attendues

    def test_apostrophe_droite_acceptee(self):
        """Tous les PDF n'emploient pas l'apostrophe typographique."""
        texte = avis("X, Président").replace("’", "'")
        assert parse(texte)["isin"] == "FR0000125486"
