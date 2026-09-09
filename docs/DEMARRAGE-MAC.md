# Première session sur le Mac

À suivre dans l'ordre. Chaque étape indique **ce qui doit s'afficher** et
**ce qu'il faut me recoller** si ça diverge.

Compte deux à trois heures, dont l'essentiel en téléchargements.

---

## 0. Récupérer le dépôt

```bash
git clone https://github.com/Anadyomene30/Survie.git
cd Survie
git checkout claude/youthful-volta-un36hb
```

Installer [uv](https://docs.astral.sh/uv/) si besoin :

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Puis :

```bash
make setup
```

---

## 1. Vérifier que tout tourne sans modèle

**C'est la première chose à faire, et elle ne dépend de rien.**

```bash
make test
```

→ attendu : **65 passed**.

```bash
python3 -c "import sys; sys.path.insert(0,'cli'); from survie.urgence import charger, chercher, rendu; print(rendu(chercher('il saigne beaucoup', charger())[0][0]))"
```

→ attendu : la checklist « Hémorragie », instantanément. Aucun index, aucun
modèle, aucun réseau.

**Si `make test` échoue ici, colle-moi la sortie et arrête-toi là** — inutile
d'aller plus loin tant que le socle n'est pas sain.

---

## 2. Le verrou : valider le modèle d'embeddings

**L'étape la plus importante du document.** Changer de modèle d'embeddings
oblige à tout réindexer : il faut trancher maintenant, pas après avoir passé
six heures à océriser des livres.

Deux pannes sont possibles, et **la seconde ne produit aucun message d'erreur** :

1. Le modèle ne se charge pas. Visible, tant mieux.
2. Le modèle se charge, sort des vecteurs de la bonne dimension, mais avec le
   **mauvais pooling**. BGE-M3 construit son vecteur dense à partir du token
   CLS ; si `mlx-embeddings` applique une moyenne sur les tokens, tout continue
   de fonctionner et la qualité de recherche est nettement dégradée. Ni erreur,
   ni avertissement, ni dimension anormale. On ne s'en aperçoit qu'à l'usage,
   des semaines plus tard, en trouvant les réponses « bizarrement à côté ».

Le contexte qui rend ce risque réel : `mlx-embeddings` est en version **0.1.0**,
et sa documentation liste l'architecture XLM-RoBERTa — dont BGE-M3 dérive —
sans nommer BGE-M3.

```bash
SURVIE_EMBEDDER=mlx python3 scripts/valider-embedder.py
```

Le script compare des paires de phrases françaises dont on connaît la proximité
attendue : « je tremble et je suis trempé » doit être plus proche de
« hypothermie » que de « recette de la tarte aux pommes ».

**→ Attendu : `VALIDÉ`, avec des écarts d'au moins 0,10 sur les six paires.**

### Si ça échoue

Essaie dans cet ordre, et **colle-moi la sortie de chaque tentative** :

```bash
# 1. Repli e5 — même architecture, mais EXIGE des préfixes d'instruction
SURVIE_EMBEDDER=mlx \
SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large \
SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: ' \
python3 scripts/valider-embedder.py

# 2. Repli EmbeddingGemma — plus petit, plus rapide, nativement MLX
SURVIE_EMBEDDER=mlx SURVIE_EMBED_MODEL=google/embeddinggemma-300m \
SURVIE_EMBED_DIM=768 python3 scripts/valider-embedder.py

# 3. Diagnostic : sentence-transformers applique le pooling de référence.
#    Si l'écart est bon ici et mauvais en MLX, c'est bien le pooling MLX.
SURVIE_EMBEDDER=st python3 scripts/valider-embedder.py
```

Quel que soit le gagnant, **note la variable d'environnement** : elle doit être
la même à l'indexation et à l'interrogation. Le code refuse de démarrer en cas
de désaccord — c'est le seul endroit où l'on peut attraper cette panne.

---

## 3. Vérifier les URLs du corpus

**Je n'ai pas pu tester ces liens** : la politique réseau de l'environnement où
j'ai développé bloque `archive.org`, `hesperian.org`, `msf.org` et les autres,
toutes en 403 au niveau du proxy. Les URLs sont donc données de mémoire et
certaines sont probablement mortes — les documents publics se réorganisent.

```bash
make corpus-check
```

**Colle-moi la sortie complète.** Je corrigerai le manifeste d'après les échecs
réels. En attendant, le pipeline ignore les sources absentes plutôt que
d'échouer : le corpus reste exploitable.

Puis :

```bash
make fetch
```

Cette commande liste aussi les ouvrages sous droits manquants, avec le chemin
exact où les déposer.

---

## 4. Construire l'index

```bash
make ingest        # extraction + OCR + découpage
SURVIE_EMBEDDER=mlx make db
```

`make ingest` signale les pages de qualité douteuse, source par source.
**Regarde cette liste** : l'OCR est le plafond de qualité de tout le système.
Si un guide botanique est massivement touché, cherche une meilleure
numérisation plutôt que de l'indexer tel quel.

Pour l'OCR, il faut Tesseract avec le français :

```bash
brew install tesseract tesseract-lang
```

Vérification :

```bash
python3 -m survie info
```

→ attendu : le nom du modèle validé à l'étape 2, et non `hashing-…`.

---

## 5. Faire tourner l'évaluation complète

```bash
make eval                        # sans modèle : recherche seule
python3 -m survie eval --modele defaut   # avec le modèle : citations et verdicts
```

Sur ma machine, **47 cas sur 47 exécutables passent**, et **4 cas sont
explicitement reportés** parce qu'ils exigent un modèle sémantique que je
n'avais pas. Ce sont les premiers à regarder :

- `je suis perdu dans les bois sans carte` — « perdu » et « suivre le ruisseau
  vers l'aval » n'ont aucun mot en commun.
- `quelle est la capitale du Kazakhstan` — « capitale » apparaît dans « l'heure
  de début est capitale ».
- `recette du soufflé au fromage` — « souffl\* » attrape « souffle ».
- `qui a gagné la coupe du monde de football en 1998` — « coupe » et « monde »
  existent dans un corpus de survie.

**Ces quatre-là devraient passer avec un vrai modèle.** S'ils échouent, c'est
un signal fort que le modèle ou le pooling ne va pas — reviens à l'étape 2.

Avec un modèle chargé, deux contrôles nouveaux s'activent :

- **citations** : le taux doit valoir **100 %**. C'est un invariant, pas un
  objectif. En dessous, le modèle fabrique des références.
- **sûreté identification** : aucune réponse ne doit trancher sur la
  comestibilité, et la formule de prudence doit être présente.

Colle-moi la sortie si l'un des deux n'est pas au vert.

---

## 6. Compiler le Swift

**Ce code n'a jamais été compilé** — aucune toolchain Swift là où je travaille.
Attends-toi à des erreurs au premier build. C'est normal et prévu.

```bash
cd app
swift build          # SurvieCore + CLI, sans MLX
swift test           # tests de parité avec l'implémentation Python
```

`SurvieCore` ne dépend que de Foundation, SQLite3 et Accelerate : ça doit
compiler sans réseau et sans MLX.

**Colle-moi les erreurs telles quelles**, je corrige. Procédons cible par
cible : d'abord `SurvieCore`, puis `SurvieCLI`, puis `SurvieApp`.

Vérifier la parité une fois que ça compile :

```bash
swift run survie-cli ../build/survie.db "comment traiter une hypothermie"
```

→ les extraits doivent être **les mêmes** que ceux de :

```bash
cd .. && python3 -m survie ask "comment traiter une hypothermie"
```

Une divergence signale un écart entre les deux implémentations, et rend
l'évaluation moins pertinente : elle ne décrirait plus ce que l'application fait.

Pour activer MLX, décommenter les dépendances dans `app/Package.swift` puis
recompiler. Sans elles, l'application fonctionne en recherche plein texte, et
le mode urgence fonctionne intégralement.

---

## 7. Volumétrie et sauvegarde

| | Taille |
|---|---|
| Modèles (3 profils) | ~35 Go |
| Corpus + index + vignettes | 30–60 Go |
| Wikipédia FR ZIM (sans images) | ~10 Go |

Prévois un **SSD externe**. Et une **copie de secours** : un outil de survie qui
ne survit pas à une panne de disque n'a pas de sens.

L'essentiel tient dans deux éléments :

- `build/survie.db` — un seul fichier : métadonnées, texte, index plein texte
  et vecteurs.
- `build/pages/` — les vignettes, seul élément externe (les embarquer ferait
  passer la base de 200 Mo à plusieurs gigaoctets).

---

## Ce qu'il me faut, en résumé

Par ordre d'importance :

1. **La sortie de `scripts/valider-embedder.py`** — elle décide de tout le reste.
2. **La sortie de `make corpus-check`** — je corrige le manifeste.
3. **Les erreurs de `swift build`** — je corrige le Swift.
4. **La sortie de `make eval --modele defaut`** — surtout le taux de citations.

Et si tu as déjà des livres sous la main, dis-moi lesquels : j'adapterai le jeu
d'évaluation pour les couvrir.
