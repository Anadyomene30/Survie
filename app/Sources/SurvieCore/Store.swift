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

    public var errorDescription: String? {
        switch self {
        case .introuvable(let url):
            return "Index introuvable : \(url.path)\n" +
                   "Construis-le avec : make fetch && make ingest && make db"
        case .sqlite(let msg):
            return "Erreur SQLite : \(msg)"
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
    public let embedDim: Int
    public let chunkCount: Int

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
        self.embedDim = Int(m["embed_dim"] ?? "0") ?? 0
        self.chunkCount = Int(m["chunk_count"] ?? "0") ?? 0
    }

    deinit { if let db { sqlite3_close(db) } }

    /// Refuse un modèle de requête différent de celui qui a bâti l'index.
    ///
    /// Ce désaccord ne provoque aucune erreur visible : il renvoie simplement
    /// des résultats sans rapport, avec la même assurance. C'est le seul
    /// endroit où on peut l'attraper.
    public func verifierEmbedder(_ nom: String) throws {
        guard nom == embedModel else {
            throw StoreError.modeleIncompatible(index: embedModel, requete: nom)
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
