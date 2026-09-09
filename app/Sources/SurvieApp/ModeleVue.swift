import Foundation
import SurvieCore
import SwiftUI

/// État de l'interface. Toute la logique vit dans SurvieCore ; cette classe ne
/// fait que relayer, et surtout ne décide de rien sur le fond.
@MainActor
final class ModeleVue: ObservableObject {

    enum Etat: Equatable {
        case aConfigurer(String)
        case pret
        case chargement(String)
        case interroge
    }

    @Published var etat: Etat = .pret
    @Published var question = ""
    @Published var reponse: Reponse?
    @Published var erreur: String?
    @Published var fichesUrgence: [FicheUrgence] = []
    @Published var ficheAffichee: FicheUrgence?
    @Published var modeUrgence = false

    private var engine: Engine?
    private let reglages: Reglages

    init(reglages: Reglages) {
        self.reglages = reglages
        self.modeUrgence = reglages.modeUrgenceAuDemarrage
        chargerUrgence()
    }

    // MARK: - Urgence

    /// Chargé en premier et indépendamment du reste : c'est le chemin qui doit
    /// survivre à la panne de tout le reste.
    func chargerUrgence() {
        guard let url = reglages.urgenceURL else { return }
        fichesUrgence = Urgence.charger(dossier: url)
    }

    func chercherUrgence(_ texte: String) {
        let trouvees = Urgence.chercher(texte, dans: fichesUrgence)
        ficheAffichee = trouvees.first
    }

    // MARK: - Moteur

    func preparer() async {
        guard let index = reglages.indexURL else {
            etat = .aConfigurer("Aucun index défini. Ouvre les réglages.")
            return
        }
        guard engine == nil else { return }

        etat = .chargement("Ouverture de l'index…")

        // Le modèle d'embeddings est facultatif : sans lui, la recherche
        // fonctionne en plein texte seul. Un outil de survie doit dégrader
        // proprement, jamais refuser de démarrer.
        var embedder: Embedder?
        var avertissement: String?
        do {
            embedder = try MLXEmbedder()
        } catch {
            avertissement = "Recherche plein texte seule : \(error.localizedDescription)"
        }

        do {
            if embedder != nil { etat = .chargement("Chargement du modèle…") }
            let generateur = reglages.profil.identifiant.map { MLXGenerateur(modele: $0) }
            engine = try Engine(db: index, embedder: embedder, generateur: generateur)
            erreur = avertissement
            etat = .pret
        } catch {
            // En revanche, un index bâti avec un AUTRE modèle d'embeddings ne
            // produit aucune erreur visible à l'usage, seulement du bruit. Là,
            // on refuse de démarrer plutôt que de répondre n'importe quoi.
            etat = .aConfigurer(error.localizedDescription)
        }
    }

    func interroger() async {
        let texte = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !texte.isEmpty else { return }

        // Le mode urgence court-circuite tout : ni index, ni modèle.
        if modeUrgence {
            chercherUrgence(texte)
            return
        }

        await preparer()
        guard let engine else { return }

        etat = .interroge
        erreur = nil
        do {
            reponse = try await engine.demander(texte)
        } catch {
            erreur = error.localizedDescription
        }
        etat = .pret
    }
}
