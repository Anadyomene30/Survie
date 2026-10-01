#!/usr/bin/env python3
"""Valide le modèle d'embeddings AVANT de construire l'index.

Pourquoi ce script existe.

Le choix du modèle d'embeddings est le verrou du projet : en changer impose de
tout réindexer. Et trois pannes possibles ne produisent AUCUN message d'erreur.

1. Le modèle ne se charge pas du tout — visible, tant mieux.
2. Le backend demandé échoue et le code retombe sur un autre. Tout continue de
   fonctionner, avec d'autres vecteurs que ceux qu'on croit. Mesuré ici le
   11 septembre 2026 : `BAAI/bge-m3` ne publie que `pytorch_model.bin`,
   mlx-embeddings n'y trouve pas de safetensors, et le repli
   sentence-transformers se faisait sans que le rapport ne le dise.
3. Le modèle se charge, produit des vecteurs de la bonne dimension, mais avec
   un POOLING différent. Rien ne le signale : ni erreur, ni dimension anormale.

Ce script mesure les trois. Il affiche le backend RÉELLEMENT obtenu, et compare
des paires de phrases françaises dont on connaît la proximité attendue.

    python scripts/valider-embedder.py
    SURVIE_EMBEDDER=mlx python scripts/valider-embedder.py
    SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large \\
        SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: ' \\
        python scripts/valider-embedder.py

COMMENT ON JUGE — et pourquoi pas par un écart de cosinus absolu.

Un seuil absolu (« au moins 0,10 d'écart ») n'est pas comparable d'un modèle à
l'autre : chacun a son propre plancher de similarité. Mesuré sur les mêmes six
paires : bge-m3 via sentence-transformers place les phrases sans rapport autour
de 0,36 ; le même bge-m3 converti pour MLX, autour de 0,63 ; multilingual-e5,
autour de 0,78. Un seuil fixe rejette e5 sans rien dire de sa qualité — il ne
mesure que l'échelle du modèle.

On mesure donc deux choses qui, elles, ont un sens pour tous :

- **l'ordre** : la phrase proche doit être mieux classée que la lointaine. Un
  pooling cassé détruit l'ordre, pas seulement la marge. C'est éliminatoire.
- **la séparation** : de combien d'écarts-types la phrase proche dépasse-t-elle
  le bruit du modèle lui-même — mesuré sur toutes les combinaisons sans
  rapport. Un z de 2 veut dire « nettement hors du bruit », quel que soit le
  plancher du modèle.
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

# Séparation moyenne minimale, en écarts-types du bruit du modèle.
# Mesuré : 2,30 pour bge-m3 via MLX, 1,95 via sentence-transformers, 1,80 pour
# multilingual-e5-large. En dessous de 1,5, le modèle ne distingue plus le
# pertinent du décor.
SEUIL_SEPARATION = 1.5
# En dessous, la paire est signalée sans faire échouer : certaines questions
# n'ont aucun mot commun avec leur réponse, et c'est justement le cas que le
# plein texte ne sait pas traiter.
SEUIL_PAIRE = 1.0


def mesurer(emb) -> tuple[int, np.ndarray, float, float, np.ndarray]:
    """Renvoie (paires bien ordonnées, z par paire, bruit moyen, écart-type,
    matrice question × candidat)."""
    questions = [p[0] for p in PAIRES]
    proches = [p[1] for p in PAIRES]
    lointains = [p[2] for p in PAIRES]

    # Asymétrie respectée : la question est encodée comme une requête, les
    # candidats comme des passages. e5 s'effondre si on l'ignore.
    Q = _normaliser(emb.encode(questions, is_query=True))
    C = _normaliser(np.concatenate([emb.encode(proches), emb.encode(lointains)]))

    n = len(PAIRES)
    S = Q @ C.T

    # Bruit : toutes les combinaisons question × candidat SANS rapport.
    bruit = np.array([S[i, j] for i in range(n) for j in range(2 * n) if j % n != i])
    mu, sd = float(bruit.mean()), float(max(bruit.std(), 1e-9))

    z = np.array([(S[i, i] - mu) / sd for i in range(n)])
    ordre = sum(1 for i in range(n) if S[i, i] > S[i, n + i])
    return ordre, z, mu, sd, S


def _normaliser(m: np.ndarray) -> np.ndarray:
    return m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)


def main() -> int:
    demande = config.EMBED_BACKEND
    print(f"Modèle demandé : {config.EMBED_MODEL}"
          f"{'' if config.EMBED_MODEL_EXPLICITE else '  (défaut, selon le backend)'}")
    print(f"Backend demandé : {demande}\n")

    try:
        emb = get_embedder()
    except Exception as e:
        print(f"ÉCHEC — le modèle ne se charge pas : {e}\n")
        _conseils()
        return 1

    print(f"Chargé : {emb.name}")
    print(f"Backend obtenu : {emb.backend}, dimension {emb.dim}\n")

    if emb.backend == "hashing":
        print("ATTENTION : c'est le backend de TEST, purement lexical.")
        print("Il n'est pas utilisable en production. Force SURVIE_EMBEDDER=mlx.\n")

    # Le repli silencieux est l'une des trois pannes qu'on traque : un rapport
    # qui valide un backend en en mesurant un autre ne vaut rien.
    if demande not in ("auto", emb.backend):
        print(f"ÉCHEC — backend « {demande} » demandé, « {emb.backend} » obtenu.")
        print("Le code a replié sans que tu l'aies choisi. Ce qui suit décrirait")
        print("un autre modèle que celui que tu crois valider.\n")
        _conseils()
        return 1

    ordre, z, mu, sd, S = mesurer(emb)
    n = len(PAIRES)

    print(f"Bruit du modèle (combinaisons sans rapport) : {mu:.3f} ± {sd:.3f}\n")
    print(f"{'proche':>7} {'lointain':>9} {'écart':>7} {'z':>6}   phrase")
    print("─" * 78)
    for i, (phrase, _, _) in enumerate(PAIRES):
        sp, sl = float(S[i, i]), float(S[i, n + i])
        marque = " " if sp > sl and z[i] >= SEUIL_PAIRE else "!"
        print(f"{marque}{sp:6.3f} {sl:9.3f} {sp - sl:7.3f} {z[i]:6.2f}   {phrase[:40]}")

    separation = float(z.mean())
    print()
    print(f"Ordre correct : {ordre}/{n}       "
          f"Séparation moyenne : {separation:.2f} σ (minimum {SEUIL_SEPARATION})")
    print()

    if ordre == n and separation >= SEUIL_SEPARATION:
        faibles = [PAIRES[i][0] for i in range(n) if z[i] < SEUIL_PAIRE]
        print("VALIDÉ — le modèle classe le pertinent devant le hors-sujet,")
        print("et l'en sépare nettement.")
        if faibles:
            print()
            print("Paires proches du bruit, à surveiller sans être bloquantes :")
            for f in faibles:
                print(f"  · {f}")
            print("  Ces questions n'ont aucun mot commun avec leur réponse :")
            print("  c'est exactement ce que la recherche plein texte rate.")
        print()
        print("Consigne ces variables — elles doivent être les mêmes à")
        print("l'indexation et à l'interrogation :")
        print(f"  SURVIE_EMBEDDER={emb.backend}")
        print(f"  SURVIE_EMBED_MODEL={emb.name}")
        if config.EMBED_QUERY_PREFIX or config.EMBED_DOC_PREFIX:
            print(f"  SURVIE_QUERY_PREFIX='{config.EMBED_QUERY_PREFIX}'")
            print(f"  SURVIE_DOC_PREFIX='{config.EMBED_DOC_PREFIX}'")
        print()
        print("L'index consigne le nom, le backend ET un vecteur témoin : une")
        print("requête produite autrement sera refusée, pas silencieusement")
        print("dégradée. Tu peux construire :  make db")
        return 0

    if ordre < n:
        print(f"ÉCHEC — {n - ordre} paire(s) mal ordonnée(s) : le modèle place une")
        print("phrase hors sujet devant la bonne réponse.")
    else:
        print(f"ÉCHEC — séparation trop faible ({separation:.2f} σ) : le modèle")
        print("classe correctement, mais ne détache pas le pertinent du décor.")
    print()
    _conseils()
    return 1


def _conseils() -> None:
    print("À essayer, dans l'ordre :")
    print()
    print("  1. Vérifier que le dépôt publie des safetensors. mlx-embeddings ne")
    print("     charge que ceux-là ; BAAI/bge-m3 n'expose que pytorch_model.bin.")
    print("     La conversion MLX existe : mlx-community/bge-m3-mlx-fp16.")
    print()
    print("  2. SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large")
    print("     avec SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: '")
    print("     (e5 EXIGE ces préfixes ; sans eux la qualité s'effondre)")
    print()
    print("  3. SURVIE_EMBED_MODEL=mlx-community/embeddinggemma-300m-bf16")
    print("     SURVIE_EMBED_DIM=768 — plus petit, plus rapide.")
    print()
    print("  4. SURVIE_EMBEDDER=st pour comparer avec sentence-transformers, qui")
    print("     applique le pooling de référence. Un bon résultat là et mauvais")
    print("     en MLX désigne le pooling MLX.")


if __name__ == "__main__":
    sys.exit(main())
