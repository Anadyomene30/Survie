import XCTest
@testable import SurvieCore

/// Parité avec l'implémentation Python de référence.
///
/// Le moteur existe deux fois : en Python, où l'itération est rapide et où
/// tourne l'évaluation, et en Swift, qui fait tourner l'application. Les deux
/// doivent se comporter identiquement, sans quoi l'évaluation ne dit plus rien
/// de ce que l'utilisateur obtient réellement.
///
/// Ces cas sont les mêmes que ceux de tests/test_divergence.py et
/// tests/test_urgence.py.
final class PariteTests: XCTestCase {

    // MARK: - Doctrines périmées

    let registre = [
        Divergence(id: "garrot", titre: "Pose et desserrage du garrot",
                   sujet: ["garrot", "tourniquet", "hémorragie", "saignement abondant"],
                   ancienne: "Le garrot est un dernier recours, à desserrer périodiquement.",
                   actuelle: "Le garrot n'est JAMAIS desserré une fois posé.",
                   bascule: 2010, gravite: "critique"),
        Divergence(id: "alcool-hypothermie", titre: "Alcool en cas d'hypothermie",
                   sujet: ["hypothermie", "alcool", "gelure"],
                   ancienne: "Donner un alcool fort pour réchauffer.",
                   actuelle: "Jamais d'alcool.",
                   bascule: 1980, gravite: "critique"),
    ]

    func hit(_ texte: String, _ date: Int?) -> Retrieve.Hit {
        Retrieve.Hit(passage: Passage(
            rowid: 0, chunkID: "c", sourceID: "src", sourceTitre: "T", auteur: "",
            date: date, pageDebut: 1, pageFin: 1, section: "", texte: texte,
            qualite: 1, image: nil, priorite: 2, langue: "fr"),
            score: 1, rangLexical: 0, rangVectoriel: 0)
    }

    func testQuestionDeclencheMemeSansExtraitAncien() {
        let d = Divergences.detecter(question: "faut-il desserrer un garrot",
                                     hits: [hit("texte neutre", 2026)], registre: registre)
        XCTAssertEqual(d.map(\.id), ["garrot"])
    }

    func testExtraitRecentNeDeclenchePas() {
        // Condition de fond : une doctrine périmée vient d'une source antérieure.
        let recent = hit("Jamais d'alcool en cas d'hypothermie, la vasodilatation trompe.", 2026)
        XCTAssertTrue(Divergences.detecter(question: "comment me réchauffer",
                                           hits: [recent], registre: registre).isEmpty)
    }

    func testExtraitAncienDeclenche() {
        let vieux = hit("En cas d'hypothermie, donner un alcool fort pour réchauffer.", 1957)
        let ids = Divergences.detecter(question: "comment me réchauffer",
                                       hits: [vieux], registre: registre).map(\.id)
        XCTAssertTrue(ids.contains("alcool-hypothermie"))
    }

    func testMotIsoleNeSuffitPas() {
        // Régression : une mention de passage sortait quatre avertissements et
        // noyait le seul qui comptait.
        let passant = hit("Le garrot est mentionné une fois ici, sans détail.", 1992)
        XCTAssertTrue(Divergences.detecter(question: "comment faire un feu sous la pluie",
                                           hits: [passant], registre: registre).isEmpty)
    }

    func testEcartDeDates() {
        XCTAssertNotNil(Divergences.ecartDeDates([hit("a", 1957), hit("b", 2024)]))
        XCTAssertNil(Divergences.ecartDeDates([hit("a", 2020), hit("b", 2024)]))
        XCTAssertNil(Divergences.ecartDeDates([hit("a", nil)]))
    }

    func testEncartContientLesDeuxDoctrines() {
        let d = Divergences.detecter(question: "desserrer un garrot",
                                     hits: [hit("x", 2026)], registre: registre)
        let txt = Divergences.encart(d)
        XCTAssertTrue(txt.contains("PÉRIMÉ"))
        XCTAssertTrue(txt.contains("ACTUEL"))
        // L'encart est une consigne, pas un document : à ne pas citer.
        XCTAssertTrue(txt.contains("pas à être cité"))
    }

    func testRegistreDecodableSansClefSource() throws {
        // Swift n'applique pas les valeurs par défaut au décodage. L'export
        // garantit la clé ; ce test vérifie qu'elle est bien exigée, pour que
        // l'oubli se voie ici plutôt qu'en supprimant tous les avertissements.
        let json = """
        [{"id":"x","titre":"T","sujet":["a"],"ancienne":"a","actuelle":"b",
          "bascule":2000,"gravite":"critique","source":""}]
        """
        let d = try JSONDecoder().decode([Divergence].self, from: Data(json.utf8))
        XCTAssertEqual(d.count, 1)
        XCTAssertTrue(d[0].critique)
    }

    // MARK: - Mode urgence

    func testRoutageUrgence() {
        let fiches = [
            FicheUrgence(nom: "01-hemorragie", titre: "Hémorragie",
                         declencheurs: ["hémorragie", "saigne", "garrot"],
                         corps: "Comprimer directement sur la plaie."),
            FicheUrgence(nom: "03-arret-cardiaque", titre: "Arrêt cardiaque",
                         declencheurs: ["arrêt cardiaque", "ne respire pas", "massage"],
                         corps: "Masser fort et vite au centre de la poitrine."),
            FicheUrgence(nom: "04-hypothermie", titre: "Hypothermie",
                         declencheurs: ["hypothermie", "froid", "frissons"],
                         corps: "Sortir du vent avant toute chose."),
        ]
        XCTAssertEqual(Urgence.chercher("il saigne beaucoup", dans: fiches).first?.nom,
                       "01-hemorragie")
        XCTAssertEqual(Urgence.chercher("il ne respire pas", dans: fiches).first?.nom,
                       "03-arret-cardiaque")
        XCTAssertEqual(Urgence.chercher("garrot", dans: fiches).first?.nom,
                       "01-hemorragie")
        // Sans accents ni majuscules : la saisie d'urgence n'en a pas.
        XCTAssertEqual(Urgence.chercher("HYPOTHERMIE", dans: fiches).first?.nom,
                       "04-hypothermie")
    }

    func testDeclencheurComposePlusFortQuUnMotIsole() {
        // « ne respire pas » ne se trouve pas par hasard ; « froid » si.
        let fiches = [
            FicheUrgence(nom: "a", titre: "A", declencheurs: ["froid"], corps: "x"),
            FicheUrgence(nom: "b", titre: "B", declencheurs: ["ne respire pas"], corps: "x"),
        ]
        XCTAssertEqual(Urgence.chercher("il fait froid et il ne respire pas",
                                        dans: fiches).first?.nom, "b")
    }
}
