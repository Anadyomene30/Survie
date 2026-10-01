# Première session sur le Mac

À suivre dans l'ordre. Chaque étape indique **ce qui doit s'afficher** et
**ce qu'il faut me recoller** si ça diverge.

Compte deux à trois heures, dont l'essentiel en téléchargements.

> **État au 11 septembre 2026.** Les étapes **1** et **6** sont faites sur ce
> Mac : les tests passent, le Swift compile, et la parité des deux moteurs est
> vérifiée sur les 53 questions du jeu d'évaluation. Restent **2 à 5**, qui
> demandent toutes du réseau ou du disque : valider le modèle d'embeddings,
> corriger le manifeste, construire l'index réel, faire tourner l'évaluation
> avec un modèle chargé.

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

→ attendu : **71 passed, 1 skipped** (le test ignoré demande `libzim`, qui
n'est installé que par `make setup`). Vérifié le 11 septembre 2026.

```bash
python3 -c "import sys; sys.path.insert(0,'cli'); from survie.urgence import charger, chercher, rendu; print(rendu(chercher('il saigne beaucoup', charger())[0][0]))"
```

→ attendu : la checklist « Hémorragie », instantanément. Aucun index, aucun
modèle, aucun réseau.

**Si `make test` échoue ici, colle-moi la sortie et arrête-toi là** — inutile
d'aller plus loin tant que le socle n'est pas sain.

---

## 2. Le verrou : valider le modèle d'embeddings — tranché

**C'était l'étape la plus importante du document. Elle est faite**, et elle a
livré trois choses qu'on ne pouvait pas deviner sans la machine.

```bash
SURVIE_EMBEDDER=mlx uv run -- python scripts/valider-embedder.py
```

→ **VALIDÉ** : ordre correct 6/6, séparation moyenne 2,30 σ.

Le couple retenu, à utiliser à l'indexation comme à l'interrogation :

```bash
SURVIE_EMBEDDER=mlx
SURVIE_EMBED_MODEL=mlx-community/bge-m3-mlx-fp16   # défaut du backend mlx
```

### Ce qu'on a trouvé, et qui change le code

**1. `BAAI/bge-m3` ne peut pas être chargé par MLX.** Le dépôt ne publie que
`pytorch_model.bin` ; `mlx-embeddings` n'accepte que des safetensors. Il levait
donc une erreur, et `get_embedder` repliait **silencieusement** sur
sentence-transformers : le rapport annonçait « Backend : mlx » et mesurait
autre chose. La conversion MLX du même modèle
(`mlx-community/bge-m3-mlx-fp16`) fournit les safetensors ; elle est devenue le
défaut du backend `mlx`. Le script affiche désormais le backend **obtenu** et
échoue si ce n'est pas celui demandé.

**2. `MLXEmbedder.encode` ne marchait pas.** `mx.eval()` force l'évaluation
paresseuse et ne renvoie rien ; son résultat était passé à `np.asarray`, ce qui
donnait un tableau de dimension zéro et faisait échouer la vectorisation au
premier lot. Jamais exécuté avant aujourd'hui, donc jamais vu.

**3. Même modèle ne veut pas dire mêmes vecteurs.** Sur une phrase témoin,
`BAAI/bge-m3` via sentence-transformers et `mlx-community/bge-m3-mlx-fp16` via
MLX donnent des vecteurs à **cosinus 0,78**. Même nom, même dimension, et
pourtant incomparables. Un index bâti avec l'un et interrogé avec l'autre rend
du bruit — sans la moindre erreur.

D'où le garde-fou ajouté : l'index consigne le **nom**, le **backend**, et le
**vecteur d'une phrase témoin**. Au démarrage, le moteur ré-encode cette phrase
et compare : en dessous de 0,99 de cosinus, il refuse de servir. Nom et backend
sont des déclarations ; le témoin est une mesure — et c'est le seul contrôle
qui tienne aussi entre Python et Swift.

### Pourquoi le critère de validation a changé

Le seuil d'origine — « au moins 0,10 d'écart de cosinus » — mesurait l'échelle
du modèle, pas sa qualité. Chaque modèle a son propre plancher de similarité,
mesuré sur les mêmes six paires :

| Modèle et backend | Plancher (sans rapport) | Ordre | Séparation |
|---|---|---|---|
| `bge-m3-mlx-fp16` via MLX | 0,63 | 6/6 | **2,30 σ** |
| `BAAI/bge-m3` via sentence-transformers | 0,36 | 6/6 | 1,95 σ |
| `multilingual-e5-large` via sentence-transformers | 0,78 | 6/6 | 1,80 σ |

Les trois classent correctement ; le seuil absolu les recalait tous les trois
en échec. Le script juge maintenant sur **l'ordre** (éliminatoire — un pooling
cassé le détruit) et sur la **séparation en écarts-types du bruit du modèle**,
qui est comparable d'un modèle à l'autre.

Une paire reste proche du bruit chez tous : « ce champignon orange sous un
châtaignier est-il bon » contre « cortinaire des montagnes, mortel, sols
acides ». Aucun mot commun, aucun modèle ne la traite bien. C'est signalé, pas
bloquant — et c'est un argument de plus pour le pack régional, qui répond, lui,
avec les mots de la question.

---

## 3. Les URLs du corpus — réparées

```bash
make corpus-check
```

→ **18 sources sur 24 répondent** (c'étaient 4 sur 23 avant réparation, le
11 septembre 2026).

### Pourquoi elles étaient mortes

Deux causes, et la première n'est pas celle qu'on croit.

**Des items archive.org ont été « obscurcis ».** Neuf sources pointaient vers
`archive.org/download/…` et rendaient 503 ou 403. Ce n'est ni un blocage
réseau ni une limite de débit : l'API de métadonnées répond `"is_dark": true`,
c'est-à-dire retiré de l'accès public — réclamation d'ayant droit, le plus
souvent. La recette pour en sortir, réutilisable :

```bash
# 1. l'item est-il vivant ?
curl -s https://archive.org/metadata/<identifiant> | grep -o '"is_dark":[a-z]*'

# 2. chercher un remplaçant, puis vérifier qu'un PDF en sort vraiment
curl -s 'https://archive.org/advancedsearch.php?q=title:(...)&fl[]=identifier&rows=15&output=json'
```

Deux pièges à éviter en choisissant le remplaçant : les items des collections
`inlibrary` / `printdisabled` ne servent qu'un PDF **chiffré** (prêt
numérique), illisible par pymupdf ; et une recherche trop lâche ramène un
homonyme — « dispensatory » avait rendu *The American homoeopathic
dispensatory* à la place du *King's American Dispensatory*.

**Des sites se sont réorganisés.** L'IRIS de l'OMS est passé à DSpace 7 :
les vieux `bitstream/handle/…` rendent une page HTML, et le PDF se récupère
maintenant par `server/api/core/bitstreams/<uuid>/content`, uuid qu'on obtient
via `server/api/discover/search/objects?query=…`.

### Ce qui a changé dans le manifeste

| Source | Devenue |
|---|---|
| `fm-21-76-1` | MCRP 3-02H, la version Marine Corps du même manuel |
| `fm-21-10` | TC 4-02.3 (2015), la doctrine qui lui succède |
| `emergency-war-surgery` | 5ᵉ édition 2018 au lieu de 2013 |
| `coste-flore` | tome 3 seulement — les tomes 1 et 2 sont absents ou obscurcis |
| `kings-dispensatory` | tomes 1 **et** 2, en deux sources |
| `nwss`, `fm-3-05-70`, `fm-3-25-26`, `ranger-handbook`, `sof-medical-handbook` | autres items, contenu identique |
| `who-basic-emergency-care`, `who-water-quality` | API DSpace de l'IRIS |

### Les six qui manquent encore

- **Hesperian** (*Where There Is No Doctor*, *No Dentist*, *A Book for
  Midwives*) — `hesperian.org` rend 522, les liens directs 404. Le site est en
  panne ou refondu ; à reprendre plus tard.
- **MSF** (guide clinique, médicaments essentiels) — les guides sont passés
  dans une application web, sans PDF public à URL stable.
- **USDA / NCHFP** (*Complete Guide to Home Canning*) — site réorganisé, les
  PDF ne sont plus exposés en lien direct.

Ce sont les trois manques les plus sensibles du corpus : ce sont les seules
sources **médicales de terrain en français** (MSF) et les seules qui traitent
la conservation des aliments avec des barèmes vérifiés (USDA). À chercher en
priorité.

Cas particulier : **FEMA `Are You Ready?`** — l'URL est bonne, mais ready.gov
refuse les clients TLS non navigateurs. `curl` obtient 200 là où `urllib` reçoit
403, quel que soit l'en-tête envoyé. La commande manuelle est notée dans le
manifeste.

```bash
make fetch
```

→ 17 fichiers, 365 Mo dans `corpus/public/`. La commande liste aussi les
ouvrages sous droits manquants, avec le chemin exact où les déposer.

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

Sur ce Mac, avec le seul pack régional indexé en backend de test
(`SURVIE_EMBEDDER=hashing` à l'index comme à la question) :
**47 cas sur 47 exécutables passent**, et **6 cas sont explicitement reportés**
parce qu'ils exigent un modèle sémantique. Ce sont les premiers à regarder :

- `je suis perdu dans les bois sans carte` — « perdu » et « suivre le ruisseau
  vers l'aval » n'ont aucun mot en commun.
- `quelle est la capitale du Kazakhstan` — « capitale » apparaît dans « l'heure
  de début est capitale ».
- `recette du soufflé au fromage` — « souffl\* » attrape « souffle ».
- `qui a gagné la coupe du monde de football en 1998` — « coupe » et « monde »
  existent dans un corpus de survie.
- `je ne sais plus où je suis dans les bois, quelle direction prendre` — même
  cause que le premier.
- `quel bois pour fumer de la viande` — « bois » au sens du combustible contre
  « bois » au sens de la forêt : deux sens, un seul mot.

**Ces six-là devraient passer avec un vrai modèle.** S'ils échouent, c'est
un signal fort que le modèle ou le pooling ne va pas — reviens à l'étape 2.

Avec un modèle chargé, deux contrôles nouveaux s'activent :

- **citations** : le taux doit valoir **100 %**. C'est un invariant, pas un
  objectif. En dessous, le modèle fabrique des références.
- **sûreté identification** : aucune réponse ne doit trancher sur la
  comestibilité, et la formule de prudence doit être présente.

Colle-moi la sortie si l'un des deux n'est pas au vert.

---

## 6. Compiler le Swift — fait

Le code Swift avait été écrit sans toolchain Swift. Il compile désormais sur
Xcode 26 / Swift 6.3, cible macOS 14 :

```bash
cd app
swift build          # SurvieCore + SurvieCLI + SurvieApp, sans MLX
swift test           # 19 tests de parité avec l'implémentation Python
```

Une seule correction a été nécessaire, dans `VueSources.swift` : un `? :` dont
les deux branches n'avaient pas le même type — `Set.insert` renvoie un tuple là
où `Set.remove` renvoie un optionnel. Le reste est passé du premier coup.

`SurvieCore` ne dépend que de Foundation, SQLite3 et Accelerate : il compile
sans réseau et sans MLX.

### Vérifier la parité

```bash
make parite          # les 53 questions du jeu d'évaluation, les deux moteurs
```

→ attendu : **PARITÉ — 53 questions, classements identiques.**

Le script interroge le moteur Python et `survie-cli`, et compare citation,
section, rang, méthode et score. Il a déjà servi : il a trouvé une divergence
sur la règle d'identification — côté Python, le motif des espèces sensibles
était ancré des deux côtés, si bien que « des amanites » ne déclenchait pas la
règle d'or alors que « une amanite » la déclenchait. Le pluriel est la forme
sous laquelle on cueille : c'était un trou de sûreté, pas un détail de parité.

Le script a besoin d'un index. Le pack régional suffit — il est dans le dépôt,
aucun téléchargement :

```bash
SURVIE_PAGE_IMAGES=0 python3 -m ingest.extract && python3 -m ingest.chunk
SURVIE_EMBEDDER=hashing python3 -m ingest.embed
SURVIE_EMBEDDER=hashing python3 -m ingest.build_db
```

**La parité ne couvre pas encore le classement vectoriel** : les deux moteurs
sont comparés en recherche plein texte seule, faute d'embedder commun. À
reprendre une fois l'étape 2 tranchée et MLX branché des deux côtés.

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
3. **La sortie de `make eval --modele defaut`** — surtout le taux de citations.

`swift build` n'est plus dans cette liste : c'est fait, et `make parite` garde
la porte fermée derrière.

Et si tu as déjà des livres sous la main, dis-moi lesquels : j'adapterai le jeu
d'évaluation pour les couvrir.
