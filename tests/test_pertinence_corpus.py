"""Le systeme refuse-t-il d'inventer, sur le vrai corpus ?

C'est la propriete de securite centrale du projet. Ces cas sont mesures sur
le corpus reel et non sur un index factice : le seuil de pertinence est
calibre par eux, et toute derive (une fiche ajoutee, un mot devenu ambigu)
les fait echouer.
"""

from __future__ import annotations

import pytest

from survie.config import DOSSIER_CONNAISSANCES, charger
from survie.corpus.chunker import decouper
from survie.corpus.loader import charger_fiches
from survie.index.store import IndexDisque
from survie.recherche.hybride import MoteurRecherche
from survie.recherche.reponse import repondre

SEUIL = charger("standard").seuil_pertinence

# Questions auxquelles le corpus doit repondre.
COUVERTES = [
    "comment rendre potable l'eau d'une mare",
    "quelle surface faut-il pour nourrir une personne",
    "comment arreter une hemorragie",
    "quand semer les pommes de terre",
    "conserver des legumes sans frigo",
    "mon enfant a la diarrhee que faire",
    "comment desinfecter l'eau avec de la javel",
    "ou installer des latrines",
]

# Questions hors du perimetre dont le vocabulaire distinctif est absent du
# corpus : le filtre lexical doit les rejeter.
HORS_SUJET = [
    "quelle est la capitale de l'Australie",
    "comment piloter un helicoptere",
    "expliquer la relativite generale",
    "comment investir en bourse",
    "qui a compose la neuvieme symphonie",
]

# Limite connue et assumee : une question hors sujet formulee avec des mots
# presents ailleurs dans le corpus passe le filtre lexical. Le garde-fou est
# alors la consigne donnee au modele et l'affichage des sources, pas le seuil.
# Ce test fige la limite pour qu'elle reste visible ; il echouera si les
# embeddings, qui la corrigent, sont un jour integres au filtre.
LIMITE_CONNUE = ["qui a gagne la coupe du monde 1998"]


@pytest.fixture(scope="module")
def moteur() -> MoteurRecherche:
    """Index lexical construit en memoire : pas de modele requis."""
    fiches = charger_fiches(DOSSIER_CONNAISSANCES)
    entrees = [
        {
            "fiche": f.fiche.identifiant,
            "titre": f.fiche.titre,
            "domaine": f.fiche.domaine,
            "criticite": f.fiche.criticite,
            "delai": f.fiche.delai,
            "verifie_le": f.fiche.verifie_le,
            "sources": f.fiche.sources,
            "section": f.section,
            "reference": f.reference,
            "texte": f.texte,
            "indexable": f.texte_indexable,
        }
        for fiche in fiches
        for f in decouper(fiche)
    ]
    return MoteurRecherche(IndexDisque(fragments=entrees, vecteurs=None))


@pytest.mark.parametrize("question", COUVERTES)
def test_les_questions_couvertes_recoivent_une_reponse(moteur, question):
    reponse = repondre(question, moteur, llm=None, seuil=SEUIL)
    assert reponse.mode == "sources", (
        f"refus a tort ({moteur.pertinence(question, moteur.chercher(question, 6)):.2f} "
        f"< {SEUIL}) : {question!r}"
    )
    assert reponse.extraits


@pytest.mark.parametrize("question", HORS_SUJET)
def test_les_questions_hors_sujet_sont_refusees(moteur, question):
    reponse = repondre(question, moteur, llm=None, seuil=SEUIL)
    assert reponse.mode == "refus", (
        f"a repondu a tort ({moteur.pertinence(question, moteur.chercher(question, 6)):.2f} "
        f">= {SEUIL}) : {question!r}"
    )
    assert reponse.extraits == []


@pytest.mark.parametrize("question", LIMITE_CONNUE)
def test_limite_du_filtre_lexical(moteur, question):
    """Documente ce que le filtre ne sait pas faire, plutot que de le taire."""
    pertinence = moteur.pertinence(question, moteur.chercher(question, 6))
    assert pertinence >= SEUIL, (
        "Cette question hors sujet est desormais rejetee : le filtre s'est "
        "ameliore, deplacer ce cas dans HORS_SUJET."
    )


def test_aucune_question_couverte_n_est_refusee_de_justesse(moteur):
    """Marge de securite : le seuil doit rester sous le pire cas legitime."""
    pire = min(
        moteur.pertinence(q, moteur.chercher(q, 6)) for q in COUVERTES
    )
    assert pire > SEUIL, f"marge nulle : la question la plus faible est a {pire:.2f}"


def test_les_bonnes_fiches_remontent(moteur):
    """Verifie que la recherche vise juste, pas seulement qu'elle repond."""
    attendus = {
        "comment desinfecter l'eau en la faisant bouillir": "01-eau/desinfection-ebullition.md",
        "comment arreter une hemorragie": "03-sante/hemorragie.md",
        "recuperer les graines de mes tomates": "02-alimentation/agriculture/conserver-ses-semences.md",
    }
    for question, attendu in attendus.items():
        fiches = {r.fiche for r in moteur.chercher(question, nombre=6)}
        assert attendu in fiches, f"{attendu} absent des resultats de {question!r}"
