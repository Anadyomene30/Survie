# SurvieApp — application en barre de menus

Cette cible n'est pas encore branchée dans `Package.swift` : elle dépend de MLX,
qu'il faut d'abord valider sur la machine (phase 0 du plan). L'ordre est
délibéré — `SurvieCore` se compile et se teste sans réseau ni modèle, ce qui
permet de vérifier la parité avec l'implémentation Python avant d'introduire
la moindre dépendance lourde.

## Ce qu'il reste à écrire

| Fichier | Rôle |
|---|---|
| `SurvieApp.swift` | `@main`, `MenuBarExtra`, cycle de vie |
| `PanneauView.swift` | panneau flottant : saisie, réponse, citations cliquables |
| `SourcesView.swift` | vignette de la page citée, zoomable |
| `UrgenceView.swift` | mode urgence : gros caractères, fond sombre, checklists |
| `MLXEmbedder.swift` | `Embedder` via `MLXEmbedders` |
| `MLXGenerateur.swift` | `Generateur` via `MLXLLM`, en flux |
| `Raccourci.swift` | raccourci global ⌥⌘S |

`SurvieCore` expose déjà tout le nécessaire : `Engine.demander(_:)` renvoie une
`Reponse` avec ses `hits`, son `rapport` de validation et son drapeau
`identification`. L'interface n'a rien à décider — elle affiche.

## Points de vigilance

- **Aucun appel réseau.** Ni `URLSession`, ni téléchargement de modèle au
  premier lancement : les poids doivent être présents sur le disque, chemin
  fourni par l'utilisateur. Un test d'intégration lance l'app réseau coupé.
- **Sandbox et vignettes.** Les images de pages vivent hors du bundle
  (`build/pages/`). Prévoir un accès à ce dossier, ou un signet de sécurité.
- **Mémoire.** Charger le modèle 24B (~13 Go) et la matrice de vecteurs en même
  temps ; surveiller la pression mémoire et libérer le modèle en mode batterie.
- **Citations cliquables.** Le texte de réponse contient `[source p.42]` :
  les transformer en liens vers `SourcesView` en réutilisant la même expression
  régulière que `Validate` pour éviter deux analyses divergentes.
