import Foundation
import SwiftUI

/// Réglages persistés. Les chemins ne sont pas devinés : l'utilisateur les
/// désigne une fois, et l'application les retient — index et modèles pèsent
/// des dizaines de gigaoctets et vivent souvent sur un disque externe.
@MainActor
final class Reglages: ObservableObject {
    @AppStorage("cheminIndex") var cheminIndex = ""
    @AppStorage("cheminVignettes") var cheminVignettes = ""
    @AppStorage("cheminUrgence") var cheminUrgence = ""
    @AppStorage("profilModele") var profilModele = Profil.defaut.rawValue
    @AppStorage("modeUrgenceAuDemarrage") var modeUrgenceAuDemarrage = false

    enum Profil: String, CaseIterable, Identifiable {
        case defaut, rapide, batterie, aucun

        var id: String { rawValue }

        var libelle: String {
            switch self {
            case .defaut:   return "Qualité — Mistral Small 24B (~13 Go)"
            case .rapide:   return "Rapide — Qwen3 30B-A3B (~17 Go)"
            case .batterie: return "Batterie — Qwen3 4B (~2,5 Go)"
            case .aucun:    return "Extraits seuls — aucun modèle"
            }
        }

        var detail: String {
            switch self {
            case .defaut:   return "Meilleur français. Le choix par défaut."
            case .rapide:   return "Trois à quatre fois plus rapide, prose un peu moins fine."
            case .batterie: return "Quand il reste 20 % de batterie et aucune prise à portée."
            case .aucun:    return "Rien n'est reformulé, donc rien ne peut être déformé."
            }
        }

        var identifiant: String? {
            switch self {
            case .defaut:   return "mlx-community/Mistral-Small-3.2-24B-Instruct-2506-4bit"
            case .rapide:   return "mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit"
            case .batterie: return "mlx-community/Qwen3-4B-Instruct-2507-4bit"
            case .aucun:    return nil
            }
        }
    }

    var profil: Profil { Profil(rawValue: profilModele) ?? .defaut }

    var indexURL: URL? { cheminIndex.isEmpty ? nil : URL(fileURLWithPath: cheminIndex) }
    var vignettesURL: URL? { cheminVignettes.isEmpty ? nil : URL(fileURLWithPath: cheminVignettes) }
    var urgenceURL: URL? { cheminUrgence.isEmpty ? nil : URL(fileURLWithPath: cheminUrgence) }

    var configure: Bool { indexURL != nil }
}

struct VueReglages: View {
    @ObservedObject var reglages: Reglages

    var body: some View {
        Form {
            Section("Emplacements") {
                ChampChemin(titre: "Index (survie.db)", chemin: $reglages.cheminIndex,
                            typeDossier: false)
                ChampChemin(titre: "Vignettes de pages", chemin: $reglages.cheminVignettes,
                            typeDossier: true)
                ChampChemin(titre: "Checklists d'urgence", chemin: $reglages.cheminUrgence,
                            typeDossier: true)
            }

            Section("Modèle") {
                Picker("Profil", selection: $reglages.profilModele) {
                    ForEach(Reglages.Profil.allCases) { p in
                        Text(p.libelle).tag(p.rawValue)
                    }
                }
                .pickerStyle(.radioGroup)
                Text(reglages.profil.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section {
                Toggle("Ouvrir en mode urgence", isOn: $reglages.modeUrgenceAuDemarrage)
                Text("""
                    Les checklists s'affichent sans charger le modèle. \
                    Ce chemin ne dépend ni de l'index ni des vecteurs : il \
                    fonctionne même si tout le reste est cassé.
                    """)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .padding()
    }
}

private struct ChampChemin: View {
    let titre: String
    @Binding var chemin: String
    let typeDossier: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(titre)
                Text(chemin.isEmpty ? "non défini" : chemin)
                    .font(.caption)
                    .foregroundStyle(chemin.isEmpty ? .red : .secondary)
                    .lineLimit(1)
                    .truncationMode(.head)
            }
            Spacer()
            Button("Choisir…") { choisir() }
        }
    }

    private func choisir() {
        let panneau = NSOpenPanel()
        panneau.canChooseFiles = !typeDossier
        panneau.canChooseDirectories = typeDossier
        panneau.allowsMultipleSelection = false
        if panneau.runModal() == .OK, let url = panneau.url {
            chemin = url.path
        }
    }
}
