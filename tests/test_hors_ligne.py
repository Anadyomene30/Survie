"""Le chemin de reponse ne doit contenir aucun acces reseau.

Une dependance reseau qui s'y glisserait ne se verrait qu'au pire moment :
hors ligne, en situation de crise. Ce test la fait echouer tout de suite.
"""

from __future__ import annotations

import socket

import pytest

from survie.recherche.hybride import MoteurRecherche
from survie.recherche.reponse import repondre
from survie.urgence.protocoles import fiches_vitales, filtrer
from survie.config import DOSSIER_CONNAISSANCES

from tests.test_recherche import _index_factice


@pytest.fixture
def reseau_coupe(monkeypatch):
    """Toute tentative de connexion leve une exception."""

    def interdit(*args, **kwargs):
        raise AssertionError("acces reseau dans le chemin de reponse")

    monkeypatch.setattr(socket, "socket", interdit)
    monkeypatch.setattr(socket, "create_connection", interdit)
    monkeypatch.setattr(socket, "getaddrinfo", interdit)


def test_recherche_fonctionne_hors_ligne(reseau_coupe):
    reponse = repondre("desinfecter l'eau", MoteurRecherche(_index_factice()), llm=None)
    assert reponse.mode == "sources"


def test_urgence_fonctionne_hors_ligne(reseau_coupe):
    """Troisieme niveau : sans index ni modele, seulement des fichiers."""
    fiches = fiches_vitales(DOSSIER_CONNAISSANCES)
    assert fiches, "aucune fiche vitale dans le corpus"
    assert fiches[0].delai == "immediat", "les gestes immediats doivent venir en tete"


def test_filtre_urgence_ignore_les_accents():
    fiches = fiches_vitales(DOSSIER_CONNAISSANCES)
    assert filtrer(fiches, "sante") == filtrer(fiches, "santé")


def test_filtre_urgence_sans_correspondance():
    assert filtrer(fiches_vitales(DOSSIER_CONNAISSANCES), "turbocompresseur") == []
