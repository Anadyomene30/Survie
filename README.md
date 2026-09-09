# Survie

Assistant local qui fonctionne **sans aucune connexion internet**, conçu pour
une situation de catastrophe : eau, agriculture vivrière, conservation des
aliments, santé, énergie, abri, hygiène, organisation collective.

Il répond **uniquement à partir de fiches vérifiées installées sur la
machine**, cite ses sources, et refuse de répondre plutôt que d'inventer.

## Pourquoi il refuse de répondre

En situation de crise, une réponse plausible mais fausse sur la potabilité
d'une eau ou la comestibilité d'une plante est un danger direct. Le modèle
n'est pas là pour savoir, il est là pour **reformuler ce que les fiches disent
déjà**. Quand le corpus ne couvre pas la question, le système le dit et
s'arrête.

## Installation (macOS, Apple Silicon)

À faire **tant que le réseau est disponible** :

```sh
xcode-select --install          # une seule fois
bash scripts/installer_macos.sh
```

Le script crée l'environnement Python, compile `llama.cpp` avec l'accélération
Metal, télécharge les modèles adaptés à la mémoire de la machine et construit
l'index. Ensuite, **le réseau peut être coupé définitivement**.

Vérifier :

```sh
source .venv/bin/activate
survie etat
```

## Utilisation

```sh
survie demande "comment rendre potable l'eau d'une mare"
survie demande "quelle surface pour nourrir une personne"

survie demande --sources-seules "..."   # sans IA : économise la batterie
survie urgence                          # fiches vitales, sans index ni modèle
survie urgence eau                      # une fiche précise
survie web --hote 0.0.0.0               # consultable depuis un téléphone
survie domaines                         # ce que couvre le corpus
```

## Les quatre niveaux de dégradation

Le système reste utile même amputé. C'est le cœur de sa fiabilité :

| Niveau | Fonctionne quand | Résultat |
|---|---|---|
| 1. IA + recherche | tout est installé | Réponse rédigée et sourcée |
| 2. Recherche seule | pas de modèle, ou batterie faible | Extraits de fiches bruts |
| 3. `survie urgence` | pas d'index, pas de modèle | Fiches vitales lues directement |
| 4. Papier | plus d'électricité | `fiches-vitales.md` imprimé |

Le niveau 2 se déclenche tout seul si le modèle est absent, et s'impose avec
`--sources-seules`. Le niveau 4 est produit par `scripts/faire_bundle.sh`.

## Profils matériels

Choisis automatiquement d'après la mémoire détectée (`sysctl hw.memsize`),
forçables avec `--profil`.

| Profil | Modèle | Taille | Cible |
|---|---|---|---|
| `leger` | Qwen3-1.7B | ~1,1 Go | Économie de batterie, Mac 8 Go |
| `standard` | Qwen3-4B-Instruct-2507 | ~2,5 Go | M1 Pro 16 Go |
| `confort` | Mistral-Small-3.2-24B | ~14 Go | 32 Go et plus |

Embeddings : `granite-embedding-107m-multilingual` (~100 Mo), commun à tous
les profils. Tous ces modèles sont sous licence Apache 2.0, donc
redistribuables sur une clé USB.

`llama.cpp` sert à la fois au modèle de langage et aux embeddings : une seule
dépendance native à compiler, au lieu d'installer PyTorch (~2,5 Go) pour un
modèle de 100 Mo.

## Ce que le refus garantit — et ce qu'il ne garantit pas

Le filtre de pertinence mesure quelle part du contenu informatif de la
question le corpus couvre réellement, en pondérant par la rareté des termes.
Il est calibré sur le corpus réel par `tests/test_pertinence_corpus.py`.

**Ce qu'il attrape de façon fiable :** les questions dont le vocabulaire
distinctif est absent du corpus (« piloter un hélicoptère », « investir en
bourse », « la capitale de l'Australie »).

**Ce qu'il n'attrape pas :** une question hors sujet formulée avec des mots
présents ailleurs dans le corpus — « qui a gagné la coupe du monde 1998 »
passe le filtre, parce que « coupe », « monde » et « gagné » existent dans les
fiches. C'est la limite intrinsèque d'un filtre lexical, et elle est figée
par un test pour rester visible.

Dans ce cas, deux garde-fous subsistent : la consigne donnée au modèle, qui
lui interdit d'ajouter quoi que ce soit aux extraits, et **l'affichage des
sources**, qui montre immédiatement que les extraits ne parlent pas du sujet.

**En pratique : lire les fiches citées avant d'agir sur une décision vitale.**

## Le corpus

36 fiches en markdown dans `connaissances/`, versionnées et relues.

```
00-urgence  01-eau  02-alimentation/{agriculture,conservation,elevage,cueillette}
03-sante  04-energie-feu  05-abri  06-hygiene-assainissement
07-outils-reparation  08-communication-navigation  09-securite
10-organisation-collective  11-scenarios
```

Chaque fiche porte un en-tête qui pilote le classement et rend la relecture
traçable :

```yaml
---
titre: Désinfecter l'eau par ébullition
domaine: eau
criticite: vitale          # vitale | haute | normale
delai: immediat            # immediat | jours | saison | long-terme
sources: [OMS-eau-de-boisson]
verifie_le: 2026-09-09
---
```

Une fiche dont l'en-tête est invalide **fait échouer la construction de
l'index** : elle n'entre pas silencieusement dans le corpus.

Pour ajouter une fiche : la déposer dans le bon dossier, puis `survie index`.

### Limites du corpus

- **Santé.** Ces fiches supposent que les secours sont hors d'atteinte. Elles
  ne remplacent ni un médecin ni une formation aux premiers secours — qui se
  fait avant la crise. Aucune posologie médicamenteuse n'y figure.
- **Cueillette.** Le corpus n'identifie aucune plante et n'affirme la
  comestibilité de rien. Il explique pourquoi les « tests universels de
  comestibilité » ne protègent pas.
- **Le corpus est le vrai travail.** Le code est modeste ; la valeur tient à
  la qualité et à la relecture des fiches. Le champ `verifie_le` sert à ça.

## Clé USB de secours

```sh
bash scripts/faire_bundle.sh
```

Produit `bundle/` : code, corpus, index, modèles, roues Python déjà compilées
(réinstallation sans réseau ni compilateur), et `fiches-vitales.md` à
imprimer.

## Tests

```sh
pytest
```

Couvrent le découpage, la tokenisation française, BM25, la fusion, la
validation de **toutes** les fiches du corpus, le refus d'inventer, et le
fonctionnement réseau coupé (`test_hors_ligne.py` fait échouer tout accès
réseau qui se glisserait dans le chemin de réponse).

## Architecture

```
question ─▶ recherche hybride (BM25 + vectoriel, fusion RRF)
                    │
                    ├─▶ mesure de couverture ──▶ sous le seuil : refus
                    │
                    └─▶ LLM local (llama.cpp) ─▶ réponse rédigée + citations
                            │
                            └─ absent ? ─▶ extraits bruts
```

BM25 et le vectoriel se complètent : le vectoriel seul rate les termes
techniques exacts (« lacto-fermentation », « hypochlorite »), qui sont
précisément le vocabulaire des fiches. La fusion RRF travaille sur les rangs,
ce qui évite de calibrer deux échelles de score hétérogènes et reste correcte
quand un seul des deux moteurs est disponible.

L'index est un simple produit scalaire NumPy sur matrice normalisée : sous
~100 000 fragments, la réponse est en dizaines de millisecondes, sans
dépendance lourde à compiler.
