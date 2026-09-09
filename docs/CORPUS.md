# Corpus : quoi acquérir, dans quel ordre, dans quel format

## Format — plus important qu'on ne croit

Par ordre de préférence : **EPUB > PDF texte natif > PDF scanné**.

Un scan passe par l'OCR, et l'OCR se trompe précisément là où c'est vital :
noms latins, tableaux de doses, légendes de planches botaniques. `make ingest`
signale les pages douteuses, mais il ne peut pas les réparer. **À titre égal,
prends toujours l'EPUB.**

Vérifie après ingestion :

```bash
make ingest    # affiche « qualité<0.55 » par source
```

Si une source est massivement touchée, cherche une meilleure numérisation
plutôt que de l'indexer telle quelle : une source illisible pollue la recherche
et fait citer des passages incompréhensibles.

## Où déposer

```
corpus/private/<identifiant>.pdf
```

L'identifiant est celui du champ `fichier_attendu` de `corpus/manifest.yaml`.
`make fetch` liste les manquants à chaque exécution.

Ce répertoire est dans `.gitignore` : **rien de ce que tu y déposes ne part
dans le dépôt.** L'usage relève de la copie privée — ouvrage acquis légalement,
usage strictement personnel, ni les fichiers ni l'index ne se redistribuent.

Pour ajouter un ouvrage non listé, ajoute une entrée dans `corpus/manifest.yaml` :

```yaml
  - id: thevenin-plantes-medicinales
    titre: "Plantes médicinales"
    auteur: "Thierry Thévenin"
    langue: fr
    licence: copyright
    domaine: [phytothérapie, plantes-médicinales]
    priorite: 1
    fichier_attendu: corpus/private/thevenin-plantes-medicinales.pdf
```

`priorite: 1` pondère légèrement la source à la hausse dans la recherche ;
`3` la déclasse (utile pour les pharmacopées anciennes, à valeur historique
mais dont les posologies ne doivent pas être suivies).

---

## Les 8 à récupérer en premier

Avec ceux-là, le système est déjà utile.

| | Ouvrage | Pourquoi celui-ci |
|---|---|---|
| 1 | **Couplan & Styner — *Plantes sauvages comestibles et toxiques*** (Delachaux) | Le plus critique, et le plus difficile à remplacer par du libre. Couvre les sosies. |
| 2 | **Eyssartier & Roux — *Guide des champignons France et Europe*** (Belin) | Mycologie européenne moderne. La Bouriane est un terrain à champignons, avec deux mortels spécifiques. |
| 3 | **Auerbach — *Wilderness Medicine*** | La référence mondiale de la médecine en milieu isolé. |
| 4 | **David Manise — *Manuel de survie*** (CEETS) | Français, terrain européen tempéré — le nôtre. |
| 5 | **Wiseman — *SAS Survival Handbook*** | Le classique généraliste. |
| 6 | **Kochanski — *Bushcraft*** | Feu, abri, bois. Rigueur technique rare. |
| 7 | **Carla Emery — *The Encyclopedia of Country Living*** | Autonomie long terme : conservation, élevage, jardin. |
| 8 | **Gonzales — *Deep Survival*** | Psychologie de la décision sous stress — la partie que tout le monde néglige, et qui décide de l'issue. |

---

## Liste complète par domaine

★ = priorité haute · ◆ = français ou spécifiquement européen

### Survie généraliste
- ★ *SAS Survival Handbook* — John « Lofty » Wiseman
- ★ *Bushcraft: Outdoor Skills and Wilderness Survival* — Mors Kochanski
- ★◆ *Manuel de survie* — David Manise
- *Bushcraft 101* — Dave Canterbury
- ◆ *Le Manuel de la vie sauvage* — Alain Saury
- *Tom Brown's Field Guide to Wilderness Survival*
- *98.6 Degrees* et *When All Hell Breaks Loose* — Cody Lundin

### Médecine en milieu isolé
- ★ *Wilderness Medicine* — Paul Auerbach
- ★ *Medicine for Mountaineering* — James Wilkerson
- *NOLS Wilderness Medicine*
- *Ditch Medicine* — Hugh Coffee
- *The Survival Medicine Handbook* — Alton
- ◆ *Médecine de montagne* — Jean-Paul Richalet

> Les guides **MSF en français** (guide clinique et thérapeutique, médicaments
> essentiels) et les guides **Hesperian** sont en accès libre : ils sont déjà
> dans le manifeste et récupérés par `make fetch`. Inutile de les acheter.

### Botanique et cueillette — le plus critique ici
- ★◆ *Guide des plantes sauvages comestibles et toxiques* — Couplan & Styner
- ★◆ *Le Régal végétal* — François Couplan
- ◆ *Reconnaître facilement les plantes* — François Couplan
- ★◆ *Flora Gallica — Flore de France* (Biotope)
- *The Forager's Harvest* / *Nature's Garden* — Samuel Thayer (méthode)
- ◆ *Plantes médicinales* — Thierry Thévenin
- ◆ *Encyclopédie des plantes médicinales* (Larousse)

> La **Flore de Coste** (1906) est dans le domaine public et déjà au manifeste.
> Nomenclature ancienne : à confronter à TAXREF pour les noms actuels.

### Mycologie
- ★◆ *Guide des champignons France et Europe* — Eyssartier & Roux
- ★◆ *Guide Delachaux des champignons* — Courtecuisse & Duhem
- ◆ Guide mycologique local Quercy / Périgord, si tu en trouves un

### Faune
- ◆ *Guide Delachaux des amphibiens et reptiles de France* (vipère aspic)
- ◆ *Guide des traces d'animaux* — Bang & Dahlström
- ◆ *Guide Delachaux des oiseaux de France*

### Autonomie alimentaire et conservation
- ★ *The Encyclopedia of Country Living* — Carla Emery
- *The Foxfire Book* (série)
- ◆ *Conserver les aliments sans énergie* — Terre Vivante
- *L'Art de la fermentation* — Sandor Katz
- *Four-Season Harvest* / *The New Organic Grower* — Eliot Coleman
- ◆ *Le Traité Rustica du potager*
- *Storey's Guide to Raising…* (poules, lapins, chèvres)

### Navigation, météo, montagne
- ★ *Mountaineering: The Freedom of the Hills*
- *Wilderness Navigation* — Burns
- ◆ *Manuel d'orientation* — FFRandonnée

### Technique et reconstruction
- ★ *The Knowledge: How to Rebuild Our World from Scratch* — Lewis Dartnell
- *ARRL Handbook* et *ARRL Antenna Book* (radio HF/VHF)

### Psychologie de la survie
- ★ *Deep Survival* — Laurence Gonzales
- *The Unthinkable* — Amanda Ripley

---

## Cartes papier

Le papier ne tombe pas en panne de batterie. IGN TOP25 :

- **2136 OT** — Gourdon, cœur de la Bouriane
- **2036 O** et **2036 E** — Salviac, Cazals
- **2036 OT** — Sarlat, Périgord Noir, vallée de la Dordogne

Vérifie les références et millésimes à l'achat : le découpage IGN évolue.

---

## Volumétrie

| | Taille |
|---|---|
| Modèles (3 profils) | ~35 Go |
| Corpus + index + vignettes | 30–60 Go |
| Wikipédia FR (ZIM, sans images) | ~10 Go |
| Wikipédia FR (ZIM complet) | ~50 Go |

Prévois un **SSD externe**, et une **copie de secours**. Un outil de survie qui
ne survit pas à une panne de disque n'a pas de sens.

## Si une URL est morte

Les documents publics bougent : réorganisations de sites, retraits d'archive.org.

```bash
make corpus-check    # signale les liens morts sans rien télécharger
```

Corrige l'URL dans `corpus/manifest.yaml`, ou dépose le fichier à la main dans
`corpus/public/<id>.pdf`. Le pipeline ignore les sources absentes plutôt que
d'échouer : le corpus reste exploitable sans elles.
