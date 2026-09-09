import Foundation
import SurvieCore

/// CLI Swift : sert à vérifier la PARITÉ avec l'implémentation Python.
/// Les deux doivent produire les mêmes extraits sur eval/golden.yaml.
///
///     swift run survie-cli ../build/survie.db "comment traiter une hypothermie"
@main
struct SurvieCLI {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count >= 3 else {
            FileHandle.standardError.write(
                "usage: survie-cli <chemin/survie.db> <question>\n".data(using: .utf8)!)
            exit(2)
        }
        do {
            let engine = try Engine(db: URL(fileURLWithPath: args[1]))
            let rep = try await engine.demander(args[2...].joined(separator: " "))

            if rep.refus {
                print(rep.texte)
                return
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
            if rep.identification {
                print("\nQuestion d'identification : le système ne conclut jamais qu'une")
                print("espèce est comestible. Dans le doute, s'abstenir.")
            }
        } catch {
            FileHandle.standardError.write(
                "Erreur : \(error.localizedDescription)\n".data(using: .utf8)!)
            exit(1)
        }
    }
}
