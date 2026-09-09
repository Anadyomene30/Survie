"""Lecture des fiches markdown du dossier connaissances/."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from survie.corpus.schema import analyser_entete, valider


@dataclass(frozen=True)
class Fiche:
    identifiant: str          # chemin relatif, sert de reference citable
    titre: str
    domaine: str
    criticite: str
    delai: str
    verifie_le: str
    corps: str
    prerequis: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    mots_cles: list[str] = field(default_factory=list)


def lire_fiche(chemin: Path, racine: Path) -> Fiche:
    identifiant = chemin.relative_to(racine).as_posix()
    metadonnees, corps = analyser_entete(chemin.read_text(encoding="utf-8"), identifiant)
    metadonnees = valider(metadonnees, identifiant)
    return Fiche(
        identifiant=identifiant,
        titre=metadonnees["titre"],
        domaine=metadonnees["domaine"],
        criticite=metadonnees["criticite"],
        delai=metadonnees["delai"],
        verifie_le=str(metadonnees["verifie_le"]),
        corps=corps,
        prerequis=metadonnees["prerequis"],
        sources=metadonnees["sources"],
        mots_cles=metadonnees["mots_cles"],
    )


def charger_fiches(racine: Path) -> list[Fiche]:
    """Toutes les fiches du corpus, triees par identifiant (ordre reproductible)."""
    if not racine.exists():
        raise FileNotFoundError(f"Dossier de connaissances introuvable : {racine}")
    return [lire_fiche(c, racine) for c in sorted(racine.rglob("*.md"))]
