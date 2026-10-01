import Foundation

/// Doctrines périmées présentes dans le corpus.
///
/// Le corpus contient délibérément des manuels anciens, excellents sur le feu
/// ou la navigation et périmés — parfois dangereusement — sur certains gestes
/// de secours. Le modèle n'a aucun moyen de savoir qu'un passage bien écrit de
/// 1992 a été invalidé depuis.
///
/// Parité avec `cli/survie/divergence.py`. Le registre lui-même reste en YAML
/// (`corpus/divergences.yaml`) et est converti en JSON à la construction de
/// l'index, pour éviter d'embarquer un analyseur YAML dans l'application.
public struct Divergence: Sendable, Codable, Identifiable {
    public let id: String
    public let titre: String
    public let sujet: [String]
    public let ancienne: String
    public let actuelle: String
    public let bascule: Int
    public let gravite: String
    public var source: String = ""

    public var critique: Bool { gravite == "critique" }
}

public enum Divergences {
    /// Au-delà, l'avertissement devient un mur de texte que personne ne lit, et
    /// le point réellement pertinent s'y noie. Mieux vaut trois avertissements
    /// lus que huit ignorés.
    public static let maximum = 3
    public static let ecartAnnees = 15

    public static func charger(_ url: URL) -> [Divergence] {
        guard let data = try? Data(contentsOf: url) else { return [] }
        return (try? JSONDecoder().decode([Divergence].self, from: data)) ?? []
    }

    /// Divergences concernées par cette question ou par les extraits retenus.
    public static func detecter(question: String, hits: [Retrieve.Hit],
                                registre: [Divergence]) -> [Divergence] {
        let q = Retrieve.plier(question)

        var parQuestion: [Divergence] = [], parExtraits: [Divergence] = []
        for d in registre {
            let sujets = d.sujet.map(Retrieve.plier)
            if sujets.contains(where: { q.contains($0) }) {
                parQuestion.append(d)
                continue
            }
            // Sur les seuls extraits, deux conditions. Un signal net : terme
            // composé ou deux termes distincts. Et surtout, ce signal doit venir
            // d'un extrait ANTÉRIEUR à la bascule — une doctrine périmée ne peut
            // être reproduite que par un document qui la précède. Un extrait
            // ancien quelconque ne suffit pas : une flore de 1906 faisait
            // avertir sur le chlore à une question sur le garrot.
            let anciens = Retrieve.plier(
                hits.filter { ($0.passage.date ?? Int.max) < d.bascule }
                    .map { "\($0.passage.section) \($0.passage.texte)" }
                    .joined(separator: " "))
            let touches = sujets.filter { anciens.contains($0) }
            let assezNet = touches.contains(where: { $0.contains(" ") }) || touches.count >= 2
            if assezNet {
                parExtraits.append(d)
            }
        }
        let tri: (Divergence, Divergence) -> Bool = {
            $0.critique != $1.critique ? $0.critique : $0.id < $1.id
        }
        return Array((parQuestion.sorted(by: tri) + parExtraits.sorted(by: tri))
            .prefix(maximum))
    }

    public static func ecartDeDates(_ hits: [Retrieve.Hit]) -> (Int, Int)? {
        let dates = Set(hits.compactMap(\.passage.date)).sorted()
        guard let min = dates.first, let max = dates.last,
              dates.count >= 2, max - min > ecartAnnees else { return nil }
        return (min, max)
    }

    /// Bloc inséré dans l'invite, AVANT les extraits : ce qui suit doit être lu
    /// à sa lumière, et un avertissement relégué en fin d'invite pèse moins
    /// qu'un texte de manuel bien tourné.
    /// Affichage direct, en mode extraits seuls — sans modèle pour reformuler.
    ///
    /// Parité avec `rendu_humain` côté Python : c'est le seul avertissement que
    /// voit l'utilisateur quand aucun modèle n'est chargé, et le mode sans
    /// modèle est précisément celui dans lequel un extrait périmé est restitué
    /// tel quel, sans qu'une reformulation puisse le corriger.
    public static func renduHumain(_ divergences: [Divergence]) -> String {
        guard !divergences.isEmpty else { return "" }
        var l = ["", "⚠ DOCTRINES AYANT CHANGÉ — les extraits peuvent être périmés", ""]
        for d in divergences {
            l.append("\(d.critique ? "‼" : "•") \(d.titre)  (changement vers \(d.bascule))")
            l.append("    Périmé : \(compacter(d.ancienne))")
            l.append("    Actuel : \(compacter(d.actuelle))")
            l.append("")
        }
        return l.joined(separator: "\n")
    }

    /// Réduit les blancs multiples à une espace : le registre YAML plie ses
    /// textes sur plusieurs lignes, ce qui n'a pas de sens sur une sortie
    /// terminal déjà mise en forme.
    private static func compacter(_ s: String) -> String {
        s.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    public static func encart(_ divergences: [Divergence],
                              ecart: (Int, Int)? = nil) -> String {
        guard !divergences.isEmpty || ecart != nil else { return "" }
        var l = ["AVERTISSEMENT — DOCTRINES AYANT CHANGÉ", ""]
        if !divergences.isEmpty {
            l.append("""
                Les extraits ci-dessous peuvent contenir des recommandations \
                périmées. Sur les points suivants, tu dois suivre la doctrine \
                ACTUELLE, et signaler explicitement que l'ancienne version est \
                dépassée si un extrait la reproduit :
                """)
            l.append("")
            for d in divergences {
                l.append("\(d.critique ? "‼ " : "• ")\(d.titre) (changement vers \(d.bascule))")
                l.append("   PÉRIMÉ  : \(d.ancienne)")
                l.append("   ACTUEL  : \(d.actuelle)")
                l.append("")
            }
        }
        if let e = ecart {
            l.append("Les extraits proviennent de sources publiées entre \(e.0) et "
                   + "\(e.1). Mentionne la date des sources que tu cites sur les "
                   + "points médicaux, et signale toute divergence entre elles.")
            l.append("")
        }
        l.append("Cet avertissement fait autorité sur les extraits. Il n'a pas à "
               + "être cité comme une source : c'est une consigne, pas un document.")
        return l.joined(separator: "\n")
    }
}
