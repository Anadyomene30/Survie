# Reprendre le projet en local, sur le Mac

Tout le code est sur la branche `claude/youthful-volta-un36hb`.

## Installation

```bash
cd ~
git clone https://github.com/Anadyomene30/Survie.git survie-ia
cd survie-ia
git checkout claude/youthful-volta-un36hb
```

> Un dossier `~/Survie` non vide existait déjà sur cette machine et faisait
> échouer le clone. D'où le nom `survie-ia`. Vérifier ce que contient l'ancien
> dossier avant de le supprimer.

Prérequis :

```bash
brew install tesseract tesseract-lang     # OCR français, pour l'ingestion
curl -LsSf https://astral.sh/uv/install.sh | sh
make setup
```

## Ce qui a changé en passant en local

L'agent qui a écrit ce code tournait dans un conteneur Linux, sans accès à cette
machine. Trois choses lui étaient impossibles et deviennent triviales en local :

| | Pourquoi c'était bloqué | En local |
|---|---|---|
| Valider le modèle d'embeddings | MLX n'existe que sur puce Apple | exécutable directement |
| Compiler le Swift | pas de toolchain macOS | `swift build` |
| Télécharger le corpus | politique réseau bloquant archive.org, hesperian.org, msf.org en 403 | `make fetch` |

## À faire, dans l'ordre

L'ordre compte : chaque étape conditionne la suivante.

### 1. Vérifier le socle

```bash
make test
```

Attendu : `65 passed`. En cas d'échec, régler ça avant tout le reste.

### 2. Choisir le modèle d'embeddings — irréversible

```bash
SURVIE_EMBEDDER=mlx python3 scripts/valider-embedder.py
```

**C'est le verrou du projet.** En changer plus tard impose de tout réindexer.

Deux pannes possibles, et la seconde est muette : un modèle qui se charge, sort
des vecteurs de la bonne dimension, mais avec le mauvais **pooling**. BGE-M3
construit son vecteur dense à partir du token CLS ; si `mlx-embeddings` applique
une moyenne sur les tokens, tout continue de fonctionner et la qualité de
recherche est nettement dégradée — sans erreur, sans avertissement. On ne s'en
aperçoit qu'à l'usage, des semaines plus tard.

Le contexte rend le risque concret : `mlx-embeddings` est en version **0.1.0**
et documente l'architecture XLM-RoBERTa, dont BGE-M3 dérive, sans nommer BGE-M3.

Si la validation échoue, essayer dans cet ordre :

```bash
# e5 — même architecture, mais EXIGE ses préfixes d'instruction
SURVIE_EMBEDDER=mlx SURVIE_EMBED_MODEL=intfloat/multilingual-e5-large \
SURVIE_QUERY_PREFIX='query: ' SURVIE_DOC_PREFIX='passage: ' \
python3 scripts/valider-embedder.py

# EmbeddingGemma — plus petit, nativement MLX
SURVIE_EMBEDDER=mlx SURVIE_EMBED_MODEL=google/embeddinggemma-300m \
SURVIE_EMBED_DIM=768 python3 scripts/valider-embedder.py

# Diagnostic : sentence-transformers applique le pooling de référence.
# Bon ici et mauvais en MLX = c'est bien le pooling MLX qui est en cause.
SURVIE_EMBEDDER=st python3 scripts/valider-embedder.py
```

Le gagnant doit être utilisé **à l'indexation comme à l'interrogation**.
`Store.check_embedder` refuse de démarrer en cas de désaccord : c'est le seul
endroit où cette panne peut être attrapée.

### 3. Corriger les URLs du corpus

```bash
make corpus-check
```

Les 23 URLs de `corpus/manifest.yaml` ont été écrites de mémoire et **jamais
testées**. Certaines sont probablement mortes — les documents publics se
réorganisent. Corriger le manifeste d'après les échecs, ou déposer le fichier à
la main dans `corpus/public/<id>.pdf`.

Le pipeline ignore les sources absentes plutôt que d'échouer : le corpus reste
exploitable sans elles.

### 4. Construire l'index

```bash
make fetch
make ingest        # surveiller le rapport de qualité OCR
SURVIE_EMBEDDER=<le modèle validé> make db
python3 -m survie info
```

L'OCR est le plafond de qualité de tout le système. Si un guide botanique est
massivement signalé, chercher une meilleure numérisation plutôt que de l'indexer
tel quel.

### 5. Évaluer avec un vrai modèle

```bash
python3 -m survie eval --modele defaut
```

Active les deux contrôles jamais exécutés jusqu'ici :

- **citations** : le taux doit valoir **100 %**. C'est un invariant, pas un
  objectif. En dessous, le modèle fabrique des références.
- **sûreté identification** : aucune réponse ne doit trancher sur la
  comestibilité, et la formule de prudence doit être présente.

Quatre cas sont marqués `requiert: semantique` dans `eval/golden.yaml` : ils
étaient impossibles avec le backend de test et **doivent passer** avec un vrai
modèle. S'ils échouent, revenir à l'étape 2.

### 6. Compiler le Swift

```bash
cd app
swift build
swift test
```

**Ces 2 000 lignes n'ont jamais été compilées** — aucune toolchain Swift dans
l'environnement de développement. Des erreurs sont attendues. Procéder cible par
cible : `SurvieCore`, puis `SurvieCLI`, puis `SurvieApp`.

Une relecture adverse a déjà corrigé trois défauts réels (décodage JSON qui
aurait supprimé silencieusement tous les avertissements de doctrine, refus de
démarrer sans MLX, raccourci global jamais installé), mais elle ne remplace pas
un compilateur.

Vérifier ensuite la **parité** :

```bash
swift run survie-cli ../build/survie.db "comment traiter une hypothermie"
cd .. && python3 -m survie ask "comment traiter une hypothermie"
```

Les extraits doivent être identiques. Une divergence rend l'évaluation
trompeuse : elle ne décrirait plus ce que l'application fait réellement.

Pour activer MLX dans l'application, décommenter les dépendances dans
`app/Package.swift`. Sans elles, l'application fonctionne en recherche plein
texte, et le mode urgence fonctionne intégralement.

## Ce qui marche déjà, sans rien installer

```bash
python3 -c "import sys; sys.path.insert(0,'cli'); \
from survie.urgence import charger, chercher, rendu; \
print(rendu(chercher('il saigne beaucoup', charger())[0][0]))"
```

Le mode urgence ne dépend ni de l'index, ni des vecteurs, ni d'un modèle : 22 ms
à froid. C'est délibéré — si tout le reste est cassé, les gestes qui sauvent
restent accessibles.

## Les livres

Rien n'est téléchargé automatiquement pour les ouvrages sous droits. La liste
priorisée est dans [`CORPUS.md`](CORPUS.md) — les huit à récupérer en premier y
sont en tête. Les déposer dans `corpus/private/`, qui est gitignoré.

Préférer **EPUB > PDF texte natif > PDF scanné** : l'OCR se trompe précisément
là où c'est vital, sur les noms latins et les tableaux de doses.

## Points de conception à ne pas « corriger » par erreur

Trois choix contre-intuitifs sont documentés dans le code et verrouillés par des
tests. Les défaire dégraderait le système :

- **Le refus lexical est un filtre rapide, pas une garantie.** Durcir son seuil
  provoquerait des faux refus — l'erreur la plus grave, puisqu'elle prive d'aide
  quelqu'un dont la question est couverte. Le vrai garde-fou est le modèle en
  RAG strict. Voir `cli/survie/engine.py`.
- **Les sièges garantis dans la fusion RRF.** Le meilleur résultat plein texte
  ne doit jamais être évincé par un consensus tiède : en survie, un terme exact
  est souvent décisif. Voir `cli/survie/retrieve.py`.
- **L'ingestion ZIM est sélective par nécessité, pas par optimisation.** Ingérer
  Wikipédia entière ferait remonter un article généraliste devant un manuel de
  médecine de terrain. Voir `corpus/zim-seeds.yaml`.
