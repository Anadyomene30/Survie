"""Acces direct aux fiches vitales, sans index ni modele.

Troisieme niveau de degradation : si l'index n'est pas construit, si NumPy
manque, si le modele a ete efface pour faire de la place, cette commande
fonctionne encore. Elle ne fait que lire des fichiers.
"""

from __future__ import annotations

from pathlib import Path

from survie.corpus.loader import charger_fiches
from survie.index.texte import deplier


def fiches_vitales(dossier: Path) -> list:
    fiches = [f for f in charger_fiches(dossier) if f.criticite == "vitale"]
    ordre = {"immediat": 0, "jours": 1, "saison": 2, "long-terme": 3}
    return sorted(fiches, key=lambda f: (ordre.get(f.delai, 9), f.identifiant))


def filtrer(fiches: list, terme: str | None) -> list:
    """Filtre simple par sous-chaine, insensible aux accents et a la casse."""
    if not terme:
        return fiches
    cible = deplier(terme)
    return [
        f
        for f in fiches
        if cible in deplier(f"{f.titre} {f.domaine} {f.identifiant} {' '.join(f.mots_cles)}")
    ]
