"""Mode urgence — checklists servies telles quelles, sans modèle.

Ce chemin ne dépend de RIEN : ni index, ni vecteurs, ni modèle de langue. Il lit
les fichiers Markdown directement. C'est délibéré et c'est la propriété la plus
importante de ce module : si l'index est corrompu, si le modèle refuse de se
charger, si la machine est en train de mourir, les gestes qui sauvent restent
accessibles instantanément.

Rien n'est reformulé, donc rien ne peut être déformé. C'est le chemin le plus
sûr du système, et le seul qui réponde en quelques millisecondes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[2] / "regional" / "urgence"

_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass
class Fiche:
    chemin: Path
    titre: str
    declencheurs: list[str] = field(default_factory=list)
    corps: str = ""

    @property
    def nom(self) -> str:
        return self.chemin.stem


def _plier(t: str) -> str:
    nfkd = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _lire(path: Path) -> Fiche | None:
    texte = path.read_text(encoding="utf-8")
    m = _FRONT.match(texte)
    if not m:
        return None

    entete, corps = m.group(1), texte[m.end():]
    titre, declencheurs = path.stem, []
    for ligne in entete.splitlines():
        if ligne.startswith("titre:"):
            titre = ligne.split(":", 1)[1].strip()
        elif ligne.startswith("declencheurs:"):
            brut = ligne.split(":", 1)[1].strip().strip("[]")
            declencheurs = [d.strip() for d in brut.split(",") if d.strip()]
    return Fiche(path, titre, declencheurs, corps.strip())


def charger(dossier: Path | None = None) -> list[Fiche]:
    dossier = dossier or DOSSIER
    if not dossier.exists():
        return []
    return [f for p in sorted(dossier.glob("*.md")) if (f := _lire(p))]


def chercher(requete: str, fiches: list[Fiche] | None = None) -> list[tuple[Fiche, int]]:
    """Fiches pertinentes, les mieux notées d'abord.

    Notation volontairement simple et lisible. En urgence, un classement qu'on
    ne sait pas expliquer vaut moins qu'un classement grossier mais prévisible :
    l'utilisateur doit pouvoir comprendre pourquoi telle fiche est sortie.
    """
    fiches = fiches if fiches is not None else charger()
    q = _plier(requete)
    mots = [m for m in re.findall(r"[a-z0-9]{3,}", q)]

    notes: list[tuple[Fiche, int]] = []
    for f in fiches:
        note = 0
        for d in f.declencheurs:
            dp = _plier(d)
            if dp in q:
                # Un déclencheur composé (« ne respire pas ») est un signal bien
                # plus fort qu'un mot isolé : il ne se trouve pas par hasard.
                note += 10 if " " in dp else 6
            elif any(mot in dp or dp in mot for mot in mots):
                note += 2
        if any(mot in _plier(f.titre) for mot in mots):
            note += 3
        corps = _plier(f.corps)
        note += sum(1 for mot in set(mots) if mot in corps)
        if note:
            notes.append((f, note))

    notes.sort(key=lambda x: (-x[1], x[0].nom))
    return notes


def rendu(fiche: Fiche, largeur: int = 74) -> str:
    barre = "━" * largeur
    return f"{barre}\n  {fiche.titre.upper()}\n{barre}\n\n{fiche.corps}\n"


def sommaire(fiches: list[Fiche] | None = None) -> str:
    fiches = fiches if fiches is not None else charger()
    if not fiches:
        return "Aucune checklist d'urgence trouvée dans regional/urgence/."
    lignes = ["CHECKLISTS D'URGENCE — servies telles quelles, sans modèle", ""]
    for f in fiches:
        lignes.append(f"  {f.nom:<20} {f.titre}")
    lignes += ["", "  survie urgence <mot>    par exemple : survie urgence saigne"]
    return "\n".join(lignes)
