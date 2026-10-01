import Foundation
import SurvieCore

#if canImport(MLXEmbedders) && canImport(MLXLLM)
import MLX
import MLXEmbedders
import MLXLLM
import MLXLMCommon

/// Vecteurs de requête via MLX.
///
/// POINT DE VIGILANCE — le pooling. BGE-M3 produit son vecteur dense à partir
/// du token CLS. Si la bibliothèque applique un mean pooling, les vecteurs
/// restent normalisés et l'application fonctionne, mais la qualité de recherche
/// est dégradée SANS AUCUN SIGNAL D'ERREUR. Le pooling doit donc être celui
/// qu'a utilisé `ingest/embed.py` pour construire l'index. Voir la procédure de
/// validation dans docs/DEMARRAGE-MAC.md.
final class MLXEmbedder: Embedder, @unchecked Sendable {
    let nom: String
    let backend = "mlx"
    private let conteneur: ModelContainer
    private let pooling: Pooling

    /// `BAAI/bge-m3` ne publie que `pytorch_model.bin` : ni mlx-embeddings ni
    /// mlx-swift n'y trouvent de safetensors. C'est la conversion MLX du même
    /// modèle qu'il faut charger — la même que celle qui a bâti l'index, sans
    /// quoi le contrôle du vecteur témoin refusera de servir.
    init(modele: String = "mlx-community/bge-m3-mlx-fp16",
         pooling: Pooling = .cls) throws {
        self.nom = modele
        self.pooling = pooling
        self.conteneur = try MLXEmbedders.loadModelContainer(
            configuration: ModelConfiguration(id: modele))
    }

    func encoder(_ textes: [String], requete: Bool) throws -> [[Float]] {
        // Les index sont construits à partir de textes bruts (bge-m3 n'attend
        // pas de préfixe d'instruction). Si l'on bascule sur e5, il faudra
        // préfixer « query: » / « passage: » ICI ET dans ingest/embed.py.
        var sortie: [[Float]] = []
        for texte in textes {
            let vecteur = conteneur.perform { modele, tokenizer in
                let jetons = tokenizer.encode(text: texte)
                let sortieModele = modele(MLXArray(jetons).expandedDimensions(axis: 0))
                return pooling(sortieModele).asArray(Float.self)
            }
            sortie.append(normaliser(vecteur))
        }
        return sortie
    }

    /// Les vecteurs de l'index sont normalisés : le produit scalaire vaut alors
    /// le cosinus. Renormaliser ici garantit que la requête suit la même règle.
    private func normaliser(_ v: [Float]) -> [Float] {
        let norme = sqrt(v.reduce(0) { $0 + $1 * $1 })
        return norme > 1e-9 ? v.map { $0 / norme } : v
    }
}

/// Génération locale. Aucun appel réseau : les poids sont sur le disque.
final class MLXGenerateur: Generateur, @unchecked Sendable {
    let nom: String
    private var conteneur: ModelContainer?

    init(modele: String) {
        self.nom = modele
    }

    func generer(systeme: String, utilisateur: String) async throws -> String {
        if conteneur == nil {
            conteneur = try await LLMModelFactory.shared.loadContainer(
                configuration: ModelConfiguration(id: nom))
        }
        guard let conteneur else { return "" }
        return try await conteneur.perform { contexte in
            let entree = try await contexte.processor.prepare(input: UserInput(chat: [
                .system(systeme), .user(utilisateur),
            ]))
            var texte = ""
            let _ = try MLXLMCommon.generate(
                input: entree, parameters: GenerateParameters(temperature: 0.2),
                context: contexte
            ) { jetons in
                texte = contexte.tokenizer.decode(tokens: jetons)
                return jetons.count >= 900 ? .stop : .more
            }
            return texte
        }
    }
}

#else

// MLX absent : l'application reste utilisable en mode extraits seuls, et le
// mode urgence fonctionne intégralement. C'est délibéré — un outil de survie
// doit dégrader proprement, jamais refuser de démarrer.

final class MLXEmbedder: Embedder, @unchecked Sendable {
    let nom = "aucun"
    let backend = "mlx"
    init(modele: String = "", pooling: Int = 0) throws {
        throw NSError(domain: "Survie", code: 1, userInfo: [
            NSLocalizedDescriptionKey:
                "MLX n'est pas disponible dans cette compilation. Décommente les "
              + "dépendances mlx-swift dans app/Package.swift, puis recompile. "
              + "Le mode urgence, lui, fonctionne déjà.",
        ])
    }
    func encoder(_ textes: [String], requete: Bool) throws -> [[Float]] { [] }
}

final class MLXGenerateur: Generateur, @unchecked Sendable {
    let nom = "aucun"
    init(modele: String) {}
    func generer(systeme: String, utilisateur: String) async throws -> String { "" }
}

#endif
