import Foundation

/// Fournit les vecteurs de requête. Implémenté par MLX côté application ;
/// laissé à `nil` pour un fonctionnement en recherche plein texte seule.
public protocol Embedder: Sendable {
    var nom: String { get }
    func encoder(_ textes: [String], requete: Bool) throws -> [[Float]]
}

/// Génère la réponse. `nil` = mode extraits seuls, le plus sûr de tous
/// puisque rien n'est reformulé.
public protocol Generateur: Sendable {
    var nom: String { get }
    func generer(systeme: String, utilisateur: String) async throws -> String
}

public struct Reponse: Sendable {
    public let question: String
    public let texte: String
    public let hits: [Retrieve.Hit]
    public let rapport: Validate.Rapport?
    public let refus: Bool
    public let identification: Bool
    public let signaux: Retrieve.Signaux?
    public var divergences: [Divergence] = []
    public var ecartDates: (Int, Int)?
}

public actor Engine {
    // Seuil bas et délibérément prudent. Des deux erreurs possibles, le faux
    // refus est la plus grave : il prive d'aide quelqu'un dont la question EST
    // couverte. Un faux accès dégrade proprement — le modèle reçoit des extraits
    // hors sujet et conclut de lui-même qu'il ne peut pas répondre.
    public static let seuilCouverture = 0.20
    public static let seuilCosinus = 0.60

    public let store: Store
    private let embedder: Embedder?
    private let generateur: Generateur?
    private let registre: [Divergence]

    public init(db: URL, embedder: Embedder? = nil, generateur: Generateur? = nil,
                registre: URL? = nil) throws {
        self.store = try Store(url: db)
        self.embedder = embedder
        self.generateur = generateur
        // Par défaut, à côté de l'index : `make db` les écrit ensemble.
        let defaut = db.deletingLastPathComponent().appendingPathComponent("divergences.json")
        self.registre = Divergences.charger(registre ?? defaut)
        // Refuse tôt un index bâti avec un autre modèle : les résultats
        // seraient du bruit, sans le moindre signal d'erreur.
        if let e = embedder { try store.verifierEmbedder(e.nom) }
    }

    public func demander(_ question: String, k: Int = Retrieve.retenus) async throws -> Reponse {
        let qvec = try embedder?.encoder([question], requete: true).first
        let hits = try Retrieve.rechercher(store: store, requete: question, qvec: qvec, k: k)
        let sig = try Retrieve.signaux(store: store, requete: question, qvec: qvec)
        let ident = Prompt.estIdentification(question)

        if hits.isEmpty || doitRefuser(sig) {
            return Reponse(question: question, texte: messageRefus(sig), hits: hits,
                           rapport: nil, refus: true, identification: ident, signaux: sig)
        }

        let divs = Divergences.detecter(question: question, hits: hits, registre: registre)
        let ecart = Divergences.ecartDeDates(hits)
        let encart = Divergences.encart(divs, ecart: ecart)

        let (sys, user) = Prompt.construire(question: question, hits: hits, encart: encart)
        let texte = try await generateur?.generer(systeme: sys, utilisateur: user) ?? ""

        guard !texte.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            // Mode extraits seuls : rien n'est reformulé, donc rien à vérifier.
            return Reponse(question: question, texte: "", hits: hits, rapport: nil,
                           refus: false, identification: ident, signaux: sig,
                           divergences: divs, ecartDates: ecart)
        }
        return Reponse(question: question, texte: texte, hits: hits,
                       rapport: Validate.verifier(reponse: texte, hits: hits),
                       refus: false, identification: ident, signaux: sig,
                       divergences: divs, ecartDates: ecart)
    }

    private func doitRefuser(_ sig: Retrieve.Signaux) -> Bool {
        if sig.couverture >= Self.seuilCouverture { return false }
        // Sans modèle sémantique, le cosinus n'est pas exploitable :
        // la couverture lexicale décide seule.
        guard embedder != nil else { return true }
        return sig.cosMax < Self.seuilCosinus
    }

    private func messageRefus(_ sig: Retrieve.Signaux) -> String {
        guard !sig.termesInconnus.isEmpty else { return Prompt.refus }
        let liste = sig.termesInconnus.prefix(6).map { "« \($0) »" }.joined(separator: ", ")
        return Prompt.refus + "\n\nAucun ouvrage indexé ne contient \(liste). "
             + "Couverture de la question : \(Int(sig.couverture * 100)) %."
    }
}
