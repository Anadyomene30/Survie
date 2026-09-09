import Foundation

/// Vérification a posteriori des citations produites par le modèle.
///
/// Garde-fou principal du système. Un modèle contraint par une consigne peut
/// malgré tout inventer une référence plausible — c'est le mode d'échec le plus
/// insidieux, parce qu'une citation fabriquée donne à une phrase fausse
/// l'apparence d'une phrase vérifiée.
public enum Validate {

    public enum Genre: String, Sendable {
        case sourceInconnue = "source-inconnue"
        case pageHorsExtrait = "page-hors-extrait"
        case phraseSansSource = "phrase-sans-source"
    }

    public struct Probleme: Sendable {
        public let genre: Genre
        public let detail: String
        public let extrait: String
    }

    public struct Rapport: Sendable {
        public let citations: Int
        public let valides: Int
        public let problemes: [Probleme]
        public var ok: Bool { problemes.isEmpty }
        public var taux: Double { citations > 0 ? Double(valides) / Double(citations) : 0 }
    }

    /// `[identifiant p.42]`
    ///
    /// Publique à dessein : l'interface s'en sert pour rendre les citations
    /// cliquables. Deux expressions régulières distinctes pour le même format
    /// finiraient par diverger, et afficheraient une source pour une autre.
    public static let citation = try! NSRegularExpression(
        pattern: #"\[([a-z0-9][a-z0-9._-]*)\s+p\.\s*(\d+)\]"#, options: [.caseInsensitive])

    public static func verifier(reponse: String, hits: [Retrieve.Hit],
                                exigerSourceParPhrase: Bool = true) -> Rapport {
        // Pages réellement transmises, par source. Toute la plage début..fin est
        // acceptée : un fragment qui enjambe une fin de page autorise
        // légitimement la citation des deux pages.
        var autorisees: [String: Set<Int>] = [:]
        for h in hits {
            let p = h.passage
            autorisees[p.sourceID, default: []].formUnion(p.pageDebut...p.pageFin)
        }

        var problemes: [Probleme] = []
        var total = 0, valides = 0
        let ns = reponse as NSString

        for m in citation.matches(in: reponse, range: NSRange(location: 0, length: ns.length)) {
            total += 1
            let sid = ns.substring(with: m.range(at: 1)).lowercased()
            let page = Int(ns.substring(with: m.range(at: 2))) ?? -1
            let texte = ns.substring(with: m.range)
            guard let pages = autorisees[sid] else {
                problemes.append(Probleme(genre: .sourceInconnue,
                    detail: "« \(sid) » ne fait pas partie des extraits transmis",
                    extrait: texte))
                continue
            }
            if pages.contains(page) {
                valides += 1
            } else {
                let liste = pages.sorted()
                let resume = liste.count <= 4
                    ? liste.map(String.init).joined(separator: ", ")
                    : "\(liste.first!)–\(liste.last!)"
                problemes.append(Probleme(genre: .pageHorsExtrait,
                    detail: "« \(sid) » a été transmis pour la ou les pages \(resume), "
                          + "pas la page \(page)",
                    extrait: texte))
            }
        }

        if exigerSourceParPhrase {
            for phrase in phrases(reponse) {
                let t = phrase.trimmingCharacters(in: .whitespacesAndNewlines)
                // On ne réclame pas de source aux titres, listes, transitions
                // courtes, ni à la formule de prudence imposée par la règle de
                // sûreté — l'exiger sourcée pousserait le modèle à lui coller
                // une citation inventée pour satisfaire le validateur.
                if t.count < 45 || t.hasPrefix("#") || t.hasPrefix("-") || t.hasPrefix("*") {
                    continue
                }
                let plie = Retrieve.plier(t)
                if plie.contains("dans le doute") && plie.contains("abstenir") { continue }
                let r = NSRange(location: 0, length: (t as NSString).length)
                if citation.firstMatch(in: t, range: r) == nil {
                    problemes.append(Probleme(genre: .phraseSansSource,
                        detail: "affirmation sans citation",
                        extrait: String(t.prefix(110))))
                }
            }
        }
        return Rapport(citations: total, valides: valides, problemes: problemes)
    }

    /// Phrases du texte, chacune accompagnée des citations qui la suivent.
    ///
    /// Subtilité : la citation suit le point final (« … au froissement. [src p.3] »)
    /// et contient elle-même un point. Un découpage naïf sur la ponctuation
    /// détacherait la citation de la phrase qu'elle source, et le validateur
    /// signalerait comme non sourcée une phrase parfaitement citée.
    static func phrases(_ texte: String) -> [String] {
        var out: [String] = []
        var courante = ""
        var i = texte.startIndex
        while i < texte.endIndex {
            let c = texte[i]
            courante.append(c)
            if c == "." || c == "!" || c == "?" || c == "\n" {
                // Absorber les citations qui suivent immédiatement.
                var j = texte.index(after: i)
                while j < texte.endIndex, texte[j] == " " { j = texte.index(after: j) }
                if j < texte.endIndex, texte[j] == "[",
                   let fin = texte[j...].firstIndex(of: "]") {
                    courante += texte[texte.index(after: i)...fin]
                    i = texte.index(after: fin)
                    continue
                }
                out.append(courante)
                courante = ""
            }
            i = texte.index(after: i)
        }
        if !courante.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            out.append(courante)
        }
        return out
    }
}
