import Foundation

/// Mode urgence — checklists servies telles quelles, sans modèle.
///
/// Ce chemin ne dépend de rien : ni index, ni vecteurs, ni modèle de langue.
/// Il lit les fichiers Markdown directement. C'est délibéré, et c'est la
/// propriété la plus importante de ce type : si l'index est corrompu, si le
/// modèle refuse de se charger, si la machine est en train de mourir, les
/// gestes qui sauvent restent accessibles instantanément.
///
/// Rien n'est reformulé, donc rien ne peut être déformé.
/// Parité avec `cli/survie/urgence.py`.
public struct FicheUrgence: Sendable, Identifiable {
    public let nom: String
    public let titre: String
    public let declencheurs: [String]
    public let corps: String

    public var id: String { nom }
}

public enum Urgence {

    public static func charger(dossier: URL) -> [FicheUrgence] {
        let fm = FileManager.default
        guard let fichiers = try? fm.contentsOfDirectory(at: dossier,
                                                         includingPropertiesForKeys: nil)
        else { return [] }
        return fichiers
            .filter { $0.pathExtension == "md" }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
            .compactMap(lire)
    }

    static func lire(_ url: URL) -> FicheUrgence? {
        guard let texte = try? String(contentsOf: url, encoding: .utf8),
              texte.hasPrefix("---") else { return nil }

        let parties = texte.components(separatedBy: "\n---")
        guard parties.count >= 2 else { return nil }
        let entete = String(parties[0].dropFirst(3))
        let corps = parties.dropFirst().joined(separator: "\n---")
            .trimmingCharacters(in: .whitespacesAndNewlines)

        var titre = url.deletingPathExtension().lastPathComponent
        var declencheurs: [String] = []
        for ligne in entete.split(separator: "\n") {
            if ligne.hasPrefix("titre:") {
                titre = String(ligne.dropFirst(6)).trimmingCharacters(in: .whitespaces)
            } else if ligne.hasPrefix("declencheurs:") {
                declencheurs = String(ligne.dropFirst(13))
                    .trimmingCharacters(in: .whitespaces)
                    .trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
                    .split(separator: ",")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
            }
        }
        return FicheUrgence(nom: url.deletingPathExtension().lastPathComponent,
                            titre: titre, declencheurs: declencheurs, corps: corps)
    }

    /// Fiches pertinentes, les mieux notées d'abord.
    ///
    /// Notation volontairement simple et lisible. En urgence, un classement
    /// qu'on ne sait pas expliquer vaut moins qu'un classement grossier mais
    /// prévisible.
    public static func chercher(_ requete: String,
                                dans fiches: [FicheUrgence]) -> [FicheUrgence] {
        let q = Retrieve.plier(requete)
        let mots = q.split(whereSeparator: { !$0.isLetter && !$0.isNumber })
            .map(String.init).filter { $0.count >= 3 }

        var notes: [(FicheUrgence, Int)] = []
        for f in fiches {
            var note = 0
            for d in f.declencheurs {
                let dp = Retrieve.plier(d)
                if q.contains(dp) {
                    // Un déclencheur composé (« ne respire pas ») est un signal
                    // bien plus fort qu'un mot isolé : il ne se trouve pas par
                    // hasard.
                    note += dp.contains(" ") ? 10 : 6
                } else if mots.contains(where: { dp.contains($0) || $0.contains(dp) }) {
                    note += 2
                }
            }
            let titre = Retrieve.plier(f.titre)
            if mots.contains(where: { titre.contains($0) }) { note += 3 }
            let corps = Retrieve.plier(f.corps)
            note += Set(mots).filter { corps.contains($0) }.count
            if note > 0 { notes.append((f, note)) }
        }
        return notes
            .sorted { $0.1 != $1.1 ? $0.1 > $1.1 : $0.0.nom < $1.0.nom }
            .map(\.0)
    }
}
