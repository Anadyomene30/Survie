"""Construction de build/survie.db — l'unique fichier que lit l'application.

Tout tient dans une seule base : métadonnées des sources, texte des fragments,
index plein texte et vecteurs. C'est un choix délibéré pour un outil de survie :
un seul fichier à copier sur un disque externe, un seul fichier à restaurer.
Les vignettes de pages sont le seul élément externe (build/pages/), parce que
les embarquer ferait passer la base de ~200 Mo à plusieurs gigaoctets.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np

from . import config, manifest

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE meta (
    cle    TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);

CREATE TABLE sources (
    id       TEXT PRIMARY KEY,
    titre    TEXT NOT NULL,
    auteur   TEXT,
    date     INTEGER,
    langue   TEXT,
    licence  TEXT,
    domaine  TEXT,      -- JSON
    priorite INTEGER,
    note     TEXT
);

CREATE TABLE chunks (
    rowid_    INTEGER PRIMARY KEY,   -- position dans la matrice de vecteurs
    chunk_id  TEXT UNIQUE NOT NULL,
    source_id TEXT NOT NULL REFERENCES sources(id),
    page_debut INTEGER NOT NULL,
    page_fin   INTEGER NOT NULL,
    section   TEXT,
    texte     TEXT NOT NULL,
    tokens    INTEGER,
    qualite   REAL,      -- qualité OCR estimée, 0..1
    image     TEXT,      -- vignette relative à build/pages/
    priorite  INTEGER,
    langue    TEXT,
    embedding BLOB       -- float32 brut, dimension = meta.embed_dim
);

CREATE INDEX idx_chunks_source ON chunks(source_id);

-- Index plein texte. remove_diacritics 2 est indispensable en français :
-- sans lui, « hypothermie » ne trouve pas « hypothermié », et surtout une
-- requête tapée sans accents (fréquent dans l'urgence) ne trouve rien.
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    texte,
    section,
    content='chunks',
    content_rowid='rowid_',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, texte, section) VALUES (new.rowid_, new.texte, new.section);
END;
"""


def build() -> int:
    if not config.CHUNKS.exists() or not config.VECTORS.exists():
        print("Fragments ou vecteurs absents. Lance `make ingest` puis `make db`.")
        return 1

    rows = [json.loads(l) for l in config.CHUNKS.read_text(encoding="utf-8").splitlines() if l]
    vecs = np.load(config.VECTORS)
    emb_meta = json.loads((config.BUILD / "embedder.json").read_text(encoding="utf-8"))

    if len(rows) != vecs.shape[0]:
        print(f"Incohérence : {len(rows)} fragments mais {vecs.shape[0]} vecteurs.")
        print("Relance `make db` après `make ingest` — les deux doivent être régénérés ensemble.")
        return 1

    config.DB.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        config.DB.with_name(config.DB.name + suffix).unlink(missing_ok=True)

    con = sqlite3.connect(config.DB)
    con.executescript(SCHEMA)

    sources = {s.id: s for s in manifest.load()}
    used = {r["source_id"] for r in rows}
    con.executemany(
        "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
        [(s.id, s.titre, s.auteur, s.date, s.langue, s.licence,
          json.dumps(s.domaine, ensure_ascii=False), s.priorite, s.note)
         for sid, s in sources.items() if sid in used],
    )

    con.executemany(
        "INSERT INTO chunks (rowid_, chunk_id, source_id, page_debut, page_fin, section,"
        " texte, tokens, qualite, image, priorite, langue, embedding)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(i, r["chunk_id"], r["source_id"], r["page_debut"], r["page_fin"],
          r.get("section", ""), r["texte"], r.get("tokens"), r.get("qualite", 1.0),
          r.get("image"), r.get("priorite", 2), r.get("langue", "fr"),
          vecs[i].tobytes())
         for i, r in enumerate(rows)],
    )

    con.executemany("INSERT INTO meta VALUES (?,?)", [
        ("schema_version", "1"),
        # Ces deux clés sont vérifiées au démarrage du runtime. Interroger un
        # index avec un autre modèle que celui qui l'a construit ne produit pas
        # d'erreur visible, seulement du bruit : la vérification est donc la
        # seule protection possible.
        ("embed_model", emb_meta["name"]),
        ("embed_backend", emb_meta.get("backend", "")),
        ("embed_temoin", _temoin_encode(emb_meta.get("temoin"))),
        ("embed_dim", str(emb_meta["dim"])),
        ("chunk_count", str(len(rows))),
        ("source_count", str(len(used))),
        ("built_at", datetime.now(timezone.utc).isoformat(timespec="seconds")),
    ])

    con.commit()
    con.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('optimize')")
    con.commit()
    con.execute("VACUUM")
    con.close()

    # Le registre des doctrines périmées est exporté en JSON à côté de l'index :
    # l'application Swift le lit sans embarquer d'analyseur YAML, et il reste
    # éditable en YAML côté dépôt, qui supporte bien mieux les textes longs.
    _exporter_divergences()

    size = config.DB.stat().st_size / 1e6
    print(f"Index construit : {config.DB.relative_to(config.ROOT)} ({size:.1f} Mo)")
    print(f"  {len(rows)} fragments, {len(used)} sources, modèle « {emb_meta['name']} »")

    if emb_meta["name"].startswith("hashing-"):
        print("\n  ATTENTION : index construit avec le backend de TEST.")
        print("  La recherche sera purement lexicale et de mauvaise qualité.")
        print("  Pour un index utilisable : SURVIE_EMBEDDER=mlx make db")
    return 0


def _exporter_divergences() -> None:
    src = config.CORPUS / "divergences.yaml"
    if not src.exists():
        return
    import yaml

    data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    entrees = data.get("divergences", [])
    # Les blocs YAML repliés portent des retours à la ligne qui n'ont aucun sens
    # une fois affichés dans une interface : on les aplatit ici, à l'export.
    for e in entrees:
        for cle in ("ancienne", "actuelle", "source", "titre"):
            if cle in e and isinstance(e[cle], str):
                e[cle] = " ".join(e[cle].split())
        # Swift n'applique pas les valeurs par défaut d'une propriété au
        # décodage : une clé absente ferait échouer tout le registre, donc
        # supprimerait silencieusement les avertissements. On la force ici.
        e.setdefault("source", "")
    (config.BUILD / "divergences.json").write_text(
        json.dumps(entrees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  {len(entrees)} doctrines périmées -> build/divergences.json")


def _temoin_encode(vecteur) -> str:
    """Vecteur témoin -> base64 de float32, pour la table meta (texte).

    Écrit ici pour être relu par TOUTE implémentation qui interroge l'index :
    c'est le seul contrôle qui attrape deux bibliothèques rendant des vecteurs
    différents sous le même nom de modèle. Voir ingest.embed.PHRASE_TEMOIN.
    """
    if not vecteur:
        return ""
    return base64.b64encode(
        np.asarray(vecteur, dtype=np.float32).tobytes()).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    return build()


if __name__ == "__main__":
    sys.exit(main())
