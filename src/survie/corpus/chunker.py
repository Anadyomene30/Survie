"""Decoupage des fiches en fragments indexables.

On decoupe sur les titres de section markdown plutot qu'a longueur fixe : une
section correspond deja a une unite de sens ("Methode", "Dosage", "Pieges"),
et un fragment ainsi obtenu reste comprehensible seul quand il est cite.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from survie.corpus.loader import Fiche

# Un fragment trop long dilue le contexte du LLM, trop court perd le sens.
TAILLE_MAX = 1200
TAILLE_MIN = 80

_TITRE = re.compile(r"^(#{2,4})\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Fragment:
    fiche: Fiche
    section: str
    texte: str

    @property
    def reference(self) -> str:
        if self.section:
            return f"{self.fiche.identifiant} § {self.section}"
        return self.fiche.identifiant

    @property
    def texte_indexable(self) -> str:
        """Le titre de la fiche est repete dans chaque fragment.

        Sans cela, un fragment "Faire bouillir 1 minute a gros bouillons" ne
        contient pas le mot "eau" et devient introuvable.
        """
        entete = f"{self.fiche.titre} — {self.section}" if self.section else self.fiche.titre
        mots_cles = " ".join(self.fiche.mots_cles)
        return f"{entete}\n{self.fiche.domaine} {mots_cles}\n{self.texte}"


def _couper_long(texte: str) -> list[str]:
    """Recoupe une section trop longue sur les paragraphes."""
    if len(texte) <= TAILLE_MAX:
        return [texte]
    morceaux: list[str] = []
    courant = ""
    for paragraphe in texte.split("\n\n"):
        if courant and len(courant) + len(paragraphe) + 2 > TAILLE_MAX:
            morceaux.append(courant.strip())
            courant = paragraphe
        else:
            courant = f"{courant}\n\n{paragraphe}" if courant else paragraphe
    if courant.strip():
        morceaux.append(courant.strip())
    return morceaux


def decouper(fiche: Fiche) -> list[Fragment]:
    positions = [(m.start(), m.group(2).strip()) for m in _TITRE.finditer(fiche.corps)]

    sections: list[tuple[str, str]] = []
    preambule = fiche.corps[: positions[0][0]] if positions else fiche.corps
    if preambule.strip():
        sections.append(("", preambule.strip()))

    for rang, (debut, titre) in enumerate(positions):
        fin = positions[rang + 1][0] if rang + 1 < len(positions) else len(fiche.corps)
        contenu = fiche.corps[debut:fin]
        contenu = contenu.split("\n", 1)[1] if "\n" in contenu else ""
        if contenu.strip():
            sections.append((titre, contenu.strip()))

    fragments: list[Fragment] = []
    for titre, contenu in sections:
        for morceau in _couper_long(contenu):
            if len(morceau) >= TAILLE_MIN:
                fragments.append(Fragment(fiche=fiche, section=titre, texte=morceau))

    # Une fiche tres courte ne doit pas disparaitre du corpus.
    if not fragments and fiche.corps.strip():
        fragments.append(Fragment(fiche=fiche, section="", texte=fiche.corps.strip()))
    return fragments
