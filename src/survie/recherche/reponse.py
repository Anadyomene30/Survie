"""Assemblage de la reponse : recherche, puis redaction si un LLM est la.

Les quatre niveaux de degradation du systeme se lisent ici : si le corpus ne
contient rien, on refuse ; si le LLM manque, on rend les extraits bruts ;
sinon on redige.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from survie.llm.prompts import REFUS, construire_invite
from survie.recherche.hybride import MoteurRecherche, Resultat


@dataclass
class Reponse:
    texte: str
    extraits: list[Resultat] = field(default_factory=list)
    mode: str = "redige"  # redige | sources | refus

    @property
    def fiches_citees(self) -> list[str]:
        vues: list[str] = []
        for extrait in self.extraits:
            if extrait.fiche not in vues:
                vues.append(extrait.fiche)
        return vues


def formater_extraits(extraits: list[Resultat]) -> str:
    blocs = []
    for extrait in extraits:
        entete = f"[{extrait.fiche}]"
        if extrait.section:
            entete += f" § {extrait.section}"
        blocs.append(f"{entete}\n{extrait.texte}")
    return "\n\n".join(blocs)


def repondre(
    question: str,
    moteur_recherche: MoteurRecherche,
    llm=None,
    nombre_extraits: int = 6,
    seuil: float = 0.12,
) -> Reponse:
    extraits = moteur_recherche.chercher(question, nombre=nombre_extraits)

    # Rien de pertinent : on refuse explicitement plutot que de laisser le
    # modele broder sur des extraits hors sujet.
    if moteur_recherche.pertinence(question, extraits) < seuil:
        return Reponse(texte=REFUS, extraits=[], mode="refus")

    if llm is None:
        return Reponse(
            texte=formater_extraits(extraits), extraits=extraits, mode="sources"
        )

    texte = llm.repondre(construire_invite(question, extraits))
    return Reponse(texte=texte, extraits=extraits, mode="redige")
