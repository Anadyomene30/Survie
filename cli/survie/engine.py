"""Assemblage : question -> recherche -> génération -> vérification."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import divergence as divergence_mod
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
# Le refus se joue à deux niveaux, et il faut bien voir lequel fait le travail.
#
# NIVEAU 1 — filtre rapide, ici. Il évite de charger un modèle de 13 Go et de
# générer 900 tokens pour une question manifestement hors sujet.
#
# NIVEAU 2 — le modèle lui-même, en mode RAG strict. Recevant des extraits sans
# rapport, il conclut qu'il ne peut pas répondre. C'est LE vrai garde-fou :
# c'est le seul qui passe à l'échelle.
#
# Pourquoi cette hiérarchie. La couverture lexicale est une heuristique qui se
# dégrade à mesure que le corpus grandit. Mesuré ici : sur 54 fragments elle
# séparait proprement ; à 85 fragments, « capitale du Kazakhstan » passait déjà,
# parce que « capitale » apparaît dans « l'heure de début est capitale », et
# « soufflé au fromage » aussi, parce que « souffl* » attrape « souffle ». Ce
# sont des homographes : aucune méthode lexicale ne peut les écarter. Sur un
# corpus réel de plusieurs dizaines de milliers de fragments, à peu près tout
# mot français se trouvera quelque part et la couverture vaudra ~1 partout.
#
# La conséquence est assumée : le filtre lexical attrape le grossier (Fourier,
# common rail, écris-moi un poème) et laisse passer le reste au modèle. Le
# cosinus, lui, ne se dégrade pas avec la taille du corpus — c'est le critère
# qui compte dès qu'un vrai modèle sémantique est présent.
#
# Des deux erreurs, le faux refus reste la plus grave : il prive d'aide
# quelqu'un dont la question EST couverte. D'où un seuil bas.
SEUIL_COUVERTURE = 0.20
SEUIL_COSINUS = 0.60      # similarité sémantique maximale jugée probante


def charger_embedder(sans_vecteurs: bool = False):
    """Embedder de requête, ou None si aucun backend utilisable n'est présent.

    Aucune raison de s'arrêter là : sans vecteurs la recherche reste plein
    texte, dégradée mais utilisable — et c'est exactement le mode dans lequel
    tourne une machine sans MLX. Le refuser ferait échouer `survie ask` et
    `make eval` sur une installation partielle, au lieu de rendre ce qu'on peut.

    On attrape plus large qu'ImportError : une bibliothèque installée mais
    incompatible avec la version de son moteur lève autre chose (vu ici :
    `AttributeError` à l'import de mlx_lm). Du point de vue de l'utilisateur
    c'est la même panne — le backend n'est pas utilisable — et la conduite à
    tenir est la même.
    """
    if sans_vecteurs:
        return None
    from ingest.embed import get_embedder

    try:
        return get_embedder()
    except Exception as e:
        print(f"  aucun backend d'embeddings ({e}) : recherche plein texte seule, "
              "sans reformulation sémantique.\n"
              "  Sur Mac : uv sync --extra mlx", file=sys.stderr)
        return None


@dataclass
class Reponse:
    question: str
    texte: str
    hits: list[retrieve.Hit]
    rapport: Rapport | None = None
    refus: bool = False
    identification: bool = False
    divergences: list = field(default_factory=list)
    ecart_dates: tuple[int, int] | None = None
    meta: dict = field(default_factory=dict)


class Engine:
    def __init__(self, db: Path, llm: LLM | None = None, embedder=None,
                 registre: list | None = None):
        self.store = Store(db)
        self.llm = llm or NoLLM()
        self.embedder = embedder
        # Chargé une fois : le registre est relu à chaque question sinon.
        self.registre = registre if registre is not None else divergence_mod.charger()
        if embedder is not None:
            # Refuse tôt un index construit avec un autre modèle : les résultats
            # seraient du bruit, sans le moindre signal d'erreur. Le nom et le
            # backend sont des déclarations ; le témoin est une mesure.
            self.store.check_embedder(embedder.name,
                                      getattr(embedder, "backend", None))
            from ingest.embed import PHRASE_TEMOIN

            self.store.check_temoin(embedder.encode([PHRASE_TEMOIN])[0])

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

        divs = divergence_mod.detecter(question, hits, self.registre)
        ecart = divergence_mod.ecart_de_dates(hits)
        encart = divergence_mod.encart(divs, ecart)

        systeme, utilisateur = prompt_mod.build(question, hits, encart)
        texte = self.llm.generate(systeme, utilisateur)

        if not texte.strip():
            # Mode extraits seuls : on rend les passages tels quels. Rien n'est
            # reformulé, donc rien n'est à vérifier.
            return Reponse(question, "", hits, identification=ident,
                           divergences=divs, ecart_dates=ecart,
                           meta={"mode": "extraits"})

        rapport = verifier(texte, hits)
        return Reponse(question, texte, hits, rapport, identification=ident,
                       divergences=divs, ecart_dates=ecart,
                       meta={"modele": self.llm.name})

    def _doit_refuser(self, sig: retrieve.Signaux) -> bool:
        """Filtre rapide. Le modèle en mode RAG strict reste le garde-fou de fond."""
        semantique = self.embedder is not None and not self.embedder.name.startswith(
            "hashing-")
        if semantique:
            # Le cosinus prime : il ne se dégrade pas avec la taille du corpus.
            # On n'exige la faiblesse lexicale qu'en complément, pour ne pas
            # refuser une reformulation inhabituelle mais bien couverte.
            return sig.cos_max < SEUIL_COSINUS and sig.couverture < SEUIL_COUVERTURE
        # Sans modèle sémantique, la couverture décide seule — en sachant qu'elle
        # laissera passer les homographes. Voir le commentaire des seuils.
        return sig.couverture < SEUIL_COUVERTURE

    def _message_refus(self, sig: retrieve.Signaux) -> str:
        msg = prompt_mod.REFUS
        if sig.termes_inconnus:
            liste = ", ".join(f"« {t} »" for t in sig.termes_inconnus[:6])
            msg += (f"\n\nAucun ouvrage indexé ne contient {liste}. "
                    f"Couverture de la question : {sig.couverture:.0%}.")
        return msg

    def close(self) -> None:
        self.store.close()
