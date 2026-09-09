import Accelerate
import Foundation

/// Recherche hybride : plein texte + vectoriel, fusionnés par RRF.
///
/// Cette implémentation doit rester en parité stricte avec `cli/survie/retrieve.py`.
/// Le jeu `eval/golden.yaml` tourne contre les deux et doit donner les mêmes
/// résultats — c'est ce qui autorise à mettre au point la recherche en Python,
/// où l'itération est rapide, puis à la porter ici.
public enum Retrieve {

    /// Constante usuelle de la fusion réciproque de rangs. Elle amortit l'écart
    /// entre les premiers rangs, ce qui évite qu'une seule méthode n'impose son
    /// premier résultat contre l'avis de l'autre.
    public static let rrfK = 60.0
    public static let candidats = 50
    public static let retenus = 8

    /// Sièges garantis : les N premiers de CHAQUE méthode entrent dans le
    /// résultat final, même si la fusion les classe mal.
    ///
    /// La fusion RRF récompense l'accord entre méthodes, et sacrifie
    /// l'excellence dans une seule : un passage premier en plein texte mais
    /// absent du classement vectoriel ne reçoit qu'une contribution, et se fait
    /// battre par des passages médiocres dans les deux, qui en cumulent deux.
    ///
    /// Mesuré côté Python : la section contenant « ébullition » sortait rang 2
    /// en BM25 et n'apparaissait pas dans les huit extraits transmis. En survie
    /// un terme exact est souvent décisif — « ébullition », « 114 » — et le
    /// perdre au profit d'un consensus tiède n'est pas acceptable.
    public static let siegesGarantis = 2

    /// Mots vides français et interrogatifs : ils font remonter n'importe quoi en BM25.
    static let motsVides: Set<String> = [
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "a", "à",
        "au", "aux", "en", "dans", "sur", "pour", "par", "avec", "sans", "que", "qui",
        "quoi", "dont", "est", "sont", "ce", "cette", "ces", "il", "elle", "on", "je",
        "tu", "nous", "vous", "ils", "se", "sa", "son", "ses", "mon", "ma", "mes",
        "comment", "pourquoi", "quand", "où", "combien", "quel", "quelle", "quels",
        "quelles", "faire", "fait", "faut", "peut", "puis", "dois", "doit", "y",
        "n", "l", "s", "j", "c", "qu", "si", "plus", "moins", "être", "avoir",
    ]

    public struct Hit: Sendable {
        public let passage: Passage
        public let score: Double
        public let rangLexical: Int?
        public let rangVectoriel: Int?

        public var methodes: String {
            var m: [String] = []
            if let r = rangLexical { m.append("texte#\(r + 1)") }
            if let r = rangVectoriel { m.append("vect#\(r + 1)") }
            return m.joined(separator: "+")
        }
    }

    /// Indices de couverture, pour décider d'un refus.
    ///
    /// Le score RRF ne peut PAS servir à cela : calculé sur des rangs, il vaut
    /// à peu près la même chose pour une question hors sujet et pour une
    /// question bien couverte, puisqu'un passage arrive toujours premier.
    public struct Signaux: Sendable {
        public let termes: [String]
        public let termesConnus: [String]
        public let termesInconnus: [String]
        public let cosMax: Double
        let poids: [String: Double]

        /// Part du poids informationnel de la question couverte par le corpus.
        /// Pondérer par la rareté évite qu'un mot passe-partout ne donne
        /// l'illusion d'une couverture.
        public var couverture: Double {
            guard !termes.isEmpty else { return 0 }
            let total = termes.reduce(0.0) { $0 + (poids[$1] ?? 1) }
            let connu = termesConnus.reduce(0.0) { $0 + (poids[$1] ?? 1) }
            return total > 0 ? connu / total : 0
        }
    }

    // MARK: - Termes

    /// Minuscules sans accents : une requête tapée sans accents doit trouver.
    public static func plier(_ s: String) -> String {
        s.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "fr"))
    }

    public static func termes(_ requete: String) -> [String] {
        let bruts = requete.lowercased()
            .components(separatedBy: CharacterSet(charactersIn:
                "abcdefghijklmnopqrstuvwxyzàâäçéèêëîïôöùûü0123456789").inverted)
            .filter { $0.count >= 2 }
        let gardes = bruts.filter { !motsVides.contains(plier($0)) }
        // Une requête faite uniquement de mots vides (« que faire ? ») ne doit
        // pas produire une recherche vide.
        return gardes.isEmpty ? bruts : gardes
    }

    /// Un terme échappé, tronqué et suffixé pour absorber la morphologie.
    ///
    /// FTS5 ne racinise pas : sans cela « frissonne » ne trouve pas « frissons ».
    /// Le préfixe seul ne va que dans un sens ; on tronque donc au-delà de six
    /// caractères, la variation portant en français surtout sur la terminaison.
    public static func termeFTS(_ t: String) -> String {
        let esc = t.replacingOccurrences(of: "\"", with: "\"\"")
        if esc.count < 5 { return "\"\(esc)\"" }
        if esc.count > 6 { return "\"\(String(esc.prefix(6)))\"*" }
        return "\"\(esc)\"*"
    }

    public static func requeteFTS(_ requete: String) -> String {
        termes(requete).map(termeFTS).joined(separator: " OR ")
    }

    // MARK: - Recherche

    public static func signaux(store: Store, requete: String,
                               qvec: [Float]?) throws -> Signaux {
        let toks = termes(requete)
        let n = Double(max(1, store.chunkCount))
        var connus: [String] = [], inconnus: [String] = [], poids: [String: Double] = [:]
        for t in toks {
            let df = try store.frequence(termeFTS(t))
            poids[t] = log(1 + n / Double(1 + df))
            if df > 0 { connus.append(t) } else { inconnus.append(t) }
        }
        var cos = 0.0
        if let qvec { cos = Double(try similarites(store: store, qvec: qvec).max() ?? 0) }
        return Signaux(termes: toks, termesConnus: connus, termesInconnus: inconnus,
                       cosMax: cos, poids: poids)
    }

    static func similarites(store: Store, qvec: [Float]) throws -> [Float] {
        let (flat, ids) = try store.matrice()
        guard !ids.isEmpty, store.embedDim > 0 else { return [] }
        var out = [Float](repeating: 0, count: ids.count)
        // Produit matrice-vecteur : les vecteurs sont déjà normalisés à
        // l'indexation, le produit scalaire est donc le cosinus.
        cblas_sgemv(CblasRowMajor, CblasNoTrans,
                    Int32(ids.count), Int32(store.embedDim), 1.0,
                    flat, Int32(store.embedDim), qvec, 1, 0.0, &out, 1)
        return out
    }

    static func rechercheVectorielle(store: Store, qvec: [Float],
                                     limite: Int) throws -> [Int] {
        let (_, ids) = try store.matrice()
        let sims = try similarites(store: store, qvec: qvec)
        guard !sims.isEmpty else { return [] }
        return zip(ids, sims)
            .sorted { $0.1 > $1.1 }
            .prefix(limite)
            .map(\.0)
    }

    /// Pondération éditoriale, volontairement faible : elle départage des
    /// passages de pertinence comparable, elle ne doit jamais faire remonter
    /// un passage hors sujet.
    static func ponderation(_ p: Passage) -> Double {
        var b = 1.0
        switch p.priorite {
        case 1: b *= 1.12
        case 3: b *= 0.88
        default: break
        }
        if p.langue == "fr" { b *= 1.05 }
        if p.qualite < 0.6 { b *= 0.85 }
        return b
    }

    public static func rechercher(store: Store, requete: String, qvec: [Float]?,
                                  k: Int = retenus) throws -> [Hit] {
        let lex = try store.rechercheLexicale(requeteFTS(requete), limite: candidats)
        let vec = try qvec.map { try rechercheVectorielle(store: store, qvec: $0,
                                                          limite: candidats) } ?? []

        var scores: [Int: Double] = [:]
        var rangs: [Int: (Int?, Int?)] = [:]
        for (i, rid) in lex.enumerated() {
            scores[rid, default: 0] += 1.0 / (rrfK + Double(i) + 1)
            rangs[rid] = (i, rangs[rid]?.1)
        }
        for (i, rid) in vec.enumerated() {
            scores[rid, default: 0] += 1.0 / (rrfK + Double(i) + 1)
            rangs[rid] = (rangs[rid]?.0, i)
        }

        let passages = try store.passages(rowids: Array(scores.keys))
        let classe = passages.compactMap { rid, p -> (Int, Hit)? in
            guard let s = scores[rid] else { return nil }
            return (rid, Hit(passage: p, score: s * ponderation(p),
                             rangLexical: rangs[rid]?.0, rangVectoriel: rangs[rid]?.1))
        }
        .sorted { $0.1.score > $1.1.score }

        let garantis = Set(lex.prefix(siegesGarantis) + vec.prefix(siegesGarantis))
        return avecSieges(classe, garantis: garantis, k: k)
    }

    /// Complète le classement fusionné avec les têtes de chaque méthode.
    ///
    /// Les garantis conservent leur score de fusion : ils obtiennent une place
    /// assurée, pas la première. Le classement reste celui du RRF.
    static func avecSieges(_ classe: [(Int, Hit)], garantis: Set<Int>,
                           k: Int) -> [Hit] {
        let retenus = Array(classe.prefix(k))
        let presents = Set(retenus.map(\.0))
        let manquants = classe.filter { garantis.contains($0.0) && !presents.contains($0.0) }
        guard !manquants.isEmpty else { return retenus.map(\.1) }
        // On évince les derniers du classement fusionné, jamais les premiers.
        let garde = Array(retenus.prefix(max(0, k - manquants.count)))
        return (garde + manquants)
            .sorted { $0.1.score > $1.1.score }
            .prefix(k)
            .map(\.1)
    }
}
