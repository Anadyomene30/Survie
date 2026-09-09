"""Interface en ligne de commande.

Le CLI est l'implémentation de référence du moteur : c'est sur lui que
s'évaluent la qualité de la recherche et la validité des citations, avant
que l'application Swift n'en reprenne la logique. Les deux doivent donner
les mêmes résultats sur eval/golden.yaml.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

DB = ROOT / "build" / "survie.db"


def _engine(args):
    from ingest.embed import get_embedder

    from .engine import Engine
    from .llm import load as load_llm

    embedder = None if args.sans_vecteurs else get_embedder()
    return Engine(Path(args.db), load_llm(args.modele), embedder)


def cmd_ask(args) -> int:
    from .divergence import rendu_humain
    from .validate import annoter

    eng = _engine(args)
    rep = eng.ask(args.question, k=args.k)

    if rep.refus:
        print(rep.texte)
        sig = rep.meta.get("signaux")
        if sig:
            print(f"\n(couverture lexicale {sig.couverture:.0%}, "
                  f"cosinus max {sig.cos_max:.3f}, {sig.n_lexical} passages "
                  f"contenant un terme de la question)")
        return 0

    # Affiché AVANT la réponse : un avertissement qu'il faut faire défiler
    # pour découvrir ne sert à rien dans l'urgence.
    if rep.divergences:
        print(rendu_humain(rep.divergences))

    if rep.texte:
        print(annoter(rep.texte, rep.rapport) if rep.rapport else rep.texte)
        if rep.rapport:
            print(f"\ncitations : {rep.rapport.valides}/{rep.rapport.citations} valides")
    else:
        print("Mode extraits seuls — aucun modèle chargé, rien n'est reformulé.\n")

    print("\n" + "─" * 70)
    print("SOURCES")
    for i, h in enumerate(rep.hits, 1):
        p = h.passage
        print(f"\n{i}. {p.citation}  {p.reference}")
        if p.section:
            print(f"   section « {p.section} »")
        print(f"   score {h.score:.4f} ({h.methodes})"
              + (f"  ⚠ OCR {p.qualite:.2f}" if p.qualite < 0.6 else ""))
        if args.extraits or not rep.texte:
            for line in p.texte.splitlines():
                print(f"   │ {line}")
        if p.image:
            print(f"   page : build/pages/{p.image}")

    if rep.ecart_dates:
        print(f"\n  Sources publiées entre {rep.ecart_dates[0]} et "
              f"{rep.ecart_dates[1]} : vérifie les dates sur les points médicaux.")

    if rep.identification:
        print("\n" + "─" * 70)
        print("Question d'identification : le système ne conclut jamais qu'une")
        print("espèce est comestible. Vérifie les critères ci-dessus contre une")
        print("flore, et dans le doute, abstiens-toi.")
    return 0


def cmd_urgence(args) -> int:
    """Chemin le plus court du système : aucun index, aucun modèle, aucun réseau.

    Volontairement indépendant du reste : il doit répondre même si la base est
    absente ou corrompue.
    """
    from .urgence import charger, chercher, rendu, sommaire

    fiches = charger()
    if not args.sujet:
        print(sommaire(fiches))
        return 0

    trouvees = chercher(" ".join(args.sujet), fiches)
    if not trouvees:
        print(f"Aucune checklist ne correspond à « {' '.join(args.sujet)} ».\n")
        print(sommaire(fiches))
        return 1

    print(rendu(trouvees[0][0]))
    if len(trouvees) > 1:
        autres = ", ".join(f.nom for f, _ in trouvees[1:4])
        print(f"Voir aussi : {autres}")
    return 0


def cmd_info(args) -> int:
    from .store import Store

    st = Store(Path(args.db))
    stats = st.stats()
    m = stats["meta"]
    print("Index :", args.db)
    print(f"  construit le   : {m.get('built_at', '?')}")
    print(f"  modèle vecteurs: {m.get('embed_model', '?')} (dim {m.get('embed_dim', '?')})")
    print(f"  fragments      : {m.get('chunk_count', '?')}")
    print(f"\n{'source':<28} {'lang':<5} {'licence':<16} fragments")
    print("─" * 66)
    for s in stats["sources"]:
        print(f"{s['id']:<28} {s['langue'] or '?':<5} {s['licence'] or '?':<16} {s['n']:>6}")
    if str(m.get("embed_model", "")).startswith("hashing-"):
        print("\n⚠ Index de TEST (backend hashing) : recherche purement lexicale.")
    st.close()
    return 0


def cmd_search(args) -> int:
    """Recherche seule, sans génération — pour juger le retrieval."""
    from ingest.embed import get_embedder

    from . import retrieve
    from .store import Store

    st = Store(Path(args.db))
    emb = None if args.sans_vecteurs else get_embedder()
    if emb:
        st.check_embedder(emb.name)
    qvec = emb.encode([args.question], is_query=True)[0] if emb else None
    for i, h in enumerate(retrieve.search(st, args.question, qvec, k=args.k), 1):
        p = h.passage
        print(f"{i:2}. {h.score:.4f} {h.methodes:<18} {p.citation} {p.section or '—'}")
        print(f"    {p.texte[:150].replace(chr(10), ' ')}…")
    st.close()
    return 0


def cmd_eval(args) -> int:
    from .evaluate import run

    return run(Path(args.fichier), Path(args.db), args)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="survie", description=__doc__)
    ap.add_argument("--db", default=str(DB), help="chemin de l'index")
    ap.add_argument("--modele", default=None,
                    help="defaut | rapide | batterie | none | <id modèle MLX>")
    ap.add_argument("--sans-vecteurs", action="store_true",
                    help="recherche plein texte uniquement (aucun modèle requis)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ask", help="poser une question")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=8, help="nombre d'extraits retenus")
    p.add_argument("--extraits", action="store_true", help="afficher le texte des sources")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("search", help="recherche seule, sans génération")
    p.add_argument("question")
    p.add_argument("-k", type=int, default=8)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("urgence", help="checklist d'urgence — sans modèle, instantané")
    p.add_argument("sujet", nargs="*", help="mot-clé ; sans argument, liste les fiches")
    p.set_defaults(func=cmd_urgence)

    p = sub.add_parser("info", help="état de l'index")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("eval", help="jeu d'évaluation")
    p.add_argument("fichier", nargs="?", default=str(ROOT / "eval" / "golden.yaml"))
    p.add_argument("-k", type=int, default=8)
    p.add_argument("--verbeux", action="store_true")
    p.set_defaults(func=cmd_eval)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"Erreur : {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        from .store import IndexMismatch

        if isinstance(e, IndexMismatch):
            print(f"Erreur : {e}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
