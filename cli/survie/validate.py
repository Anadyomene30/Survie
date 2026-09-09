"""Vérification a posteriori des citations produites par le modèle.

C'est le garde-fou principal du système. Un modèle contraint par une consigne
peut malgré tout inventer une référence plausible — c'est même le mode d'échec
le plus insidieux, parce qu'une citation fabriquée donne à une phrase fausse
l'apparence d'une phrase vérifiée. Ici, chaque citation est confrontée aux
extraits réellement transmis : ce qui ne correspond à rien est signalé.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .retrieve import Hit

# [identifiant p.42] — l'identifiant suit la convention du manifeste.
CITATION = re.compile(r"\[([a-z0-9][a-z0-9._-]*)\s+p\.\s*(\d+)\]", re.I)

# Découpage en phrases, pour localiser les affirmations non sourcées.
#
# Subtilité : la citation suit le point final (« … au froissement. [src p.3] »),
# et elle contient elle-même un point. Un découpage naïf sur la ponctuation
# détacherait donc la citation de la phrase qu'elle source, et le validateur
# signalerait comme non sourcée une phrase parfaitement citée. On masque donc
# les citations avant de découper, puis on rattache à chaque phrase les
# citations qui la suivent immédiatement.
_MASQUE = "\x00{}\x00"
_MASQUE_RE = re.compile(r"\x00\d+\x00")
PHRASE = re.compile(r"[^.!?\n]+[.!?]*(?:\s*\x00\d+\x00)*")


def _phrases(texte: str) -> list[str]:
    """Phrases du texte, chacune accompagnée des citations qui la suivent."""
    citations: list[str] = []

    def _masquer(m: re.Match) -> str:
        citations.append(m.group(0))
        return _MASQUE.format(len(citations) - 1)

    masque = CITATION.sub(_masquer, texte)
    out = []
    for brut in PHRASE.findall(masque):
        out.append(_MASQUE_RE.sub(lambda m: citations[int(m.group(0).strip("\x00"))], brut))
    return out


@dataclass
class Probleme:
    genre: str          # "source-inconnue" | "page-hors-extrait" | "phrase-sans-source"
    detail: str
    extrait: str


@dataclass
class Rapport:
    citations: int
    valides: int
    problemes: list[Probleme]

    @property
    def ok(self) -> bool:
        return not self.problemes

    @property
    def taux(self) -> float:
        return self.valides / self.citations if self.citations else 0.0


def _pages_autorisees(hits: list[Hit]) -> dict[str, set[int]]:
    """Pages réellement transmises, par source.

    On accepte toute la plage page_debut..page_fin : un fragment qui enjambe
    une fin de page autorise légitimement la citation des deux pages.
    """
    autorisees: dict[str, set[int]] = {}
    for h in hits:
        p = h.passage
        autorisees.setdefault(p.source_id, set()).update(
            range(p.page_debut, p.page_fin + 1)
        )
    return autorisees


def verifier(reponse: str, hits: list[Hit], *, exiger_source_par_phrase: bool = True) -> Rapport:
    autorisees = _pages_autorisees(hits)
    problemes: list[Probleme] = []
    total = valides = 0

    for m in CITATION.finditer(reponse):
        total += 1
        sid, page = m.group(1).lower(), int(m.group(2))
        if sid not in autorisees:
            problemes.append(Probleme(
                "source-inconnue",
                f"« {sid} » ne fait pas partie des extraits transmis",
                m.group(0)))
        elif page not in autorisees[sid]:
            pages = sorted(autorisees[sid])
            problemes.append(Probleme(
                "page-hors-extrait",
                f"« {sid} » a été transmis pour la ou les pages "
                f"{_resume(pages)}, pas la page {page}",
                m.group(0)))
        else:
            valides += 1

    if exiger_source_par_phrase:
        for phrase in _phrases(reponse):
            texte = phrase.strip()
            # On ne réclame pas de source aux titres, listes vides, transitions
            # courtes et à la formule de prudence imposée par la règle de sûreté.
            if len(texte) < 45 or texte.startswith(("#", "-", "*")):
                continue
            if "doute" in texte.lower() and "abstenir" in texte.lower():
                continue
            if not CITATION.search(texte):
                problemes.append(Probleme(
                    "phrase-sans-source",
                    "affirmation sans citation",
                    texte[:110]))

    return Rapport(total, valides, problemes)


def _resume(pages: list[int]) -> str:
    if len(pages) <= 4:
        return ", ".join(str(p) for p in pages)
    return f"{pages[0]}–{pages[-1]}"


def annoter(reponse: str, rapport: Rapport) -> str:
    """Ajoute un avertissement lisible quand la vérification échoue."""
    if rapport.ok:
        return reponse
    lignes = ["", "⚠ VÉRIFICATION DES CITATIONS — problèmes détectés :"]
    for p in rapport.problemes:
        lignes.append(f"  • {p.genre} : {p.detail}")
        lignes.append(f"    dans : {p.extrait}")
    lignes.append("")
    lignes.append("  Une citation invalide signale une réponse potentiellement")
    lignes.append("  inventée. Vérifie directement les extraits ci-dessous.")
    return reponse + "\n" + "\n".join(lignes)
