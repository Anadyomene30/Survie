"""Recherche hybride : BM25 + vectoriel, fusionnes par RRF.

RRF (Reciprocal Rank Fusion) travaille sur les rangs et non sur les scores :
inutile de calibrer deux echelles heterogenes, et la fusion reste correcte
quand l'un des deux moteurs est absent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from survie.index.bm25 import BM25
from survie.index.store import IndexDisque

K_RRF = 60  # constante usuelle : amortit le poids des premiers rangs

# En dessous de ce cosinus, le moteur vectoriel ne "reconnait" pas le
# fragment : il ne doit pas voter pour lui.
SIMILARITE_MINIMALE = 0.3

# Une question urgente doit remonter les gestes immediats avant la theorie.
POIDS_CRITICITE = {"vitale": 1.15, "haute": 1.05, "normale": 1.0}
MOTS_URGENCE = frozenset(
    "urgence urgent immediat immediatement vite secours danger mourir mort "
    "blesse blessure saigne saignement etouffe noyade brule tout de suite".split()
)


@dataclass
class Resultat:
    reference: str
    fiche: str
    titre: str
    section: str
    texte: str
    domaine: str
    criticite: str
    sources: list[str]
    verifie_le: str
    score: float


def _rangs(scores, minimum: float = 0.0) -> dict[int, int]:
    """Rangs des seuls documents qu'un moteur retient reellement.

    Un document dont le score est nul ne recoit aucune contribution. Sans ce
    filtre, le premier d'une liste de zeros obtiendrait le meilleur score RRF
    possible : une question hors corpus remonterait une fiche au hasard avec
    un score maximal, et le seuil de pertinence ne protegerait plus de rien.
    """
    candidats = [i for i, score in enumerate(scores) if score > minimum]
    candidats.sort(key=lambda i: scores[i], reverse=True)
    return {indice: rang for rang, indice in enumerate(candidats)}


def _est_urgente(question: str) -> bool:
    from survie.index.texte import tokeniser

    return bool(MOTS_URGENCE & set(tokeniser(question)))


class MoteurRecherche:
    def __init__(self, index: IndexDisque, encodeur=None) -> None:
        self.index = index
        self.encodeur = encodeur
        self.bm25 = BM25([f["indexable"] for f in index.fragments])

    def chercher(self, question: str, nombre: int = 6) -> list[Resultat]:
        total = len(self.index.fragments)
        if total == 0:
            return []

        fusion: dict[int, float] = {}

        for indice, rang in _rangs(self.bm25.scores(question)).items():
            fusion[indice] = fusion.get(indice, 0.0) + 1.0 / (K_RRF + rang)

        if self.encodeur is not None and self.index.a_vecteurs:
            vecteur = self.encodeur.encoder([question])[0]
            similarites = self.index.vecteurs @ vecteur
            for indice, rang in _rangs(similarites, SIMILARITE_MINIMALE).items():
                fusion[indice] = fusion.get(indice, 0.0) + 1.0 / (K_RRF + rang)

        # Aucun moteur n'a rien retenu : le corpus ne parle pas du sujet.
        if not fusion:
            return []

        urgente = _est_urgente(question)
        for indice, valeur in fusion.items():
            if urgente:
                criticite = self.index.fragments[indice]["criticite"]
                valeur *= POIDS_CRITICITE.get(criticite, 1.0)
            fusion[indice] = valeur

        meilleurs = sorted(fusion, key=lambda i: fusion[i], reverse=True)[:nombre]
        resultats = []
        for indice in meilleurs:
            fragment = self.index.fragments[indice]
            # Un fragment qu'aucun terme de la question ne touche et que le
            # vectoriel n'a pas non plus fait remonter n'est pas un resultat.
            resultats.append(
                Resultat(
                    reference=fragment["reference"],
                    fiche=fragment["fiche"],
                    titre=fragment["titre"],
                    section=fragment["section"],
                    texte=fragment["texte"],
                    domaine=fragment["domaine"],
                    criticite=fragment["criticite"],
                    sources=fragment["sources"],
                    verifie_le=fragment["verifie_le"],
                    score=fusion[indice],
                )
            )
        return resultats

    def pertinence(self, question: str, resultats: list[Resultat]) -> float:
        """Le corpus traite-t-il reellement le sujet de la question ? (0 a 1)

        Mesure distincte du classement : un premier rang dans une liste de
        resultats tous mauvais ne prouve rien. C'est cette valeur, et non le
        rang, que le seuil de pertinence teste avant d'autoriser une reponse.
        """
        if not resultats:
            return 0.0
        references = {r.reference for r in resultats}
        indices = [
            i for i, f in enumerate(self.index.fragments) if f["reference"] in references
        ]
        return self.bm25.couverture(question, indices)
