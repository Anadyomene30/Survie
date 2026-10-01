#!/usr/bin/env python3
"""Vérifie que les moteurs Python et Swift renvoient les MÊMES extraits.

Pourquoi ce script existe.

Le moteur vit en deux exemplaires : Python, où l'on met la recherche au point
et où tourne `eval/golden.yaml`, et Swift, qui est ce que l'utilisateur exécute
réellement. Mettre au point la recherche en Python n'est légitime qu'à une
condition : que les deux implémentations donnent le même classement. Sinon
l'évaluation ne décrit plus l'application — elle décrit un prototype que
personne n'utilise, et chaque réglage validé en Python est une supposition.

Cette condition était affirmée dans le README et dans docs/DEMARRAGE-MAC.md ;
elle n'était vérifiée par rien. Ce script la mesure, question par question, sur
tout le jeu d'évaluation.

    python3 scripts/parite.py                    # sur build/survie.db
    python3 scripts/parite.py --db autre.db --verbeux

PORTÉE — recherche plein texte seule. Les deux moteurs sont comparés SANS
vecteurs, parce qu'ils n'ont pas le même embedder disponible : côté Python le
repli « hashing » existe, côté Swift l'embedder est fourni par MLX ou absent.
Comparer un moteur vectorisé à un moteur lexical ne mesurerait rien.

Ce que cela couvre quand même : la requête FTS5 et sa troncature morphologique,
le classement BM25, la fusion RRF, les sièges garantis, la pondération
éditoriale, la couverture lexicale pondérée par la rareté, et le seuil de
refus. C'est-à-dire tout ce qui a été porté à la main d'un langage à l'autre,
et donc tout ce qui peut diverger silencieusement.

Ce que cela ne couvre pas : le classement vectoriel. Il faudra le vérifier une
fois MLX branché des deux côtés, en construisant l'index avec le modèle validé
par scripts/valider-embedder.py et en le passant aux deux moteurs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cli"))

import yaml  # noqa: E402

APP = ROOT / "app"
BINAIRE = APP / ".build" / "debug" / "survie-cli"

# Les scores sont calculés en double des deux côtés, avec les mêmes opérations
# dans le même ordre : ils doivent coïncider au bit près. On tolère malgré tout
# l'erreur d'arrondi d'un aller-retour par JSON, pas davantage — un écart plus
# large signale une différence de formule, pas de représentation.
TOLERANCE = 1e-9


def construire_cli() -> Path:
    """Compile le CLI Swift si besoin. Aucune dépendance externe, aucun réseau."""
    if BINAIRE.exists():
        return BINAIRE
    print("Compilation du CLI Swift…")
    r = subprocess.run(["swift", "build", "--product", "survie-cli"],
                       cwd=APP, capture_output=True, text=True)
    if r.returncode != 0 or not BINAIRE.exists():
        print(r.stdout[-3000:])
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit("Le CLI Swift ne compile pas — corrige-le avant la parité.")
    return BINAIRE


def cote_swift(db: Path, question: str) -> dict:
    r = subprocess.run([str(BINAIRE), "--json", str(db), question],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"survie-cli a échoué sur « {question} » :\n{r.stderr}")
    return json.loads(r.stdout)


def cote_python(engine, question: str) -> dict:
    from survie import retrieve

    rep = engine.ask(question)
    # Le moteur ne remonte les signaux que dans son message de refus ; on les
    # recalcule pour pouvoir les comparer aussi sur les questions acceptées,
    # où une divergence de couverture est justement invisible à l'écran.
    sig = retrieve.signaux(engine.store, question, None)
    return {
        "question": question,
        "refus": rep.refus,
        "identification": rep.identification,
        "couverture": round(sig.couverture, 9),
        "termesInconnus": list(sig.termes_inconnus),
        "hits": [{"citation": h.passage.citation,
                  "section": h.passage.section,
                  "score": round(h.score, 9),
                  "methodes": h.methodes} for h in rep.hits],
    }


def comparer(py: dict, sw: dict) -> list[str]:
    """Renvoie la liste des écarts. Vide = parité stricte sur cette question."""
    ecarts: list[str] = []

    for champ in ("refus", "identification"):
        if py[champ] != sw[champ]:
            ecarts.append(f"{champ} : python={py[champ]} swift={sw[champ]}")

    if abs(py["couverture"] - sw["couverture"]) > TOLERANCE:
        ecarts.append(f"couverture : python={py['couverture']:.6f} "
                      f"swift={sw['couverture']:.6f}")

    # Les termes inconnus sont nommés à l'utilisateur dans le message de refus :
    # une divergence ici se voit directement à l'écran.
    if sorted(py["termesInconnus"]) != sorted(sw["termesInconnus"]):
        ecarts.append(f"termes inconnus : python={py['termesInconnus']} "
                      f"swift={sw['termesInconnus']}")

    hp, hs = py["hits"], sw["hits"]
    if len(hp) != len(hs):
        ecarts.append(f"nombre d'extraits : python={len(hp)} swift={len(hs)}")

    for i, (a, b) in enumerate(zip(hp, hs), start=1):
        if a["citation"] != b["citation"] or a["section"] != b["section"]:
            ecarts.append(f"rang {i} : python={a['citation']} « {a['section']} » "
                          f"≠ swift={b['citation']} « {b['section']} »")
        elif a["methodes"] != b["methodes"]:
            ecarts.append(f"rang {i} {a['citation']} : méthodes "
                          f"python={a['methodes']} swift={b['methodes']}")
        elif abs(a["score"] - b["score"]) > TOLERANCE:
            ecarts.append(f"rang {i} {a['citation']} : score "
                          f"python={a['score']:.9f} swift={b['score']:.9f}")
    return ecarts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=ROOT / "build" / "survie.db")
    ap.add_argument("--golden", type=Path, default=ROOT / "eval" / "golden.yaml")
    ap.add_argument("--verbeux", action="store_true",
                    help="affiche aussi les questions en parité")
    args = ap.parse_args(argv)

    if not args.db.exists():
        print(f"Index introuvable : {args.db}")
        print("Construis-le d'abord :  make ingest && make db")
        print("Le pack régional suffit — il est dans le dépôt, aucun téléchargement.")
        return 1

    construire_cli()

    from survie.engine import Engine
    from survie.llm import NoLLM

    # embedder=None : recherche plein texte seule, voir la portée en en-tête.
    engine = Engine(args.db, NoLLM(), None)

    golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
    questions = [c["q"] for c in golden.get("questions", [])]
    print(f"Parité Python ↔ Swift sur {len(questions)} questions "
          f"({args.db.relative_to(ROOT)}, recherche plein texte seule)\n")

    divergentes = 0
    for q in questions:
        py, sw = cote_python(engine, q), cote_swift(args.db, q)
        ecarts = comparer(py, sw)
        if ecarts:
            divergentes += 1
            print(f"✗ {q}")
            for e in ecarts:
                print(f"    {e}")
        elif args.verbeux:
            etat = "refus" if py["refus"] else f"{len(py['hits'])} extraits"
            print(f"✓ {q[:60]:<62} {etat}")

    engine.close()
    print()
    if divergentes == 0:
        print(f"PARITÉ — {len(questions)} questions, classements identiques.")
        print("La mise au point de la recherche en Python décrit bien "
              "l'application Swift.")
        return 0

    print(f"DIVERGENCE — {divergentes} question(s) sur {len(questions)}.")
    print()
    print("Les résultats de `make eval` ne décrivent PAS ce que fait")
    print("l'application tant que ces écarts subsistent. Par ordre de")
    print("probabilité, les endroits où les deux implémentations dérivent :")
    print("  1. termes() et termeFTS() — troncature à 6 caractères, mots vides,")
    print("     pliage des accents. Un seul terme construit différemment change")
    print("     tout le classement BM25.")
    print("  2. _boost() / boost() — l'ordre des multiplications compte en")
    print("     virgule flottante ; les coefficients doivent être identiques.")
    print("  3. _avec_sieges() / siègesGarantis — l'éviction en fin de")
    print("     classement est la partie la plus facile à porter de travers.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
