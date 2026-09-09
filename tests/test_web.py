"""Interface web locale.

L'interface est optionnelle : ces tests se sautent si FastAPI n'est pas
installe, l'installation minimale devant rester utilisable sans lui.
"""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from survie.web.serveur import creer_application  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(creer_application("standard"))


def test_la_page_est_servie(client):
    reponse = client.get("/")
    assert reponse.status_code == 200
    assert "Survie" in reponse.text


def test_la_page_ne_charge_aucune_ressource_distante(client):
    """Une page qui appelle un CDN est blanche hors ligne."""
    page = client.get("/").text
    for interdit in ("http://", "https://", "//cdn", "fonts.googleapis"):
        assert interdit not in page, f"ressource distante dans la page : {interdit}"


def test_etat_expose_le_mode_de_fonctionnement(client):
    """La page doit pouvoir dire a l'utilisateur si l'IA est active."""
    etat = client.get("/api/etat").json()
    assert etat["profil"] == "standard"
    assert etat["fragments"] > 0
    assert isinstance(etat["llm"], bool)


def test_demande_renvoie_des_sources(client):
    donnees = client.get(
        "/api/demande", params={"q": "desinfecter l'eau", "sources_seules": True}
    ).json()
    assert donnees["mode"] == "sources"
    assert donnees["fiches"]
    assert all(f.startswith("01-eau/") for f in donnees["fiches"])


def test_demande_hors_sujet_refusee(client):
    donnees = client.get("/api/demande", params={"q": "piloter un helicoptere"}).json()
    assert donnees["mode"] == "refus"
    assert donnees["extraits"] == []


def test_question_vide_rejetee(client):
    assert client.get("/api/demande", params={"q": "   "}).status_code == 400
