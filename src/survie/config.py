"""Chargement de la configuration et detection du profil materiel.

Aucun acces reseau ici, ni ailleurs dans le chemin de reponse : tout se lit
sur disque.
"""

from __future__ import annotations

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
CHEMIN_PROFILS = RACINE / "config" / "profils.toml"
DOSSIER_CONNAISSANCES = RACINE / "connaissances"
DOSSIER_MODELES = RACINE / "modeles"
DOSSIER_INDEX = RACINE / "index"

PROFILS_CONNUS = ("leger", "standard", "confort")


@dataclass(frozen=True)
class Profil:
    """Un profil materiel : quel modele charger et avec quel contexte."""

    nom: str
    description: str
    llm_depot: str
    llm_fichier: str
    llm_taille_go: float
    contexte: int
    ram_minimale_go: int

    @property
    def chemin_llm(self) -> Path:
        return DOSSIER_MODELES / self.llm_fichier


@dataclass(frozen=True)
class Config:
    profil: Profil
    embeddings_depot: str
    embeddings_fichier: str
    embeddings_dimension: int
    extraits: int
    seuil_pertinence: float

    @property
    def chemin_embeddings(self) -> Path:
        return DOSSIER_MODELES / self.embeddings_fichier


def memoire_totale_go() -> float:
    """Memoire vive de la machine, en Go. 0.0 si indeterminable."""
    try:
        sortie = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return int(sortie.stdout.strip()) / 1024**3
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    # Repli Linux, utile pour les tests et une eventuelle machine de secours.
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for ligne in meminfo.read_text().splitlines():
            if ligne.startswith("MemTotal:"):
                return int(ligne.split()[1]) / 1024**2
    return 0.0


def detecter_profil(profils: dict[str, dict]) -> str:
    """Choisit le profil le plus ambitieux que la memoire permet.

    En cas de doute on descend d'un cran : un modele qui ne tient pas en
    memoire fait ramer la machine au pire moment.
    """
    memoire = memoire_totale_go()
    if memoire <= 0:
        return "standard"
    for nom in reversed(PROFILS_CONNUS):
        if memoire >= profils[nom]["ram_minimale_go"]:
            return nom
    return "leger"


def charger(nom_profil: str | None = None) -> Config:
    with CHEMIN_PROFILS.open("rb") as flux:
        brut = tomllib.load(flux)

    profils = {nom: brut[nom] for nom in PROFILS_CONNUS}
    nom = nom_profil or detecter_profil(profils)
    if nom not in profils:
        connus = ", ".join(PROFILS_CONNUS)
        raise ValueError(f"Profil inconnu : {nom!r}. Profils disponibles : {connus}.")

    return Config(
        profil=Profil(nom=nom, **profils[nom]),
        embeddings_depot=brut["embeddings"]["depot"],
        embeddings_fichier=brut["embeddings"]["fichier"],
        embeddings_dimension=brut["embeddings"]["dimension"],
        extraits=brut["recherche"]["extraits"],
        seuil_pertinence=brut["recherche"]["seuil_pertinence"],
    )
