import Foundation
import SQLite3

/// Un passage citable, tel qu'il sera présenté à l'utilisateur.
public struct Passage: Sendable, Identifiable {
    public let rowid: Int
    public let chunkID: String
    public let sourceID: String
    public let sourceTitre: String
    public let auteur: String
    public let date: Int?
    public let pageDebut: Int
    public let pageFin: Int
    public let section: String
    public let texte: String
    public let qualite: Double
    public let image: String?
    public let priorite: Int
    public let langue: String

    public var id: String { chunkID }

    /// Étiquette telle qu'elle apparaît dans les réponses : `[source p.42]`.
    public var citation: String { "[\(sourceID) p.\(pageDebut)]" }

    public var reference: String {
        let an = date.map { ", \($0)" } ?? ""
        return "\(sourceTitre) — \(auteur)\(an), p. \(pageDebut)"
    }
}

public enum StoreError: LocalizedError {
    case introuvable(URL)
    case sqlite(String)
    /// L'index a été construit avec un autre modèle d'embeddings.
    case modeleIncompatible(index: String, requete: String)
    /// Même nom de modèle, mais les vecteurs ne concordent pas.
    case temoinDivergent(cosinus: Float)

    public var errorDescription: String? {
        switch self {
        case .introuvable(let url):
            return "Index introuvable : \(url.path)\n" +
                   "Construis-le avec : make fetch && make ingest && make db"
        case .sqlite(let msg):
            return "Erreur SQLite : \(msg)"
        case .temoinDivergent(let cos):
            return """
                Le vecteur témoin ne concorde pas : cosinus \(String(format: "%.3f", cos))                 (minimum \(Store.temoinMinimum)). L'index et cette application ne                 produisent pas les mêmes vecteurs pour la même phrase — pooling,                 quantification ou conversion de poids diffèrent. Reconstruis l'index                 avec l'implémentation qui l'interroge.
                """
        case .modeleIncompatible(let index, let requete):
            return """
                L'index a été construit avec « \(index) » mais la requête utilise \
                « \(requete) ». Les résultats seraient du bruit, sans erreur visible. \
                Reconstruis l'index.
                """
        }
    }
}

/// Accès en lecture seule à survie.db. N'ouvre jamais de connexion réseau.
public final class Store {
    private var db: OpaquePointer?
    public let meta: [String: String]
    public let embedModel: String
    /// Bibliothèque qui a produit les vecteurs de l'index (« mlx », « st »…).
    /// Vide pour un index bâti avant que le backend ne soit consigné.
    public let embedBackend: String
    public let embedDim: Int
    public let chunkCount: Int
    /// Vecteur de `Store.phraseTemoin` tel que l'a produit l'implémentation qui
    /// a bâti l'index. `nil` pour un index antérieur au témoin.
    public let embedTemoin: [Float]?

    /// Matrice des vecteurs, chargée paresseusement puis conservée.
    /// Recherche exhaustive assumée : à l'échelle du corpus (quelques dizaines
    /// de milliers de fragments) le produit matriciel coûte quelques
    /// millisecondes via Accelerate, pour zéro dépendance et un seul fichier.
    private var vectors: [Float]?
    private var vectorRowIDs: [Int]?

    public init(url: URL) throws {
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw StoreError.introuvable(url)
        }
        var handle: OpaquePointer?
        guard sqlite3_open_v2(url.path, &handle, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
            throw StoreError.sqlite(String(cString: sqlite3_errmsg(handle)))
        }
        self.db = handle

        var m: [String: String] = [:]
        try Store.query(handle, "SELECT cle, valeur FROM meta") { stmt in
            m[Store.text(stmt, 0)] = Store.text(stmt, 1)
        }
        self.meta = m
        self.embedModel = m["embed_model"] ?? "?"
        self.embedBackend = m["embed_backend"] ?? ""
        self.embedDim = Int(m["embed_dim"] ?? "0") ?? 0
        self.chunkCount = Int(m["chunk_count"] ?? "0") ?? 0
        self.embedTemoin = Store.decoderTemoin(m["embed_temoin"])
    }

    /// Phrase témoin. Doit rester identique à `ingest.embed.PHRASE_TEMOIN`,
    /// au caractère près — c'est la moitié du contrôle.
    public static let phraseTemoin =
        "hypothermie : sortir du vent, isoler du sol, réchauffer le tronc"

    /// Cosinus minimal entre le témoin de l'index et celui de la requête. Deux
    /// exécutions de la même implémentation ne diffèrent que par l'arrondi ;
    /// deux implémentations différentes tombent bien plus bas — 0,78 mesuré
    /// entre sentence-transformers et MLX sur le même bge-m3.
    public static let temoinMinimum: Float = 0.99

    private static func decoderTemoin(_ b64: String?) -> [Float]? {
        guard let b64, !b64.isEmpty,
              let data = Data(base64Encoded: b64), data.count % 4 == 0
        else { return nil }
        return data.withUnsafeBytes { Array($0.bindMemory(to: Float.self)) }
    }

    /// Contrôle numérique : la requête retrouve-t-elle le vecteur de l'index ?
    ///
    /// Le nom du modèle et celui du backend sont des déclarations ; ceci est
    /// une mesure. C'est le seul contrôle qui attrape deux bibliothèques — ou
    /// deux langages — produisant des vecteurs différents sous le même nom :
    /// pooling divergent, quantification, conversion de poids. Parité avec
    /// `Store.check_temoin` côté Python.
    public func verifierTemoin(_ vecteur: [Float]) throws {
        guard let attendu = embedTemoin else { return }
        guard vecteur.count == attendu.count else {
            throw StoreError.temoinDivergent(cosinus: 0)
        }
        var produit: Float = 0, norme: Float = 0
        for (a, b) in zip(vecteur, attendu) { produit += a * b; norme += a * a }
        let cos = norme > 1e-9 ? produit / sqrt(norme) : 0
        guard cos >= Store.temoinMinimum else {
            throw StoreError.temoinDivergent(cosinus: cos)
        }
    }

    deinit { if let db { sqlite3_close(db) } }

    /// Refuse un modèle — ou un backend — de requête différent de l'index.
    ///
    /// Ce désaccord ne provoque aucune erreur visible : il renvoie simplement
    /// des résultats sans rapport, avec la même assurance. C'est le seul
    /// endroit où on peut l'attraper.
    ///
    /// Le backend compte autant que le nom : « BAAI/bge-m3 » chargé par MLX et
    /// par sentence-transformers porte le même nom et la même dimension, et
    /// peut rendre d'autres vecteurs — il suffit que l'un prenne le token CLS
    /// et l'autre la moyenne des tokens. Un index vaut pour un couple
    /// (modèle, backend). Parité avec `Store.check_embedder` côté Python.
    public func verifierEmbedder(_ nom: String, backend: String = "") throws {
        guard nom == embedModel else {
            throw StoreError.modeleIncompatible(index: embedModel, requete: nom)
        }
        // Index antérieur à la consignation du backend : rien à comparer.
        guard embedBackend.isEmpty || backend.isEmpty || backend == embedBackend else {
            throw StoreError.modeleIncompatible(index: "\(embedModel) via \(embedBackend)",
                                                requete: "\(nom) via \(backend)")
        }
    }

    // MARK: - Vecteurs

    public func matrice() throws -> (valeurs: [Float], rowids: [Int]) {
        if let vectors, let vectorRowIDs { return (vectors, vectorRowIDs) }
        var flat: [Float] = []
        var ids: [Int] = []
        flat.reserveCapacity(chunkCount * embedDim)
        try Store.query(db, "SELECT rowid_, embedding FROM chunks ORDER BY rowid_") { stmt in
            ids.append(Int(sqlite3_column_int64(stmt, 0)))
            if let blob = sqlite3_column_blob(stmt, 1) {
                let n = Int(sqlite3_column_bytes(stmt, 1)) / MemoryLayout<Float>.size
                flat.append(contentsOf: UnsafeBufferPointer(
                    start: blob.assumingMemoryBound(to: Float.self), count: n))
            }
        }
        vectors = flat
        vectorRowIDs = ids
        return (flat, ids)
    }

    // MARK: - Lecture

    public func passages(rowids: [Int]) throws -> [Int: Passage] {
        guard !rowids.isEmpty else { return [:] }
        let placeholders = rowids.map { String($0) }.joined(separator: ",")
        var out: [Int: Passage] = [:]
        try Store.query(db, """
            SELECT c.rowid_, c.chunk_id, c.source_id, s.titre, s.auteur, s.date,
                   c.page_debut, c.page_fin, c.section, c.texte, c.qualite,
                   c.image, c.priorite, c.langue
            FROM chunks c JOIN sources s ON s.id = c.source_id
            WHERE c.rowid_ IN (\(placeholders))
            """) { stmt in
            let rowid = Int(sqlite3_column_int64(stmt, 0))
            out[rowid] = Passage(
                rowid: rowid,
                chunkID: Store.text(stmt, 1),
                sourceID: Store.text(stmt, 2),
                sourceTitre: Store.text(stmt, 3),
                auteur: Store.text(stmt, 4),
                date: sqlite3_column_type(stmt, 5) == SQLITE_NULL
                    ? nil : Int(sqlite3_column_int64(stmt, 5)),
                pageDebut: Int(sqlite3_column_int64(stmt, 6)),
                pageFin: Int(sqlite3_column_int64(stmt, 7)),
                section: Store.text(stmt, 8),
                texte: Store.text(stmt, 9),
                qualite: sqlite3_column_double(stmt, 10),
                image: sqlite3_column_type(stmt, 11) == SQLITE_NULL
                    ? nil : Store.text(stmt, 11),
                priorite: Int(sqlite3_column_int64(stmt, 12)),
                langue: Store.text(stmt, 13))
        }
        return out
    }

    /// Recherche plein texte, ordonnée par BM25.
    public func rechercheLexicale(_ requete: String, limite: Int) throws -> [Int] {
        var ids: [Int] = []
        try Store.query(db, """
            SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ?
            ORDER BY bm25(chunks_fts, 1.0, 2.0) LIMIT \(limite)
            """, bind: [requete]) { stmt in
            ids.append(Int(sqlite3_column_int64(stmt, 0)))
        }
        return ids
    }

    /// Nombre de fragments contenant un terme — sert à pondérer sa rareté.
    public func frequence(_ terme: String) throws -> Int {
        var n = 0
        try Store.query(db, "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH ?",
                        bind: [terme]) { stmt in
            n = Int(sqlite3_column_int64(stmt, 0))
        }
        return n
    }

    // MARK: - Utilitaires SQLite

    private static func text(_ stmt: OpaquePointer?, _ col: Int32) -> String {
        guard let c = sqlite3_column_text(stmt, col) else { return "" }
        return String(cString: c)
    }

    private static func query(_ db: OpaquePointer?, _ sql: String,
                              bind: [String] = [],
                              row: (OpaquePointer?) -> Void) throws {
        var stmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else {
            throw StoreError.sqlite(String(cString: sqlite3_errmsg(db)))
        }
        defer { sqlite3_finalize(stmt) }
        let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        for (i, value) in bind.enumerated() {
            sqlite3_bind_text(stmt, Int32(i + 1), value, -1, transient)
        }
        while sqlite3_step(stmt) == SQLITE_ROW { row(stmt) }
    }
}
