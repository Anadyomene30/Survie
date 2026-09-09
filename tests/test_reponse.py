"""Assemblage de la reponse et refus d'inventer.

Le refus est la propriete la plus importante du systeme : une reponse
plausible mais fausse sur une eau ou une plante peut tuer.
"""

from __future__ import annotations

from survie.index.store import IndexDisque
from survie.llm.prompts import REFUS, construire_invite
from survie.recherche.hybride import MoteurRecherche
from survie.recherche.reponse import repondre

from tests.test_recherche import _index_factice


class LLMFactice:
    """Enregistre l'invite recue au lieu d'appeler un vrai modele."""

    def __init__(self) -> None:
        self.invites: list[str] = []

    def repondre(self, invite: str, max_tokens: int = 700) -> str:
        self.invites.append(invite)
        return "Reponse redigee."


def test_question_hors_corpus_refusee():
    moteur = MoteurRecherche(_index_factice())
    llm = LLMFactice()
    reponse = repondre("reparer un turbocompresseur diesel", moteur, llm=llm)

    assert reponse.mode == "refus"
    assert reponse.texte == REFUS
    assert reponse.extraits == []
    assert llm.invites == [], "le LLM ne doit meme pas etre sollicite"


def test_sans_llm_les_extraits_sont_rendus_bruts():
    """Deuxieme niveau de degradation : utile sans modele."""
    reponse = repondre("desinfecter l'eau", MoteurRecherche(_index_factice()), llm=None)
    assert reponse.mode == "sources"
    assert "gros bouillons" in reponse.texte
    assert reponse.fiches_citees == ["01-eau/ebullition.md"]


def test_avec_llm_l_invite_ne_contient_que_les_extraits():
    llm = LLMFactice()
    reponse = repondre("desinfecter l'eau", MoteurRecherche(_index_factice()), llm=llm)

    assert reponse.mode == "redige"
    invite = llm.invites[0]
    assert "gros bouillons" in invite
    assert "01-eau/ebullition.md" in invite, "la source doit etre citable"


def test_seuil_de_pertinence_respecte():
    moteur = MoteurRecherche(_index_factice())
    llm = LLMFactice()
    # Seuil a 1.1 : rien ne peut l'atteindre, tout doit etre refuse.
    reponse = repondre("desinfecter l'eau", moteur, llm=llm, seuil=1.1)
    assert reponse.mode == "refus"
    assert llm.invites == []


def test_fiches_citees_sans_doublon():
    fragments = _index_factice().fragments
    fragments.append({**fragments[0], "section": "Autre", "reference": "x § Autre"})
    reponse = repondre(
        "eau bouillir", MoteurRecherche(IndexDisque(fragments, None)), llm=None
    )
    assert len(reponse.fiches_citees) == len(set(reponse.fiches_citees))


def test_invite_numerote_et_source_chaque_extrait():
    moteur = MoteurRecherche(_index_factice())
    invite = construire_invite("test", moteur.chercher("eau bouillir", nombre=2))
    assert "Extrait 1" in invite
    assert invite.count("---") >= 2
