"""Tests du pont vers Wealthfolio.

Wealthfolio consomme ces routes via des chemins JSONPath enregistrés dans sa
configuration : `$.price`, `$.rows[*].close`… Renommer un champ casserait
silencieusement l'intégration côté utilisateur, sans erreur visible ici. Ces
tests figent donc la **forme** des réponses autant que leur contenu.

Aucun appel réseau : les fournisseurs sont remplacés par des doublures.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers import obb_source, yahoo_search
from app.routers import wealthfolio

QUOTE = {
    "symbol": "MC.PA",
    "name": "LVMH",
    "last_price": 475.15,
    "open": 468.95,
    "high": 478.9,
    "low": 467.5,
    "volume": 429187.0,
    "prev_close": 473.3,
    "currency": "EUR",
    "as_of": "2026-08-01T17:04:13.200689",
}

HISTORY = [
    {"date": "2026-07-30", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
    {"date": "2026-07-31", "open": 1.5, "high": 2.5, "low": 1.0, "close": 2.0, "volume": 20.0},
]

PROFILE = {"symbol": "MC.PA", "name": "LVMH", "hq_country": "France"}


@pytest.fixture
def client(monkeypatch):
    async def fake_quote(symbol, provider=obb_source.DEFAULT_PROVIDER):
        return dict(QUOTE, symbol=symbol)

    async def fake_history(symbol, start_date=None, end_date=None, interval="1d", provider=None):
        return list(HISTORY)

    async def fake_profile(symbol, provider=obb_source.DEFAULT_PROVIDER):
        return dict(PROFILE, symbol=symbol)

    async def fake_resolve_isin(isin):
        return "MC.PA"

    monkeypatch.setattr(wealthfolio.obb_source, "quote", fake_quote)
    monkeypatch.setattr(wealthfolio.obb_source, "historical", fake_history)
    monkeypatch.setattr(wealthfolio.obb_source, "profile", fake_profile)
    monkeypatch.setattr(wealthfolio.yahoo_search, "resolve_isin", fake_resolve_isin)
    with TestClient(app) as test_client:
        yield test_client


class TestFormeDeLaCotation:
    def test_les_champs_du_contrat_sont_presents(self, client):
        """Ces noms sont gravés dans la configuration de Wealthfolio."""
        body = client.get("/api/wf/quote/MC.PA").json()
        for field in ("symbol", "price", "date", "currency", "open", "high", "low", "volume"):
            assert field in body, f"champ manquant : {field}"

    def test_le_prix_est_un_nombre_et_non_une_chaine(self, client):
        body = client.get("/api/wf/quote/MC.PA").json()
        assert isinstance(body["price"], float)
        assert body["price"] == 475.15

    def test_la_date_est_une_date_de_seance_pas_un_horodatage(self, client):
        """Wealthfolio range les cours par jour : un horodatage complet
        produirait une ligne par collecte."""
        body = client.get("/api/wf/quote/MC.PA").json()
        assert body["date"] == "2026-08-01"
        assert len(body["date"]) == 10

    def test_le_caractere_differe_est_annonce(self, client):
        assert client.get("/api/wf/quote/MC.PA").json()["delayed"] is True

    def test_le_statut_pea_accompagne_la_cotation(self, client):
        assert client.get("/api/wf/quote/MC.PA").json()["pea_status"] == "eligible"


class TestFormeDeLHistorique:
    def test_les_lignes_portent_les_champs_du_contrat(self, client):
        body = client.get("/api/wf/history/MC.PA").json()
        assert isinstance(body["rows"], list)
        for field in ("date", "open", "high", "low", "close", "volume"):
            assert field in body["rows"][0], f"champ manquant : {field}"

    def test_les_dates_sont_tronquees_au_jour(self, client):
        body = client.get("/api/wf/history/MC.PA").json()
        assert all(len(row["date"]) == 10 for row in body["rows"])

    def test_l_ordre_chronologique_est_preserve(self, client):
        rows = client.get("/api/wf/history/MC.PA").json()["rows"]
        assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)

    def test_les_bornes_from_et_to_sont_acceptees(self, client):
        """Wealthfolio substitue {FROM} et {TO} dans l'URL du gabarit."""
        response = client.get("/api/wf/history/MC.PA?from=2026-07-01&to=2026-07-31")
        assert response.status_code == 200


class TestResolutionISIN:
    def test_un_isin_est_converti_en_ticker(self, client):
        """Les relevés de brokers français désignent les titres par ISIN."""
        body = client.get("/api/wf/quote/FR0000121014").json()
        assert body["symbol"] == "MC.PA"

    def test_un_ticker_passe_tel_quel(self, client):
        assert client.get("/api/wf/quote/MC.PA").json()["symbol"] == "MC.PA"

    def test_la_casse_du_ticker_est_normalisee(self, client):
        assert client.get("/api/wf/quote/mc.pa").json()["symbol"] == "MC.PA"

    def test_un_isin_non_resolu_donne_404(self, client, monkeypatch):
        async def unresolved(isin):
            return None

        monkeypatch.setattr(wealthfolio.yahoo_search, "resolve_isin", unresolved)
        assert client.get("/api/wf/quote/FR0000000000").status_code == 404


class TestEligibilitePea:
    def test_le_verdict_porte_sa_justification(self, client):
        """Un booléen sans explication serait inutilisable : l'utilisateur doit
        pouvoir vérifier pourquoi un titre est classé ainsi."""
        body = client.get("/api/wf/pea/MC.PA").json()
        assert body["eligible"] is True
        assert body["country_iso"] == "FR"
        assert body["reason"]

    def test_une_societe_hors_eee_est_refusee(self, client, monkeypatch):
        async def swiss_profile(symbol, provider=obb_source.DEFAULT_PROVIDER):
            return {"symbol": symbol, "name": "Nestlé", "hq_country": "Switzerland"}

        monkeypatch.setattr(wealthfolio.obb_source, "profile", swiss_profile)
        body = client.get("/api/wf/pea/NESN.SW").json()
        assert body["eligible"] is False
        assert body["country_iso"] == "CH"

    def test_un_pays_inconnu_ne_vaut_pas_eligible(self, client, monkeypatch):
        async def blank_profile(symbol, provider=obb_source.DEFAULT_PROVIDER):
            return {"symbol": symbol, "name": "?", "hq_country": None}

        monkeypatch.setattr(wealthfolio.obb_source, "profile", blank_profile)
        body = client.get("/api/wf/pea/XXXX.PA").json()
        assert body["eligible"] is False
        assert body["status"] == "inconnu"


class TestValeursManquantes:
    def test_un_champ_absent_devient_null_et_ne_casse_pas(self, client, monkeypatch):
        async def partial_quote(symbol, provider=obb_source.DEFAULT_PROVIDER):
            return {"symbol": symbol, "last_price": 10.0, "as_of": "2026-08-01T10:00:00"}

        monkeypatch.setattr(wealthfolio.obb_source, "quote", partial_quote)
        body = client.get("/api/wf/quote/X.PA").json()
        assert body["price"] == 10.0
        assert body["volume"] is None
        assert body["currency"] is None
