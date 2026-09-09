"""Validation de l'en-tete des fiches.

L'en-tete n'est pas decoratif : `criticite` et `delai` pilotent le classement
des resultats, `verifie_le` rend la relecture tracable. Une fiche mal formee
fait echouer la construction de l'index plutot que d'entrer silencieusement
dans le corpus.

L'analyseur ci-dessous couvre le sous-ensemble de YAML reellement utilise
(cles simples, listes en ligne). C'est volontaire : une dependance de moins a
installer sans reseau.
"""

from __future__ import annotations

import datetime as dt

CRITICITES = ("vitale", "haute", "normale")
DELAIS = ("immediat", "jours", "saison", "long-terme")

CHAMPS_OBLIGATOIRES = ("titre", "domaine", "criticite", "delai", "verifie_le")


class FicheInvalide(ValueError):
    """En-tete de fiche absent, mal forme ou incomplet."""


def _valeur(brut: str) -> str | list[str]:
    brut = brut.strip()
    if brut.startswith("[") and brut.endswith("]"):
        interieur = brut[1:-1].strip()
        if not interieur:
            return []
        return [element.strip().strip("\"'") for element in interieur.split(",")]
    return brut.strip("\"'")


def analyser_entete(texte: str, origine: str = "<memoire>") -> tuple[dict, str]:
    """Separe l'en-tete du corps. Renvoie (metadonnees, corps)."""
    lignes = texte.lstrip("﻿").splitlines()
    if not lignes or lignes[0].strip() != "---":
        raise FicheInvalide(f"{origine} : en-tete '---' manquant en premiere ligne.")

    try:
        fin = next(i for i, l in enumerate(lignes[1:], start=1) if l.strip() == "---")
    except StopIteration:
        raise FicheInvalide(f"{origine} : en-tete non referme par '---'.") from None

    metadonnees: dict = {}
    for numero, ligne in enumerate(lignes[1:fin], start=2):
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        if ":" not in ligne:
            raise FicheInvalide(f"{origine}, ligne {numero} : '{ligne}' n'est pas 'cle: valeur'.")
        cle, _, brut = ligne.partition(":")
        metadonnees[cle.strip()] = _valeur(brut)

    return metadonnees, "\n".join(lignes[fin + 1 :]).strip()


def valider(metadonnees: dict, origine: str = "<memoire>") -> dict:
    manquants = [c for c in CHAMPS_OBLIGATOIRES if not metadonnees.get(c)]
    if manquants:
        raise FicheInvalide(f"{origine} : champs manquants : {', '.join(manquants)}.")

    if metadonnees["criticite"] not in CRITICITES:
        raise FicheInvalide(
            f"{origine} : criticite {metadonnees['criticite']!r} inconnue "
            f"(attendu : {', '.join(CRITICITES)})."
        )
    if metadonnees["delai"] not in DELAIS:
        raise FicheInvalide(
            f"{origine} : delai {metadonnees['delai']!r} inconnu "
            f"(attendu : {', '.join(DELAIS)})."
        )
    try:
        dt.date.fromisoformat(str(metadonnees["verifie_le"]))
    except ValueError:
        raise FicheInvalide(
            f"{origine} : verifie_le {metadonnees['verifie_le']!r} n'est pas une date AAAA-MM-JJ."
        ) from None

    for cle in ("prerequis", "sources", "mots_cles"):
        valeur = metadonnees.get(cle, [])
        metadonnees[cle] = valeur if isinstance(valeur, list) else [valeur]

    return metadonnees
