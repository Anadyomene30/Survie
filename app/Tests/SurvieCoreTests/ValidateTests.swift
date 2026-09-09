import XCTest
@testable import SurvieCore

/// Parité avec tests/test_validate.py. Ces cas doivent passer à l'identique
/// des deux côtés — c'est ce qui garantit que l'application se comporte comme
/// l'implémentation de référence évaluée sur eval/golden.yaml.
final class ValidateTests: XCTestCase {

    func hit(_ sourceID: String, _ debut: Int, _ fin: Int) -> Retrieve.Hit {
        Retrieve.Hit(passage: Passage(
            rowid: 0, chunkID: "\(sourceID)#1", sourceID: sourceID,
            sourceTitre: "Pack Bouriane", auteur: "", date: 2026,
            pageDebut: debut, pageFin: fin, section: "Eau", texte: "…",
            qualite: 1.0, image: nil, priorite: 1, langue: "fr"),
            score: 1.0, rangLexical: 0, rangVectoriel: 0)
    }

    lazy var hits = [hit("bouriane", 2, 3), hit("fm-21-76", 40, 40)]

    func testCitationValide() {
        let r = Validate.verifier(reponse:
            "Sortir du vent avant tout, c'est la première chose à faire en cas "
            + "d'hypothermie. [bouriane p.2]", hits: hits)
        XCTAssertTrue(r.ok, "\(r.problemes)")
        XCTAssertEqual(r.citations, 1)
        XCTAssertEqual(r.valides, 1)
    }

    func testSourceInventeeDetectee() {
        let r = Validate.verifier(reponse:
            "Il faut administrer 500 mg d'amoxicilline toutes les huit heures "
            + "sans attendre. [merck-manual p.221]", hits: hits)
        XCTAssertFalse(r.ok)
        XCTAssertTrue(r.problemes.contains { $0.genre == .sourceInconnue })
    }

    func testPageHorsExtraitDetectee() {
        let r = Validate.verifier(reponse:
            "La dose recommandée est de deux comprimés par jour pendant cinq "
            + "jours au minimum. [bouriane p.99]", hits: hits)
        XCTAssertTrue(r.problemes.contains { $0.genre == .pageHorsExtrait })
    }

    func testPlageDePagesAcceptee() {
        for page in [2, 3] {
            let r = Validate.verifier(reponse:
                "Cette affirmation porte sur un point technique précis et "
                + "détaillé. [bouriane p.\(page)]", hits: hits)
            XCTAssertTrue(r.ok, "page \(page) refusée à tort")
        }
    }

    func testFormuleDePrudenceExemptee() {
        let r = Validate.verifier(reponse:
            "Le colchique n'a aucune odeur alors que l'ail des ours sent "
            + "puissamment l'ail au froissement. [bouriane p.3] "
            + "Dans le doute, s'abstenir.", hits: hits)
        XCTAssertTrue(r.ok, "\(r.problemes)")
    }

    func testIdentificationDetectee() {
        for q in ["ce champignon est-il comestible",
                  "c'est bien de l'ail des ours ?",
                  "baies noires en grappe, est-ce du sureau",
                  "châtaigne ou marron",
                  "je peux le manger ?"] {
            XCTAssertTrue(Prompt.estIdentification(q), "non détecté : \(q)")
        }
        for q in ["comment traiter une hypothermie", "où trouver de l'eau"] {
            XCTAssertFalse(Prompt.estIdentification(q), "faux positif : \(q)")
        }
    }

    func testTermeFTSTronque() {
        // « frissonne » doit trouver « frissons » : le préfixe seul ne suffit pas.
        XCTAssertEqual(Retrieve.termeFTS("frissonne"), "\"frisso\"*")
        XCTAssertEqual(Retrieve.termeFTS("eau"), "\"eau\"")
        XCTAssertEqual(Retrieve.termeFTS("orage"), "\"orage\"*")
    }

    func testMotsVidesRetires() {
        XCTAssertEqual(Retrieve.termes("comment faire pour traiter une eau de source"),
                       ["traiter", "eau", "source"])
        // Une requête entièrement composée de mots vides ne doit pas être vide.
        XCTAssertFalse(Retrieve.termes("que faire").isEmpty)
    }
}
