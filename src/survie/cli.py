"""Interface en ligne de commande."""

from __future__ import annotations

import argparse
import subprocess
import sys

from survie import config as configuration
from survie.corpus.loader import charger_fiches
from survie.index.embeddings import EmbeddingsIndisponibles, Encodeur
from survie.index.store import IndexDisque
from survie.llm.moteur import LLMIndisponible, Moteur
from survie.recherche.hybride import MoteurRecherche
from survie.recherche.reponse import repondre
from survie.urgence.protocoles import fiches_vitales, filtrer

SEUIL_BATTERIE = 25


def niveau_batterie() -> int | None:
    """Pourcentage de batterie sur macOS, None si indeterminable."""
    try:
        sortie = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5, check=True
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for morceau in sortie.split():
        if morceau.endswith("%;"):
            try:
                return int(morceau.rstrip("%;"))
            except ValueError:
                return None
    return None


def _charger_moteur(config, avec_llm: bool):
    """Prepare la recherche, et le LLM s'il est demande et disponible."""
    index = IndexDisque.lire(configuration.DOSSIER_INDEX)

    encodeur = None
    if index.a_vecteurs:
        try:
            encodeur = Encodeur(config.chemin_embeddings, config.embeddings_dimension)
        except EmbeddingsIndisponibles:
            pass  # BM25 seul : degrade mais operationnel

    llm = None
    if avec_llm:
        try:
            llm = Moteur(config.profil.chemin_llm, config.profil.contexte)
        except LLMIndisponible as erreur:
            print(f"[mode sources seules] {erreur}\n", file=sys.stderr)

    return MoteurRecherche(index, encodeur), llm


def commande_index(args) -> int:
    from survie.index.build import construire

    config = configuration.charger(args.profil)
    construire(
        config,
        configuration.DOSSIER_CONNAISSANCES,
        configuration.DOSSIER_INDEX,
        avec_vecteurs=not args.sans_vecteurs,
    )
    return 0


def commande_demande(args) -> int:
    config = configuration.charger(args.profil)
    question = " ".join(args.question)

    avec_llm = not args.sources_seules
    batterie = niveau_batterie()
    if avec_llm and batterie is not None and batterie < SEUIL_BATTERIE:
        print(
            f"Batterie a {batterie} % : le modele consomme beaucoup. "
            "Utilisez --sources-seules pour economiser.\n",
            file=sys.stderr,
        )

    moteur_recherche, llm = _charger_moteur(config, avec_llm)
    reponse = repondre(
        question,
        moteur_recherche,
        llm=llm,
        nombre_extraits=config.extraits,
        seuil=config.seuil_pertinence,
    )

    print(reponse.texte)
    if reponse.mode == "redige" and reponse.fiches_citees:
        print("\nFiches consultees : " + ", ".join(reponse.fiches_citees))
    return 0 if reponse.mode != "refus" else 2


def commande_urgence(args) -> int:
    fiches = filtrer(fiches_vitales(configuration.DOSSIER_CONNAISSANCES), args.terme)
    if not fiches:
        print(f"Aucune fiche vitale ne correspond a {args.terme!r}.")
        return 2

    if args.liste or len(fiches) > 1 and not args.terme:
        for fiche in fiches:
            print(f"  {fiche.identifiant:<52} {fiche.titre}")
        print(f"\n{len(fiches)} fiches vitales. Affichez-en une : survie urgence <mot>")
        return 0

    for fiche in fiches:
        print(f"\n{'=' * 70}\n{fiche.titre}  [{fiche.identifiant}]\n{'=' * 70}\n")
        print(fiche.corps)
    return 0


def commande_domaines(args) -> int:
    fiches = charger_fiches(configuration.DOSSIER_CONNAISSANCES)
    domaines: dict[str, int] = {}
    for fiche in fiches:
        domaines[fiche.domaine] = domaines.get(fiche.domaine, 0) + 1
    print(f"{len(fiches)} fiches, {len(domaines)} domaines :\n")
    for domaine, nombre in sorted(domaines.items()):
        print(f"  {domaine:<28} {nombre:>3} fiche(s)")
    return 0


def commande_etat(args) -> int:
    config = configuration.charger(args.profil)
    memoire = configuration.memoire_totale_go()
    batterie = niveau_batterie()

    print(f"Profil            : {config.profil.nom} — {config.profil.description}")
    print(f"Memoire detectee  : {memoire:.1f} Go")
    if batterie is not None:
        print(f"Batterie          : {batterie} %")

    llm = config.profil.chemin_llm
    emb = config.chemin_embeddings
    print(f"Modele LLM        : {'present' if llm.exists() else 'ABSENT'} — {llm.name}")
    print(f"Modele embeddings : {'present' if emb.exists() else 'ABSENT'} — {emb.name}")

    try:
        index = IndexDisque.lire(configuration.DOSSIER_INDEX)
        vect = "lexical + vectoriel" if index.a_vecteurs else "lexical seul"
        print(f"Index             : {len(index.fragments)} fragments ({vect})")
    except FileNotFoundError:
        print("Index             : ABSENT — lancez : survie index")

    try:
        print(f"Corpus            : {len(charger_fiches(configuration.DOSSIER_CONNAISSANCES))} fiches")
    except Exception as erreur:  # corpus invalide : il faut le voir tout de suite
        print(f"Corpus            : ERREUR — {erreur}")
        return 1
    return 0


def commande_web(args) -> int:
    from survie.web.serveur import lancer

    return lancer(args.profil, args.hote, args.port)


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(
        prog="survie",
        description="Assistant de survie local, hors-ligne.",
    )
    analyseur.add_argument("--profil", choices=configuration.PROFILS_CONNUS, default=None)
    sous = analyseur.add_subparsers(dest="commande", required=True)

    p = sous.add_parser("index", help="construire l'index a partir du corpus")
    p.add_argument("--sans-vecteurs", action="store_true", help="index lexical seul")
    p.set_defaults(fonction=commande_index)

    p = sous.add_parser("demande", help="poser une question")
    p.add_argument("question", nargs="+")
    p.add_argument("--sources-seules", action="store_true",
                   help="extraits bruts, sans LLM (economise la batterie)")
    p.set_defaults(fonction=commande_demande)

    p = sous.add_parser("urgence", help="fiches vitales, sans index ni modele")
    p.add_argument("terme", nargs="?", default=None)
    p.add_argument("--liste", action="store_true", help="lister sans afficher le contenu")
    p.set_defaults(fonction=commande_urgence)

    p = sous.add_parser("domaines", help="lister les domaines couverts")
    p.set_defaults(fonction=commande_domaines)

    p = sous.add_parser("etat", help="verifier l'installation")
    p.set_defaults(fonction=commande_etat)

    p = sous.add_parser("web", help="interface web locale")
    p.add_argument("--hote", default="127.0.0.1",
                   help="0.0.0.0 pour ouvrir aux autres appareils du reseau local")
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(fonction=commande_web)

    args = analyseur.parse_args(argv)
    try:
        return args.fonction(args)
    except (FileNotFoundError, ValueError) as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
