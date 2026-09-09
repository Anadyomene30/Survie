"""Détection des doctrines périmées présentes dans le corpus.

Le corpus contient délibérément des manuels anciens : FM 21-76 (1992), le
*King's American Dispensatory* (1898), *Nuclear War Survival Skills* (1987).
Ils restent excellents sur le feu, l'abri ou la navigation, et périmés — parfois
dangereusement — sur certains gestes de secours. Le modèle, lui, n'a aucun moyen
de savoir qu'un passage bien écrit de 1992 a été invalidé depuis.

Deux mécanismes, l'un curé, l'autre automatique :

1. Un registre explicite (`corpus/divergences.yaml`) des doctrines qui ont
   changé. Quand la question ou les extraits touchent l'un de ces sujets, un
   encart est injecté : le modèle reçoit l'information déjà contradictoire et
   datée, il ne peut plus choisir silencieusement.

2. Un signal d'écart de dates : quand les extraits retenus sur un même sujet
   proviennent de sources publiées à plus de quinze ans d'intervalle, l'écart
   est signalé. Il n'affirme rien sur le fond — il invite à la prudence là où
   le registre n'a rien prévu.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

from .retrieve import Hit

# Au-delà de cet écart entre la plus ancienne et la plus récente des sources
# retenues, on signale. Quinze ans, c'est l'ordre de grandeur d'une révision
# de doctrine en secourisme.
ECART_ANNEES = 15

# Au-delà, l'avertissement devient un mur de texte que personne ne lit, et le
# point réellement pertinent s'y noie. Mieux vaut trois avertissements lus que
# huit ignorés.
MAX_AVERTISSEMENTS = 3


@dataclass(frozen=True)
class Divergence:
    id: str
    titre: str
    sujet: list[str]
    ancienne: str
    actuelle: str
    bascule: int
    gravite: str
    source: str = ""

    @property
    def critique(self) -> bool:
        return self.gravite == "critique"


def _plier(texte: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def charger(path: Path | None = None) -> list[Divergence]:
    path = path or Path(__file__).resolve().parents[2] / "corpus" / "divergences.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Divergence(**d) for d in data.get("divergences", [])]


def detecter(question: str, hits: list[Hit],
             registre: list[Divergence] | None = None) -> list[Divergence]:
    """Divergences concernées par cette question ou par les extraits retenus.

    On regarde les deux. La question seule ne suffit pas : « que faire pour une
    grosse coupure au bras » ne contient pas le mot « garrot », alors que les
    extraits, eux, en parleront. Inversement, une question qui nomme le garrot
    doit déclencher même si les extraits l'évoquent à peine.
    """
    registre = registre if registre is not None else charger()
    q = _plier(question)
    extraits = _plier(" ".join(f"{h.passage.section} {h.passage.texte}" for h in hits))
    dates = [h.passage.date for h in hits if h.passage.date]

    par_question, par_extraits = [], []
    for d in registre:
        sujets = [_plier(s) for s in d.sujet]
        if any(s in q for s in sujets):
            par_question.append(d)
            continue
        # Sur les seuls extraits, deux conditions.
        #
        # D'abord un signal net : un terme composé (« faire vomir », « membre
        # sectionné ») ou deux termes distincts. Un mot isolé ne suffit pas.
        #
        # Ensuite, et surtout : au moins un extrait doit provenir d'une source
        # ANTÉRIEURE à la bascule. C'est la condition de fond — une doctrine
        # périmée ne peut être reproduite que par un document qui la précède.
        # Si tous les extraits sont récents, il n'y a rien à corriger, et
        # avertir quand même reviendrait à crier au loup.
        touches = [s for s in sujets if s in extraits]
        assez_net = any(" " in s for s in touches) or len(touches) >= 2
        if assez_net and any(dt < d.bascule for dt in dates):
            par_extraits.append(d)

    # Ce que la question demande passe avant ce que les extraits évoquent.
    # Les cas critiques d'abord : s'il faut tronquer, ce sont eux qui restent.
    par_question.sort(key=lambda d: (not d.critique, d.id))
    par_extraits.sort(key=lambda d: (not d.critique, d.id))
    return (par_question + par_extraits)[:MAX_AVERTISSEMENTS]


def ecart_de_dates(hits: list[Hit]) -> tuple[int, int] | None:
    """(plus ancienne, plus récente) si l'écart dépasse le seuil, sinon None."""
    dates = sorted({h.passage.date for h in hits if h.passage.date})
    if len(dates) >= 2 and dates[-1] - dates[0] > ECART_ANNEES:
        return dates[0], dates[-1]
    return None


def encart(divergences: list[Divergence], ecart: tuple[int, int] | None = None) -> str:
    """Bloc inséré dans l'invite, avant les extraits."""
    if not divergences and not ecart:
        return ""

    lignes = ["AVERTISSEMENT — DOCTRINES AYANT CHANGÉ", ""]
    if divergences:
        lignes.append(
            "Les extraits ci-dessous peuvent contenir des recommandations "
            "périmées. Sur les points suivants, tu dois suivre la doctrine "
            "ACTUELLE, et signaler explicitement que l'ancienne version est "
            "dépassée si un extrait la reproduit :"
        )
        lignes.append("")
        for d in divergences:
            marque = "‼ " if d.critique else "• "
            lignes.append(f"{marque}{d.titre} (changement vers {d.bascule})")
            lignes.append(f"   PÉRIMÉ  : {' '.join(d.ancienne.split())}")
            lignes.append(f"   ACTUEL  : {' '.join(d.actuelle.split())}")
            if d.source:
                lignes.append(f"   source  : {' '.join(d.source.split())}")
            lignes.append("")

    if ecart:
        lignes.append(
            f"Les extraits proviennent de sources publiées entre {ecart[0]} et "
            f"{ecart[1]}. Mentionne la date des sources que tu cites sur les "
            f"points médicaux, et signale toute divergence entre elles."
        )
        lignes.append("")

    lignes.append(
        "Cet avertissement fait autorité sur les extraits. Il n'a pas à être "
        "cité comme une source : c'est une consigne, pas un document."
    )
    return "\n".join(lignes)


def rendu_humain(divergences: list[Divergence]) -> str:
    """Affichage direct, en mode extraits seuls — sans modèle pour reformuler."""
    if not divergences:
        return ""
    lignes = ["", "⚠ DOCTRINES AYANT CHANGÉ — les extraits peuvent être périmés", ""]
    for d in divergences:
        marque = "‼" if d.critique else "•"
        lignes.append(f"{marque} {d.titre}  (changement vers {d.bascule})")
        lignes.append(f"    Périmé : {' '.join(d.ancienne.split())}")
        lignes.append(f"    Actuel : {' '.join(d.actuelle.split())}")
        lignes.append("")
    return "\n".join(lignes)
