"""Règle d'or : déclencher la sûreté d'identification sur les bons énoncés.

Ce test porte sur le détecteur, pas sur la réponse. C'est un endroit où
l'asymétrie des erreurs est totale : sur-déclencher ajoute un avertissement
inutile, sous-déclencher laisse passer sans garde-fou la question d'une
personne qui tient un champignon dans la main.

Les mêmes cas tournent côté Swift dans app/Tests/SurvieCoreTests/PariteTests.swift.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli"))

from survie.prompt import is_identification  # noqa: E402

DECLENCHE = [
    "ce champignon est-il comestible",
    # Le pluriel fait partie du nom : c'est la forme sous laquelle on cueille.
    "comment garder des châtaignes tout l'hiver",
    "j'ai ramassé des amanites ce matin",
    "ces bolets poussent sous les chênes",
    "des sureaux au bord du chemin",          # pluriel en -x
    "des fougères plein le sous-bois",
    "un if dans le cimetière du village",
    "une œnanthe safranée près du ruisseau",
    "une oenanthe safranée près du ruisseau",  # même plante, saisie sans ligature
    "châtaigne ou marron, comment les distinguer",
]

NE_DECLENCHE_PAS = [
    "comment faire un feu sous la pluie",
    "quelle direction prendre pour rejoindre une route",
    # « cependant » commence par « cèpe » plié : l'ancrage en tête de mot doit
    # l'écarter, sans quoi la moitié des questions déclencheraient la règle.
    "cependant il pleut, où s'abriter",
    "je préfère marcher de nuit",
]


@pytest.mark.parametrize("question", DECLENCHE)
def test_declenche(question):
    assert is_identification(question), question


@pytest.mark.parametrize("question", NE_DECLENCHE_PAS)
def test_ne_declenche_pas(question):
    assert not is_identification(question), question
