"""Assemblage : question -> recherche -> génération -> vérification."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import prompt as prompt_mod
from . import retrieve
from .llm import LLM, NoLLM
from .store import Store
from .validate import Rapport, verifier

# Refus : le corpus ne couvre pas la question.
#
# Les deux conditions doivent être réunies pour refuser. Exiger les deux évite
# les faux refus : une reformulation inhabituelle fait chuter la couverture
# lexicale, mais un vrai modèle sémantique la rattrape par le cosinus.
# Seuil bas et délibérément prudent. Des deux erreurs possibles, le faux refus
# est la plus grave : il prive d'aide quelqu'un dont la question EST couverte.
# Un faux accès, lui, dégrade proprement — le modèle reçoit des extraits hors
# sujet et conclut de lui-même qu'il ne peut pas répondre.
# Mesuré sur le corpus : questions couvertes 0,27 à 1,00 ; hors corpus 0,00 à 0,36.
SEUIL_COUVERTURE = 0.20
SEUIL_COSINUS = 0.60      # similarité sémantique maximale jugée probante


@dataclass
class Reponse:
    question: str
    texte: str
    hits: list[retrieve.Hit]
    rapport: Rapport | None = None
    refus: bool = False
    identification: bool = False
    meta: dict = field(default_factory=dict)


class Engine:
    def __init__(self, db: Path, llm: LLM | None = None, embedder=None):
        self.store = Store(db)
        self.llm = llm or NoLLM()
        self.embedder = embedder
        if embedder is not None:
            # Refuse tôt un index construit avec un autre modèle : les résultats
            # seraient du bruit, sans le moindre signal d'erreur.
            self.store.check_embedder(embedder.name)

    def _qvec(self, question: str) -> np.ndarray | None:
        if self.embedder is None:
            return None
        return self.embedder.encode([question], is_query=True)[0]

    def ask(self, question: str, k: int = retrieve.RETENUS) -> Reponse:
        hits = retrieve.search(self.store, question, self._qvec(question), k=k)
        ident = prompt_mod.is_identification(question)

        sig = retrieve.signaux(self.store, question, self._qvec(question))
        if not hits or self._doit_refuser(sig):
            return Reponse(question, self._message_refus(sig), hits, refus=True,
                           identification=ident, meta={"signaux": sig})

        systeme, utilisateur = prompt_mod.build(question, hits)
        texte = self.llm.generate(systeme, utilisateur)

        if not texte.strip():
            # Mode extraits seuls : on rend les passages tels quels. Rien n'est
            # reformulé, donc rien n'est à vérifier.
            return Reponse(question, "", hits, identification=ident,
                           meta={"mode": "extraits"})

        rapport = verifier(texte, hits)
        return Reponse(question, texte, hits, rapport, identification=ident,
                       meta={"modele": self.llm.name})

    def _doit_refuser(self, sig: retrieve.Signaux) -> bool:
        if sig.couverture >= SEUIL_COUVERTURE:
            return False
        # Sans modèle sémantique (backend de test, ou recherche plein texte
        # seule), le cosinus n'est pas exploitable : la couverture décide seule.
        if self.embedder is None or self.embedder.name.startswith("hashing-"):
            return True
        return sig.cos_max < SEUIL_COSINUS

    def _message_refus(self, sig: retrieve.Signaux) -> str:
        msg = prompt_mod.REFUS
        if sig.termes_inconnus:
            liste = ", ".join(f"« {t} »" for t in sig.termes_inconnus[:6])
            msg += (f"\n\nAucun ouvrage indexé ne contient {liste}. "
                    f"Couverture de la question : {sig.couverture:.0%}.")
        return msg

    def close(self) -> None:
        self.store.close()
