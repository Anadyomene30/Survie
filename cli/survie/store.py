"""Accès à l'index. Aucune E/S réseau, jamais."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Passage:
    chunk_id: str
    source_id: str
    source_titre: str
    auteur: str
    date: int | None
    licence: str
    page_debut: int
    page_fin: int
    section: str
    texte: str
    qualite: float
    image: str | None
    priorite: int
    langue: str
    score: float = 0.0

    @property
    def citation(self) -> str:
        """Étiquette telle qu'elle apparaît dans les réponses."""
        return f"[{self.source_id} p.{self.page_debut}]"

    @property
    def reference(self) -> str:
        an = f", {self.date}" if self.date else ""
        return f"{self.source_titre} — {self.auteur}{an}, p. {self.page_debut}"


class IndexMismatch(RuntimeError):
    pass


class Store:
    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(
                f"Index introuvable : {path}\n"
                "Construis-le avec : make fetch && make ingest && make db"
            )
        self.path = path
        self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.con.row_factory = sqlite3.Row
        self.meta = {r["cle"]: r["valeur"] for r in self.con.execute("SELECT * FROM meta")}
        self.embed_model = self.meta.get("embed_model", "?")
        self.embed_dim = int(self.meta.get("embed_dim", "0"))
        self._vectors: np.ndarray | None = None
        self._ids: list[int] | None = None

    # -- vecteurs ----------------------------------------------------------

    def vectors(self) -> tuple[np.ndarray, list[int]]:
        """Charge la matrice des vecteurs, une seule fois.

        Recherche exhaustive assumée : à l'échelle du corpus (quelques dizaines
        de milliers de fragments) un produit matriciel coûte quelques
        millisecondes, pour zéro dépendance supplémentaire et un seul fichier
        à sauvegarder.
        """
        if self._vectors is None:
            rows = self.con.execute(
                "SELECT rowid_, embedding FROM chunks ORDER BY rowid_"
            ).fetchall()
            self._ids = [r["rowid_"] for r in rows]
            self._vectors = np.frombuffer(
                b"".join(r["embedding"] for r in rows), dtype=np.float32
            ).reshape(len(rows), self.embed_dim)
        return self._vectors, self._ids  # type: ignore[return-value]

    def check_embedder(self, name: str) -> None:
        """Refuse un modèle de requête différent de celui de l'index.

        Ce désaccord ne provoque aucune erreur visible : il renvoie simplement
        des résultats sans rapport, avec la même assurance. C'est le seul
        endroit où on peut l'attraper.
        """
        if name != self.embed_model:
            raise IndexMismatch(
                f"L'index a été construit avec « {self.embed_model} » mais la requête "
                f"utilise « {name} ».\nLes résultats seraient du bruit. "
                f"Reconstruis l'index : SURVIE_EMBEDDER=… make db"
            )

    # -- lecture -----------------------------------------------------------

    def passages(self, rowids: list[int]) -> dict[int, Passage]:
        if not rowids:
            return {}
        q = ",".join("?" * len(rowids))
        rows = self.con.execute(
            f"""SELECT c.*, s.titre AS source_titre, s.auteur, s.date, s.licence
                FROM chunks c JOIN sources s ON s.id = c.source_id
                WHERE c.rowid_ IN ({q})""",
            rowids,
        ).fetchall()
        return {
            r["rowid_"]: Passage(
                chunk_id=r["chunk_id"], source_id=r["source_id"],
                source_titre=r["source_titre"], auteur=r["auteur"] or "",
                date=r["date"], licence=r["licence"] or "",
                page_debut=r["page_debut"], page_fin=r["page_fin"],
                section=r["section"] or "", texte=r["texte"],
                qualite=r["qualite"] or 1.0, image=r["image"],
                priorite=r["priorite"] or 2, langue=r["langue"] or "fr",
            )
            for r in rows
        }

    def stats(self) -> dict:
        srcs = self.con.execute(
            "SELECT s.id, s.titre, s.langue, s.licence, COUNT(c.rowid_) n "
            "FROM sources s LEFT JOIN chunks c ON c.source_id = s.id "
            "GROUP BY s.id ORDER BY n DESC"
        ).fetchall()
        return {"meta": self.meta, "sources": [dict(r) for r in srcs]}

    def close(self) -> None:
        self.con.close()
