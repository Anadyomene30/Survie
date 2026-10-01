import SurvieCore
import SwiftUI

/// Réponse du modèle, avec ses citations rendues cliquables.
struct VueReponse: View {
    let reponse: Reponse
    @State private var citationOuverte: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(texteAttribue)
                .textSelection(.enabled)
                .environment(\.openURL, OpenURLAction { url in
                    guard url.scheme == "survie" else { return .systemAction }
                    citationOuverte = url.host
                    return .handled
                })

            if let r = reponse.rapport, !r.ok {
                Encadre(couleur: .red, icone: "quote.bubble.fill") {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Vérification des citations — \(r.valides)/\(r.citations) valides")
                            .bold()
                        ForEach(Array(r.problemes.enumerated()), id: \.offset) { _, p in
                            Text("• \(p.detail)").font(.caption)
                        }
                        Text("""
                            Une citation invalide signale une réponse \
                            potentiellement inventée. Vérifie directement les \
                            extraits ci-dessous.
                            """)
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    /// Transforme `[source p.42]` en lien interne.
    ///
    /// On réutilise l'expression régulière de `Validate` : deux analyses
    /// divergentes du même format finiraient par se contredire, et c'est le
    /// genre d'incohérence qui fait afficher une source pour une autre.
    private var texteAttribue: AttributedString {
        var sortie = AttributedString(reponse.texte)
        let ns = reponse.texte as NSString
        let plage = NSRange(location: 0, length: ns.length)
        for m in Validate.citation.matches(in: reponse.texte, range: plage).reversed() {
            guard let borne = Range(m.range, in: sortie) else { continue }
            let cle = ns.substring(with: m.range(at: 1)).lowercased()
            sortie[borne].link = URL(string: "survie://\(cle)")
            sortie[borne].foregroundColor = .accentColor
        }
        return sortie
    }
}

/// Extraits transmis au modèle, avec la vignette de la page citée.
struct VueSources: View {
    let hits: [Retrieve.Hit]
    let vignettes: URL?
    @State private var deplie: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("SOURCES")
                .font(.system(.caption, design: .monospaced)).bold()
                .foregroundStyle(.secondary)

            ForEach(Array(hits.enumerated()), id: \.element.passage.id) { i, hit in
                let p = hit.passage
                DisclosureGroup(isExpanded: lien(p.id)) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(p.texte).font(.callout).textSelection(.enabled)

                        // La vignette est le point qui compte : elle donne accès
                        // au schéma d'origine — nœud, attelle, planche botanique
                        // — que la transcription seule ne restitue pas.
                        if let image = vignette(p) {
                            Image(nsImage: image)
                                .resizable().scaledToFit()
                                .frame(maxHeight: 420)
                                .border(Color.secondary.opacity(0.3))
                        }
                    }
                    .padding(.top, 6)
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text("\(i + 1).").foregroundStyle(.secondary)
                            Text(p.citation)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundStyle(Color.accentColor)
                            if p.qualite < 0.6 {
                                Image(systemName: "text.badge.xmark")
                                    .foregroundStyle(.orange)
                                    .help("Texte océrisé de qualité incertaine")
                            }
                        }
                        Text(p.reference).font(.caption)
                        if !p.section.isEmpty {
                            Text("section « \(p.section) »")
                                .font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
    }

    private func lien(_ id: String) -> Binding<Bool> {
        Binding(get: { deplie.contains(id) },
                set: { ouvert in
                    if ouvert { deplie.insert(id) } else { deplie.remove(id) }
                })
    }

    private func vignette(_ p: Passage) -> NSImage? {
        guard let dossier = vignettes, let rel = p.image else { return nil }
        return NSImage(contentsOf: dossier.appendingPathComponent(rel))
    }
}
