import Foundation
import SurvieCore

/// CLI Swift : sert à vérifier la PARITÉ avec l'implémentation Python.
/// Les deux doivent produire les mêmes extraits sur eval/golden.yaml.
///
///     swift run survie-cli ../build/survie.db "comment traiter une hypothermie"
///     swift run survie-cli --json ../build/survie.db "…"   # pour scripts/parite.py
@main
struct SurvieCLI {

    /// Vue sérialisable d'une réponse, consommée par `scripts/parite.py`.
    ///
    /// Comparer deux sorties humaines à coups d'expressions régulières serait
    /// fragile : la moindre retouche de mise en forme d'un côté ferait échouer
    /// la parité sans qu'aucun résultat n'ait bougé. On expose donc exactement
    /// ce qui doit coïncider, et rien d'autre.
    struct SortieJSON: Encodable {
        struct HitJSON: Encodable {
            let citation: String
            let section: String
            let score: Double
            let methodes: String
        }
        let question: String
        let refus: Bool
        let identification: Bool
        let couverture: Double
        let termesInconnus: [String]
        let hits: [HitJSON]
    }

    static func main() async {
        var args = Array(CommandLine.arguments.dropFirst())
        var json = false
        if let i = args.firstIndex(of: "--json") {
            json = true
            args.remove(at: i)
        }

        guard args.count >= 2 else {
            FileHandle.standardError.write(
                "usage: survie-cli [--json] <chemin/survie.db> <question>\n".data(using: .utf8)!)
            exit(2)
        }

        let question = args[1...].joined(separator: " ")
        do {
            let engine = try Engine(db: URL(fileURLWithPath: args[0]))
            let rep = try await engine.demander(question)
            if json {
                afficherJSON(rep)
            } else {
                afficher(rep)
            }
        } catch {
            FileHandle.standardError.write(
                "Erreur : \(error.localizedDescription)\n".data(using: .utf8)!)
            exit(1)
        }
    }

    // MARK: - Sorties

    private static func afficherJSON(_ rep: Reponse) {
        let sortie = SortieJSON(
            question: rep.question,
            refus: rep.refus,
            identification: rep.identification,
            // Arrondi : la comparaison porte sur le classement et l'ordre de
            // grandeur du score, pas sur le dernier bit d'un Double.
            couverture: arrondi(rep.signaux?.couverture ?? 0),
            termesInconnus: rep.signaux?.termesInconnus ?? [],
            hits: rep.hits.map {
                .init(citation: $0.passage.citation, section: $0.passage.section,
                      score: arrondi($0.score), methodes: $0.methodes)
            })
        let encodeur = JSONEncoder()
        encodeur.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        if let data = try? encodeur.encode(sortie) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write("\n".data(using: .utf8)!)
        }
    }

    private static func arrondi(_ x: Double) -> Double {
        (x * 1e9).rounded() / 1e9
    }

    private static func afficher(_ rep: Reponse) {
        if rep.refus {
            print(rep.texte)
            return
        }

        // Affiché AVANT la réponse : un avertissement qu'il faut faire défiler
        // pour découvrir ne sert à rien dans l'urgence.
        if !rep.divergences.isEmpty {
            print(Divergences.renduHumain(rep.divergences))
        }

        if rep.texte.isEmpty {
            print("Mode extraits seuls — aucun modèle chargé, rien n'est reformulé.\n")
        } else {
            print(rep.texte)
            if let r = rep.rapport {
                print("\ncitations : \(r.valides)/\(r.citations) valides")
                for p in r.problemes { print("  ⚠ \(p.genre.rawValue) : \(p.detail)") }
            }
        }

        print(String(repeating: "─", count: 70))
        print("SOURCES")
        for (i, h) in rep.hits.enumerated() {
            let p = h.passage
            print("\n\(i + 1). \(p.citation)  \(p.reference)")
            if !p.section.isEmpty { print("   section « \(p.section) »") }
            print("   score \(String(format: "%.4f", h.score)) (\(h.methodes))")
        }

        if let (min, max) = rep.ecartDates {
            print("\n  Sources publiées entre \(min) et \(max) : vérifie les dates "
                + "sur les points médicaux.")
        }
        if rep.identification {
            print("\nQuestion d'identification : le système ne conclut jamais qu'une")
            print("espèce est comestible. Dans le doute, s'abstenir.")
        }
    }
}
