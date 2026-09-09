"""Tokenisation, BM25 et recherche hybride."""

from __future__ import annotations

import pytest

from survie.index.bm25 import BM25
from survie.index.store import IndexDisque
from survie.index.texte import deplier, tokeniser
from survie.recherche.hybride import MoteurRecherche


def test_deplier_supprime_les_accents():
    assert deplier("Ébullition") == "ebullition"
    assert deplier("Désinfecter l'EAU") == "desinfecter l'eau"


def test_tokeniser_ecarte_les_mots_vides():
    tokens = tokeniser("Comment rendre l'eau de la mare potable ?")
    assert "eau" in tokens and "potable" in tokens
    assert "de" not in tokens and "la" not in tokens


def test_tokeniser_ignore_les_accents():
    """Sans cela, une question accentuee ne retrouve pas une fiche accentuee."""
    assert tokeniser("désinfecter") == tokeniser("desinfecter")


def test_bm25_classe_le_document_pertinent_en_tete():
    moteur = BM25(
        [
            "Faire bouillir l'eau a gros bouillons pendant une minute",
            "Semer les pommes de terre au mois d'avril",
            "Conserver les semences au sec et a l'obscurite",
        ]
    )
    scores = moteur.scores("bouillir eau")
    assert scores[0] == max(scores) > 0


def test_bm25_sans_correspondance_renvoie_zero():
    moteur = BM25(["semer les carottes en avril"])
    assert moteur.scores("moteur diesel turbocompresse") == [0.0]


def _index_factice() -> IndexDisque:
    fragments = [
        {
            "fiche": "01-eau/ebullition.md",
            "titre": "Desinfecter l'eau par ebullition",
            "domaine": "eau",
            "criticite": "vitale",
            "delai": "immediat",
            "verifie_le": "2026-01-01",
            "sources": [],
            "section": "Methode",
            "reference": "01-eau/ebullition.md § Methode",
            "texte": "Porter a gros bouillons pendant une minute complete.",
            "indexable": "Desinfecter l'eau par ebullition eau "
                         "Porter a gros bouillons pendant une minute complete.",
        },
        {
            "fiche": "02-alimentation/semis.md",
            "titre": "Calendrier de semis",
            "domaine": "agriculture",
            "criticite": "normale",
            "delai": "saison",
            "verifie_le": "2026-01-01",
            "sources": [],
            "section": "Avril",
            "reference": "02-alimentation/semis.md § Avril",
            "texte": "Planter les pommes de terre des que le gel est passe.",
            "indexable": "Calendrier de semis agriculture "
                         "Planter les pommes de terre des que le gel est passe.",
        },
    ]
    return IndexDisque(fragments=fragments, vecteurs=None)


def test_recherche_trouve_la_bonne_fiche():
    moteur = MoteurRecherche(_index_factice())
    resultats = moteur.chercher("comment desinfecter l'eau", nombre=2)
    assert resultats[0].fiche == "01-eau/ebullition.md"


def test_score_normalise_borne_a_un():
    """Le seuil de pertinence n'a de sens que si le score est comparable."""
    moteur = MoteurRecherche(_index_factice())
    for resultat in moteur.chercher("eau bouillir", nombre=2):
        assert 0.0 <= resultat.score <= 1.0


def test_question_hors_sujet_ne_remonte_rien():
    """Aucun moteur ne reconnait le sujet : il ne faut rien remonter.

    C'est la garantie qui empeche le LLM de broder sur des extraits pris au
    hasard faute de mieux.
    """
    moteur = MoteurRecherche(_index_factice())
    assert moteur.chercher("reparer un turbocompresseur diesel", nombre=2) == []


def test_index_vide_ne_plante_pas():
    moteur = MoteurRecherche(IndexDisque(fragments=[], vecteurs=None))
    assert moteur.chercher("quoi que ce soit") == []
