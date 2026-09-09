#!/usr/bin/env python3
"""Valide le modèle d'embeddings AVANT de construire l'index.

Pourquoi ce script existe.

Le choix du modèle d'embeddings est le verrou du projet : en changer impose de
tout réindexer. Et deux pannes possibles ne produisent AUCUN message d'erreur.

1. Le modèle ne se charge pas du tout — visible, tant mieux.
2. Le modèle se charge, produit des vecteurs de la bonne dimension, mais avec
   le MAUVAIS POOLING. BGE-M3 construit son vecteur dense à partir du token
   CLS ; si la bibliothèque applique une moyenne sur les tokens, tout continue
   de fonctionner, mais la qualité de recherche est nettement dégradée. Rien ne
   le signale : ni erreur, ni avertissement, ni dimension anormale.

Ce script teste le second cas de la seule manière fiable : sur des paires de
phrases françaises dont on connaît la proximité attendue. Un modèle sain doit
juger « je tremble et j'ai froid » plus proche de « hypothermie » que de
« recette de cuisine ». Un pooling cassé brouille précisément ces écarts.

    python scripts/valider-embedder.py
    SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large python scripts/valider-embedder.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from ingest import config  # noqa: E402
from ingest.embed import get_embedder  # noqa: E402

# (phrase A, phrase proche, phrase lointaine)
# Toutes tirées du domaine réel, en français, avec des paraphrases telles qu'un
# utilisateur les taperait.
PAIRES = [
    ("je tremble et je suis trempé, j'ai très froid",
     "hypothermie : signes précoces, frissons incontrôlables",
     "recette de la tarte aux pommes"),
    ("l'eau de la source est claire, puis-je la boire",
     "potabilisation de l'eau, ébullition et filtration",
     "réglage de l'allumage d'un moteur diesel"),
    ("il saigne beaucoup du bras, que faire",
     "hémorragie : comprimer directement, garrot si nécessaire",
     "histoire de la Renaissance italienne"),
    ("ce champignon orange sous un châtaignier est-il bon",
     "cortinaire des montagnes, mortel, sols acides",
     "programmation d'une base de données relationnelle"),
    ("je ne sais plus où je suis dans la forêt",
     "orientation : suivre la pente puis le ruisseau vers l'aval",
     "cours de la bourse et marchés financiers"),
    ("comment prévenir les secours sans réseau",
     "alerter : 112 sans carte SIM, 114 par SMS",
     "entretien d'un aquarium d'eau douce"),
]

SEUIL_ECART = 0.10   # marge minimale attendue entre proche et lointain


def main() -> int:
    print(f"Modèle demandé : {config.EMBED_MODEL}")
    print(f"Backend        : {config.EMBED_BACKEND}\n")

    try:
        emb = get_embedder()
    except Exception as e:
        print(f"ÉCHEC — le modèle ne se charge pas : {e}\n")
        print("Replis prévus, à essayer dans cet ordre :")
        print("  SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large  (XLM-R, comme bge-m3)")
        print("      + SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: '")
        print("  SURVIE_EMBED_MODEL=google/embeddinggemma-300m      (petit, rapide)")
        print("  SURVIE_EMBEDDER=st                                 (sentence-transformers)")
        return 1

    print(f"Chargé : {emb.name}, dimension {emb.dim}\n")

    if emb.name.startswith("hashing-"):
        print("ATTENTION : c'est le backend de TEST, purement lexical.")
        print("Il n'est pas utilisable en production. Force SURVIE_EMBEDDER=mlx.\n")

    echecs = 0
    print(f"{'proche':>7} {'lointain':>9} {'écart':>7}   phrase")
    print("─" * 78)
    for phrase, proche, lointain in PAIRES:
        v = emb.encode([phrase, proche, lointain])
        v = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
        s_proche, s_lointain = float(v[0] @ v[1]), float(v[0] @ v[2])
        ecart = s_proche - s_lointain
        ok = ecart >= SEUIL_ECART
        echecs += not ok
        marque = " " if ok else "!"
        print(f"{marque}{s_proche:6.3f} {s_lointain:9.3f} {ecart:7.3f}   {phrase[:44]}")

    print()
    if echecs == 0:
        print("VALIDÉ — le modèle sépare correctement le pertinent du hors-sujet.")
        print("Tu peux construire l'index :  make db")
        return 0

    print(f"ÉCHEC — {echecs} paire(s) sur {len(PAIRES)} mal séparée(s).")
    print()
    print("Cause la plus probable : le POOLING. BGE-M3 attend le token CLS ; si")
    print("la bibliothèque applique une moyenne sur les tokens, les vecteurs")
    print("restent valides en apparence mais discriminent mal. C'est exactement")
    print("le genre de panne qui ne se voit qu'à l'usage, des semaines plus tard.")
    print()
    print("À essayer, dans l'ordre :")
    print("  1. Vérifier l'option de pooling exposée par mlx-embeddings.")
    print("  2. SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large")
    print("     avec SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: '")
    print("     (e5 EXIGE ces préfixes ; sans eux la qualité s'effondre)")
    print("  3. SURVIE_EMBEDDER=st pour comparer avec sentence-transformers,")
    print("     qui applique le pooling de référence. Si l'écart est bon là et")
    print("     mauvais en MLX, c'est bien le pooling MLX qui est en cause.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
