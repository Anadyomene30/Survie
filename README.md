# SURVIE

Assistant de survie conversationnel, **100 % hors ligne**, adapté au terrain de
la **Bouriane** (nord-ouest du Lot) et du **Périgord Noir**.

Il répond uniquement à partir d'un corpus d'ouvrages de référence indexés
localement, **cite systématiquement sa source et sa page**, et refuse de
répondre plutôt que d'inventer.

Cible : MacBook Pro M1 Pro, 32 Go.

---

## Le principe

En survie, une hallucination n'est pas un bug, c'est un risque vital : une
posologie inventée, une plante mal identifiée, un geste de secours périmé. Toute
l'architecture découle d'une règle unique :

> **Le modèle ne parle jamais en son nom. Il restitue et synthétise des sources
> vérifiables.**

Trois garde-fous, dans cet ordre de gravité :

1. **Validateur de citations** — chaque `[source p.42]` produit par le modèle est
   confronté aux extraits réellement transmis. Une référence fabriquée est
   signalée. C'est le mode d'échec le plus insidieux, parce qu'une citation
   inventée donne à une phrase fausse l'apparence d'une phrase vérifiée.
2. **Règle d'or d'identification** — sur toute question portant sur une plante,
   un champignon ou une baie, le système ne conclut **jamais** à la
   comestibilité. Il donne les critères discriminants, nomme les sosies toxiques,
   et rappelle « dans le doute, s'abstenir ». Détecté par le logiciel, pas
   seulement demandé au modèle.
3. **Refus explicite** — hors corpus, le système refuse et **nomme les termes
   qu'aucun ouvrage indexé ne contient**.

---

## Démarrage

> **Première fois sur le Mac ?** Suis [`docs/DEMARRAGE-MAC.md`](docs/DEMARRAGE-MAC.md) :
> commandes exactes, sorties attendues, et les deux points qu'il faut valider
> avant de construire quoi que ce soit.


```bash
make setup           # dépendances (uv)
make corpus-check    # vérifie que les URLs du manifeste répondent
make fetch           # télécharge les sources libres de droit
make ingest          # extraction + OCR + découpage
make db              # vectorisation + index -> build/survie.db
make ask Q="je tremble et j'ai froid après la pluie"
```

Sur Linux ou sans modèle, tout fonctionne en **mode extraits seuls** : la
recherche tourne, les passages sont restitués tels quels, rien n'est reformulé.
C'est le mode le plus sûr de tous.

```bash
make test            # 71 tests, sans réseau ni dépendance lourde
make eval            # jeu d'évaluation (sûreté, citations, refus, recherche)
make parite          # les moteurs Python et Swift donnent-ils les mêmes extraits ?
```

## Choix du modèle

| Profil | Modèle | Empreinte | Usage |
|---|---|---|---|
| `defaut` | Mistral-Small-3.2-24B 4 bits | ~13 Go | meilleur français |
| `rapide` | Qwen3-30B-A3B 4 bits | ~17 Go | 3–4× plus rapide (MoE) |
| `batterie` | Qwen3-4B 4 bits | ~2,5 Go | autonomie maximale |

```bash
survie ask --modele rapide "..."
```

Le modèle d'**embeddings**, lui, n'est pas un choix de confort : il fige
l'index. Validé sur ce Mac (`scripts/valider-embedder.py`) :

```bash
SURVIE_EMBEDDER=mlx
SURVIE_EMBED_MODEL=mlx-community/bge-m3-mlx-fp16   # défaut du backend mlx
```

`BAAI/bge-m3` ne publie pas de safetensors et ne peut donc pas être chargé par
MLX ; la conversion MLX du même modèle, si. Et ce n'est pas un détail de
plomberie : sur une phrase témoin, les deux rendent des vecteurs à **cosinus
0,78**. Même nom, même dimension, vecteurs incomparables. L'index consigne donc
le nom, le backend **et** le vecteur d'une phrase témoin, que tout moteur
ré-encode au démarrage — Python comme Swift. En dessous de 0,99, il refuse de
servir plutôt que de rendre du bruit.

Le mode `batterie` n'est pas un gadget : quand il reste 20 % de batterie et
aucune prise à moins de trois heures de marche, la question n'est plus la
qualité de la prose.

---

## Architecture

```
ingest/     Python — pipeline exécuté UNE fois, jamais livré
cli/        moteur de référence + CLI (Python) — sert à l'évaluation
app/        SurvieCore (Swift) + application en barre de menus
corpus/     manifest.yaml ; public/ téléchargé ; private/ jamais versionné
regional/   pack Bouriane & Périgord Noir (13 fiches) + 9 fiches d'urgence
eval/       golden.yaml — 53 cas
```

Le moteur existe en deux implémentations : **Python** (référence, itération
rapide, évaluation) et **Swift** (runtime de l'application). Elles doivent
donner les mêmes extraits sur `eval/golden.yaml` — c'est la condition qui
autorise à mettre au point la recherche en Python.

Cette condition est **vérifiée mécaniquement** : `make parite` interroge les
deux moteurs sur les 53 questions du jeu d'évaluation et compare citation par
citation, rang par rang, score par score. Sans cela, l'évaluation décrirait un
prototype que personne n'utilise. Le comparatif porte sur la recherche plein
texte : le classement vectoriel ne pourra être comparé qu'une fois MLX branché
des deux côtés, avec le même modèle.

### Décisions notables

**Un seul fichier.** Métadonnées, texte, index plein texte et vecteurs vivent
tous dans `survie.db`. Un seul fichier à copier sur un disque externe, un seul
à restaurer. Un outil de survie qui ne survit pas à une panne de disque n'a pas
de sens.

**Recherche exhaustive plutôt que `sqlite-vec`.** À l'échelle du corpus
(~40 000 fragments), le produit matriciel coûte quelques millisecondes via
Accelerate. Cela supprime une dépendance native et préserve la propriété
« un seul fichier ».

**Le refus ne s'appuie pas sur le score de recherche.** Le score RRF est calculé
sur des rangs : mesuré sur le corpus, une question hors sujet obtient 0,019
contre 0,039 pour une question couverte — plages trop proches pour un seuil
fiable. Le refus repose donc sur la **couverture lexicale pondérée par la
rareté** des termes, complétée par le cosinus quand un vrai modèle sémantique
est présent.

**Pages citées, vignettes affichées.** Chaque fragment retient sa page d'origine
et l'application affiche l'**image** de cette page — indispensable pour lire un
schéma de nœud, d'attelle ou une planche botanique, que la transcription seule
ne rend pas.

---

## Le pack régional

La Bouriane est une **anomalie géologique** du Quercy : sables et grès du
Sidérolithique donnent un sol **siliceux et acide**, quand tout le causse
alentour est calcaire. Ce n'est pas un détail de botaniste.

- Le **châtaignier** marque le sol acide et signe la Bouriane.
- Le **cortinaire des montagnes**, mortel à effet retardé de 3 jours à
  3 semaines, est une espèce des sols acides : il est ici, pas sur le causse.
- La **digitale pourpre**, cardiotoxique, idem.
- La **truffe**, à l'inverse, veut du calcaire : bordure de causse, jamais les
  sables de Bouriane.

Un guide générique « Quercy » ou une flore calcicole donne donc de mauvaises
réponses ici. C'est précisément ce que le pack corrige.

---

## Corpus

- **Sources libres** (24 déclarées, **18 accessibles** au 11 septembre 2026) —
  téléchargées automatiquement : manuels de survie du domaine public (FM 21-76,
  FM 3-05.70, MCRP 3-02H, Ranger Handbook), médecine de terrain (*Emergency War
  Surgery* 2018, *SOF Medical Handbook*, OMS), *Nuclear War Survival Skills*,
  **Flore de Coste** (1906) et *King's American Dispensatory* (1898), inventaire
  flore Dordogne du CBNSA.
  Six sources restent introuvables : les trois guides **Hesperian** (site en
  panne), les deux guides **MSF en français** (passés en application web) et le
  guide de conserves **USDA**. Ce sont les manques les plus sensibles — MSF est
  la seule médecine de terrain en français du corpus. Détail et méthode de
  réparation dans [`docs/DEMARRAGE-MAC.md`](docs/DEMARRAGE-MAC.md).
- **Ouvrages sous droits** (8 déclarés, extensibles) — **jamais téléchargés**.
  À se procurer légalement et à déposer dans `corpus/private/`.
- **Wikipédia FR hors ligne** (archive Kiwix) — ingérée **sélectivement** par
  semences thématiques (`corpus/zim-seeds.yaml`) : quelques dizaines de
  milliers d'articles, jamais les 2,5 millions, et forcée en priorité 3.
  C'est un repli, pas une source de référence. Ingérer l'encyclopédie entière
  ferait remonter un article généraliste devant un manuel de médecine de
  terrain — la latence, elle, tiendrait (47 ms mesurées à 500 000 fragments) ;
  c'est le bruit qui interdit.

**Liste d'acquisition détaillée et priorisée : [`docs/CORPUS.md`](docs/CORPUS.md).**

`corpus/private/` et `build/` sont dans `.gitignore` : le dépôt ne contient
jamais d'œuvre sous droits ni d'index dérivé.

---

## État

| Composant | État |
|---|---|
| Pipeline d'ingestion | fonctionnel, testé de bout en bout |
| Moteur RAG + CLI (Python) | fonctionnel, 71 tests, éval 47/47 exécutables |
| Pack régional Bouriane | 13 fiches + 9 fiches d'urgence |
| Jeu d'évaluation | 53 cas |
| `SurvieCore` (Swift) | **compile et passe ses 19 tests** (Swift 6.3, macOS 26) |
| Parité Python ↔ Swift | **53/53**, recherche plein texte (`make parite`) |
| Application menu bar | écrite, compile — **jamais lancée** |
| Index de production | à construire : ni corpus téléchargé, ni modèle validé |

Le code Swift avait été écrit sans toolchain Swift ; il a été compilé pour la
première fois le 11 septembre 2026 sur M1 Pro, au prix d'une seule correction
(un `? :` dont les deux branches n'avaient pas le même type).

Ce qui reste à faire, dans l'ordre : valider le modèle d'embeddings
(`scripts/valider-embedder.py`), corriger le manifeste d'après `make
corpus-check`, construire l'index réel, puis lancer l'application.

## Limites connues

- **La qualité de l'OCR plafonne tout le système.** Les guides botaniques
  scannés sont les plus fragiles (noms latins, tableaux). `make ingest` signale
  les pages douteuses ; préfère un EPUB ou un PDF texte natif quand tu as le choix.
- **Six cas d'évaluation exigent le modèle sémantique** et ne peuvent pas
  passer avec le backend de test. Ils sont déclarés comme tels plutôt que
  masqués.
- **La parité vérifiée ne couvre pas le classement vectoriel.** Les deux
  moteurs sont comparés sans vecteurs, faute d'un embedder commun : côté
  Python le repli « hashing » existe, côté Swift l'embedder vient de MLX ou
  n'existe pas. Tout ce qui a été porté à la main d'un langage à l'autre est
  couvert ; la recherche vectorielle reste à confronter.
- **L'identification par photo est hors périmètre.** Techniquement faisable via
  Core ML, mais rendre un verdict visuel sur une plante est exactement le type
  de fonctionnalité qui tue quelqu'un.
- **Les doctrines médicales évoluent** (garrot, RCP). La date de publication de
  chaque source est affichée avec les réponses médicales.

## Avertissement

Cet outil ne remplace ni une formation aux premiers secours, ni un médecin, ni
un mycologue, ni le **15**. Il donne accès à des ouvrages, hors ligne, en citant
ses sources. Rien de plus — et c'est déjà beaucoup quand il n'y a pas de réseau.
