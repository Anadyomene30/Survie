import SurvieCore
import SwiftUI

/// Panneau principal. Il affiche ce que le moteur décide ; il ne décide rien.
struct PanneauView: View {
    @ObservedObject var modele: ModeleVue
    @ObservedObject var reglages: Reglages
    @FocusState private var saisieActive: Bool

    var body: some View {
        VStack(spacing: 0) {
            barre
            Divider()

            if modele.modeUrgence {
                VueUrgence(modele: modele)
            } else {
                contenu
            }

            Divider()
            saisie
        }
        .background(modele.modeUrgence ? Color.black : Color(nsColor: .windowBackgroundColor))
        .onAppear { saisieActive = true }
    }

    // MARK: - Barre

    private var barre: some View {
        HStack(spacing: 12) {
            Text(modele.modeUrgence ? "URGENCE" : "SURVIE")
                .font(.system(.caption, design: .monospaced)).bold()
                .foregroundStyle(modele.modeUrgence ? .red : .secondary)

            if case .chargement(let quoi) = modele.etat {
                ProgressView().controlSize(.small)
                Text(quoi).font(.caption).foregroundStyle(.secondary)
            }

            Spacer()

            Toggle(isOn: $modele.modeUrgence) {
                Label("Urgence", systemImage: "cross.case.fill")
            }
            .toggleStyle(.button)
            .help("Checklists servies telles quelles, sans modèle. "
                + "Fonctionne même si l'index est absent.")

            SettingsLink { Image(systemName: "gearshape") }
                .buttonStyle(.borderless)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Contenu

    @ViewBuilder
    private var contenu: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if case .aConfigurer(let message) = modele.etat {
                    Encadre(couleur: .orange, icone: "exclamationmark.triangle.fill") {
                        Text(message)
                    }
                }
                if let erreur = modele.erreur {
                    Encadre(couleur: .red, icone: "xmark.octagon.fill") { Text(erreur) }
                }

                if let rep = modele.reponse {
                    // L'avertissement passe AVANT la réponse : un avertissement
                    // qu'il faut faire défiler pour découvrir ne sert à rien.
                    ForEach(rep.divergences) { VueDivergence(divergence: $0) }

                    if rep.refus {
                        Encadre(couleur: .secondary, icone: "questionmark.circle") {
                            Text(rep.texte)
                        }
                    } else {
                        if !rep.texte.isEmpty {
                            VueReponse(reponse: rep)
                        } else {
                            Text("Mode extraits seuls — aucun modèle chargé, "
                               + "rien n'est reformulé.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if rep.identification { avertissementIdentification }
                        VueSources(hits: rep.hits, vignettes: reglages.vignettesURL)
                    }
                } else if case .pret = modele.etat {
                    accueil
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var avertissementIdentification: some View {
        Encadre(couleur: .orange, icone: "leaf.fill") {
            VStack(alignment: .leading, spacing: 4) {
                Text("Question d'identification").bold()
                Text("""
                    Le système ne conclut jamais qu'une espèce est comestible. \
                    Vérifie les critères ci-dessous contre une flore, et compare \
                    avec les sosies toxiques cités. Dans le doute, s'abstenir.
                    """)
            }
        }
    }

    private var accueil: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Pose une question.").font(.title3)
            Text("""
                Les réponses viennent uniquement des ouvrages indexés, avec leur \
                source et leur page. Si le corpus ne couvre pas la question, \
                le système le dit plutôt que d'inventer.
                """)
                .foregroundStyle(.secondary)
            Divider().padding(.vertical, 4)
            Label("En urgence, bascule en mode Urgence : réponse instantanée, "
                + "sans charger le modèle.", systemImage: "cross.case")
                .font(.callout).foregroundStyle(.secondary)
        }
    }

    // MARK: - Saisie

    private var saisie: some View {
        HStack(spacing: 8) {
            TextField(modele.modeUrgence ? "Que se passe-t-il ?" : "Ta question…",
                      text: $modele.question)
                .textFieldStyle(.plain)
                .font(modele.modeUrgence ? .title2 : .body)
                .focused($saisieActive)
                .onSubmit { Task { await modele.interroger() } }

            if case .interroge = modele.etat {
                ProgressView().controlSize(.small)
            } else {
                Button {
                    Task { await modele.interroger() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                }
                .buttonStyle(.borderless)
                .disabled(modele.question.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
        .padding(12)
    }
}

// MARK: - Composants

struct Encadre<Contenu: View>: View {
    let couleur: Color
    let icone: String
    @ViewBuilder let contenu: Contenu

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icone).foregroundStyle(couleur)
            contenu.textSelection(.enabled)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(couleur.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct VueDivergence: View {
    let divergence: Divergence

    var body: some View {
        Encadre(couleur: divergence.critique ? .red : .orange,
                icone: "clock.badge.exclamationmark.fill") {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(divergence.titre) — doctrine changée vers \(divergence.bascule)")
                    .bold()
                Label { Text(divergence.ancienne) } icon: {
                    Text("PÉRIMÉ").font(.caption2).bold().foregroundStyle(.red)
                }
                Label { Text(divergence.actuelle).bold() } icon: {
                    Text("ACTUEL").font(.caption2).bold().foregroundStyle(.green)
                }
            }
            .font(.callout)
        }
    }
}
