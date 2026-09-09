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
make test            # 26 tests, sans réseau ni dépendance lourde
make eval            # jeu d'évaluation (sûreté, citations, refus, recherche)
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
regional/   pack Bouriane & Périgord Noir (8 fiches)
eval/       golden.yaml — 31 cas
```

Le moteur existe en deux implémentations : **Python** (référence, itération
rapide, évaluation) et **Swift** (runtime de l'application). Elles doivent
donner les mêmes extraits sur `eval/golden.yaml` — c'est la condition qui
autorise à mettre au point la recherche en Python.

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

- **Sources libres** (24) — téléchargées automatiquement : manuels de survie du
  domaine public, guides médicaux Hesperian et **MSF en français**, OMS,
  *Nuclear War Survival Skills*, **Flore de Coste** (1906, domaine public),
  inventaire flore Dordogne du CBNSA.
- **Ouvrages sous droits** (8 déclarés, extensibles) — **jamais téléchargés**.
  À se procurer légalement et à déposer dans `corpus/private/`.

**Liste d'acquisition détaillée et priorisée : [`docs/CORPUS.md`](docs/CORPUS.md).**

`corpus/private/` et `build/` sont dans `.gitignore` : le dépôt ne contient
jamais d'œuvre sous droits ni d'index dérivé.

---

## État

| Composant | État |
|---|---|
| Pipeline d'ingestion | fonctionnel, testé de bout en bout |
| Moteur RAG + CLI (Python) | fonctionnel, 26 tests, éval 29/29 |
| Pack régional Bouriane | 8 fiches rédigées |
| Jeu d'évaluation | 31 cas |
| `SurvieCore` (Swift) | écrit, **non compilé** — à valider sur le Mac |
| Application menu bar | à écrire (voir `app/Sources/SurvieApp/README.md`) |

Le code Swift a été écrit sur une machine Linux et n'a donc **jamais été
compilé**. Attends-toi à des corrections au premier `swift build`.

## Limites connues

- **La qualité de l'OCR plafonne tout le système.** Les guides botaniques
  scannés sont les plus fragiles (noms latins, tableaux). `make ingest` signale
  les pages douteuses ; préfère un EPUB ou un PDF texte natif quand tu as le choix.
- **Deux cas d'évaluation exigent le modèle sémantique** et ne peuvent pas
  passer avec le backend de test. Ils sont déclarés comme tels plutôt que
  masqués.
- **L'identification par photo est hors périmètre.** Techniquement faisable via
  Core ML, mais rendre un verdict visuel sur une plante est exactement le type
  de fonctionnalité qui tue quelqu'un.
- **Les doctrines médicales évoluent** (garrot, RCP). La date de publication de
  chaque source est affichée avec les réponses médicales.

## Avertissement

Cet outil ne remplace ni une formation aux premiers secours, ni un médecin, ni
un mycologue, ni le **15**. Il donne accès à des ouvrages, hors ligne, en citant
ses sources. Rien de plus — et c'est déjà beaucoup quand il n'y a pas de réseau.
