import SurvieCore
import SwiftUI

/// Mode urgence : gros caractères, fond sombre, aucune dépendance.
///
/// Ni index, ni vecteurs, ni modèle. Si tout le reste est cassé, ceci
/// fonctionne encore — c'est toute la raison d'être de ce mode.
struct VueUrgence: View {
    @ObservedObject var modele: ModeleVue

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if modele.fichesUrgence.isEmpty {
                    Encadre(couleur: .orange, icone: "exclamationmark.triangle.fill") {
                        Text("Aucune checklist trouvée. Indique le dossier "
                           + "regional/urgence dans les réglages.")
                    }
                } else if let fiche = modele.ficheAffichee {
                    detail(fiche)
                } else {
                    sommaire
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .foregroundStyle(.white)
    }

    private var sommaire: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("APPELER LE 15")
                .font(.system(size: 30, weight: .heavy, design: .rounded))
                .foregroundStyle(.red)
            Text("18 pompiers · 112 europe · 114 par SMS quand la voix ne passe pas")
                .font(.title3).foregroundStyle(.white.opacity(0.85))
                .padding(.bottom, 12)

            ForEach(modele.fichesUrgence) { fiche in
                Button { modele.ficheAffichee = fiche } label: {
                    HStack {
                        Text(fiche.titre)
                            .font(.title3).multilineTextAlignment(.leading)
                        Spacer()
                        Image(systemName: "chevron.right")
                    }
                    .padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                Divider().background(.white.opacity(0.2))
            }
        }
    }

    private func detail(_ fiche: FicheUrgence) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Button { modele.ficheAffichee = nil } label: {
                Label("Toutes les checklists", systemImage: "chevron.left")
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white.opacity(0.7))

            Text(fiche.titre)
                .font(.system(size: 26, weight: .bold, design: .rounded))
                .foregroundStyle(.red)

            // Rendu tel quel : rien n'est reformulé, donc rien ne peut être
            // déformé. C'est le chemin le plus sûr du système.
            Text(fiche.corps)
                .font(.system(size: 17))
                .lineSpacing(4)
                .textSelection(.enabled)
        }
    }
}
