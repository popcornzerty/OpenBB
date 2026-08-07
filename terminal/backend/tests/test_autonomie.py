"""Le terminal doit fonctionner intégralement sans Wealthfolio.

Wealthfolio a d'abord servi de source de portefeuille ; il n'est plus qu'un
**import ponctuel**, et la synchronisation reste offerte à qui l'utilise. Ces
tests figent cette indépendance : chaque écran doit tenir alors que la base de
Wealthfolio est introuvable, et seule la route d'import a le droit d'échouer.

La régression serait sournoise — sur une machine où Wealthfolio est installé,
personne ne s'apercevrait qu'une dépendance s'est réintroduite.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.portfolio import realized, store, targets
from app.providers import wealthfolio_db


@pytest.fixture
def sans_wealthfolio(tmp_path, monkeypatch):
    """Base Wealthfolio introuvable, et état entièrement isolé du poste.

    Les **trois** magasins sont redirigés. N'en isoler qu'un a suffi à écrire
    de fausses cessions et à écraser les pondérations cibles dans les données
    réelles de l'utilisateur : ces tests exercent des routes qui écrivent, et
    tout ce qu'elles touchent doit atterrir dans le répertoire temporaire.
    """
    absente = tmp_path / "nulle-part" / "app.db"
    monkeypatch.setattr(wealthfolio_db, "database_path", lambda: absente)

    etat = tmp_path / "etat"
    etat.mkdir()
    monkeypatch.setattr(store, "_path", lambda: etat / "positions.json")
    monkeypatch.setattr(realized, "_path", lambda: etat / "realized.json")
    monkeypatch.setattr(targets, "_path", lambda: etat / "allocation_targets.json")

    with TestClient(app) as client:
        yield client


def test_l_isolation_couvre_tous_les_magasins(sans_wealthfolio, tmp_path):
    """Garde-fou : une écriture ne doit jamais sortir du répertoire temporaire.

    Sans ce test, ajouter demain un quatrième magasin sans l'isoler
    repasserait inaperçu jusqu'à ce qu'il pollue des données réelles.
    """
    for module in (store, realized, targets):
        chemin = Path(module._path())
        assert tmp_path in chemin.parents, f"{module.__name__} écrit hors du bac à sable"


class TestLesEcransTiennentSansWealthfolio:
    def test_l_application_demarre(self, sans_wealthfolio):
        assert sans_wealthfolio.get("/api/health").status_code == 200

    @pytest.mark.parametrize(
        "route",
        [
            "/api/portfolio/positions",
            "/api/portfolio/holdings",
            "/api/portfolio/realized",
            "/api/portfolio/targets",
            "/api/portfolio/status",
        ],
    )
    def test_les_routes_du_portefeuille_repondent(self, sans_wealthfolio, route):
        assert sans_wealthfolio.get(route).status_code == 200

    def test_l_indisponibilite_est_annoncee_sans_erreur(self, sans_wealthfolio):
        """L'interface doit pouvoir masquer le bouton d'import, pas planter."""
        body = sans_wealthfolio.get("/api/portfolio/status").json()
        assert body["wealthfolio"]["available"] is False
        assert body["wealthfolio"]["positions"] == 0

    def test_un_portefeuille_vide_n_est_pas_une_erreur(self, sans_wealthfolio):
        body = sans_wealthfolio.get("/api/portfolio/holdings").json()
        assert body["empty"] is True
        assert body["rows"] == []


class TestLeCycleDeViePasseSansWealthfolio:
    """Saisir, importer, modifier, vendre, supprimer — sans rien d'externe."""

    def test_saisie_manuelle(self, sans_wealthfolio):
        response = sans_wealthfolio.put(
            "/api/portfolio/positions/MC.PA",
            json={"symbol": "MC.PA", "quantity": 10, "average_cost": 500.0},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 1

    def test_import_csv(self, sans_wealthfolio):
        response = sans_wealthfolio.post(
            "/api/portfolio/positions/import-csv",
            json={"content": "symbol;quantity;buyingPrice\nSAN.PA;50;80,00\n",
                  "replace": True},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1

    def test_modification_puis_suppression(self, sans_wealthfolio):
        sans_wealthfolio.put(
            "/api/portfolio/positions/MC.PA",
            json={"symbol": "MC.PA", "quantity": 10, "average_cost": 500.0},
        )
        modifiee = sans_wealthfolio.put(
            "/api/portfolio/positions/MC.PA",
            json={"symbol": "MC.PA", "quantity": 20, "average_cost": 500.0},
        )
        assert modifiee.json()["positions"][0]["quantity"] == 20
        assert sans_wealthfolio.delete("/api/portfolio/positions/MC.PA").json()["count"] == 0

    def test_cession(self, sans_wealthfolio):
        sans_wealthfolio.put(
            "/api/portfolio/positions/MC.PA",
            json={"symbol": "MC.PA", "quantity": 10, "average_cost": 500.0},
        )
        response = sans_wealthfolio.post(
            "/api/portfolio/positions/MC.PA/sell",
            json={"quantity": 4, "price": 600.0, "date": "2026-08-01"},
        )
        assert response.status_code == 200
        assert response.json()["sale"]["gain"] == pytest.approx(400.0)

    def test_cibles_de_repartition(self, sans_wealthfolio):
        response = sans_wealthfolio.put(
            "/api/portfolio/targets",
            json={"sectors": {"Technology": 0.25}, "regions": {"France": 0.5}},
        )
        assert response.status_code == 200
        assert response.json()["sectors"]["Technology"] == pytest.approx(0.25)


class TestSeuleLaPasserelleEchoue:
    def test_l_import_annonce_clairement_l_absence(self, sans_wealthfolio):
        response = sans_wealthfolio.post("/api/portfolio/positions/import-wealthfolio")
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "Wealthfolio" in detail
        # Le message doit indiquer quoi faire, pas seulement ce qui manque.
        assert "PEATERM_WEALTHFOLIO_DB" in detail

    def test_l_echec_ne_touche_pas_au_portefeuille(self, sans_wealthfolio):
        sans_wealthfolio.put(
            "/api/portfolio/positions/MC.PA",
            json={"symbol": "MC.PA", "quantity": 10, "average_cost": 500.0},
        )
        sans_wealthfolio.post("/api/portfolio/positions/import-wealthfolio")
        assert sans_wealthfolio.get("/api/portfolio/positions").json()["count"] == 1


class TestLaSynchronisationResteOfferte:
    """Le pont sortant ne dépend pas de l'installation de Wealthfolio.

    Ces routes servent Wealthfolio, elles ne le consultent pas : elles doivent
    répondre que le voisin soit là ou non.
    """

    def test_les_routes_du_pont_sont_montees(self, sans_wealthfolio):
        chemins = {r.path for r in app.routes}
        assert "/api/wf/quote/{symbol}" in chemins
        assert "/api/wf/history/{symbol}" in chemins
        assert "/api/wf/pea/{symbol}" in chemins

    def test_l_import_reste_propose(self, sans_wealthfolio):
        """Retirer la route priverait ceux qui utilisent les deux."""
        chemins = {r.path for r in app.routes}
        assert "/api/portfolio/positions/import-wealthfolio" in chemins


class TestAucuneEcritureDansWealthfolio:
    """Le terminal lit Wealthfolio, il ne l'écrit jamais."""

    def test_la_base_est_ouverte_en_lecture_seule(self):
        source = Path(wealthfolio_db.__file__).read_text(encoding="utf-8")
        assert "mode=ro" in source or "immutable" in source

    def test_aucune_instruction_d_ecriture(self):
        source = Path(wealthfolio_db.__file__).read_text(encoding="utf-8").upper()
        for mot in ("INSERT ", "UPDATE ", "DELETE FROM", "DROP "):
            assert mot not in source, mot


class TestPageDAccueilDuService:
    """Le port de l'API n'est pas celui de l'interface.

    Y arriver par mégarde est fréquent — c'est le port qu'on lit dans les
    journaux. La page doit renvoyer vers la bonne interface, et surtout
    signaler le cas où elle ne peut pas la connaître.
    """

    def test_la_racine_repond(self, sans_wealthfolio):
        reponse = sans_wealthfolio.get("/")
        assert reponse.status_code == 200
        assert "service de données" in reponse.text

    def test_elle_renvoie_vers_l_interface(self, sans_wealthfolio):
        assert "localhost:5180" in sans_wealthfolio.get("/").text

    def test_aucun_avertissement_en_configuration_par_defaut(self, sans_wealthfolio):
        assert "n'est pas celui par défaut" not in sans_wealthfolio.get("/").text

    def test_un_port_backend_deplace_declenche_l_avertissement(
        self, sans_wealthfolio, monkeypatch
    ):
        """Une seconde instance mal réglée renverrait sinon vers la première.

        Le port de l'interface est un réglage, pas une détection : rien ne
        permet de le deviner depuis une requête arrivée en direct.
        """
        from app import main
        from app.settings import Settings

        monkeypatch.setattr(main, "settings", Settings(port=8802, frontend_port=5180))
        assert "n'est pas celui par défaut" in sans_wealthfolio.get("/").text

    def test_deux_instances_correctement_reglees_ne_se_confondent_pas(
        self, sans_wealthfolio, monkeypatch
    ):
        from app import main
        from app.settings import Settings

        monkeypatch.setattr(main, "settings", Settings(port=8802, frontend_port=5181))
        html = sans_wealthfolio.get("/").text
        assert "localhost:5181" in html
        assert "localhost:5180" not in html
        assert "n'est pas celui par défaut" not in html
