"""Accès à l'index. Aucune E/S réseau, jamais."""

from __future__ import annotations

import base64
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


# Cosinus minimal entre le témoin de l'index et celui que recalcule la requête.
# Deux exécutions de la MÊME implémentation ne diffèrent que par l'arrondi ;
# deux implémentations différentes tombent bien plus bas — 0,78 mesuré entre
# sentence-transformers et MLX sur le même bge-m3.
TEMOIN_MINIMUM = 0.99


def _decoder_temoin(b64: str):
    if not b64:
        return None
    try:
        return np.frombuffer(base64.b64decode(b64), dtype=np.float32)
    except (ValueError, TypeError):
        return None


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
        self.embed_backend = self.meta.get("embed_backend", "")
        self.embed_temoin = _decoder_temoin(self.meta.get("embed_temoin", ""))
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

    def check_embedder(self, name: str, backend: str | None = None) -> None:
        """Refuse un modèle — ou un backend — de requête différent de l'index.

        Ce désaccord ne provoque aucune erreur visible : il renvoie simplement
        des résultats sans rapport, avec la même assurance. C'est le seul
        endroit où on peut l'attraper.

        Le backend compte autant que le nom. « BAAI/bge-m3 » chargé par MLX et
        par sentence-transformers porte le même nom, la même dimension, et peut
        rendre des vecteurs différents — il suffit que l'un prenne le token CLS
        et l'autre la moyenne des tokens. Un index vaut pour un couple
        (modèle, backend), pas pour un nom.
        """
        if name != self.embed_model:
            raise IndexMismatch(
                f"L'index a été construit avec « {self.embed_model} » mais la requête "
                f"utilise « {name} ».\nLes résultats seraient du bruit. "
                f"Reconstruis l'index : SURVIE_EMBEDDER=… make db"
            )
        # Index antérieurs à la consignation du backend : rien à comparer.
        if backend and self.embed_backend and backend != self.embed_backend:
            raise IndexMismatch(
                f"L'index a été construit avec « {self.embed_model} » via le backend "
                f"« {self.embed_backend} », la requête utilise « {backend} ».\n"
                f"Même modèle, mais rien ne garantit le même pooling : les vecteurs "
                f"peuvent être incomparables.\n"
                f"Reconstruis l'index, ou relance avec SURVIE_EMBEDDER={self.embed_backend}."
            )

    def check_temoin(self, vecteur) -> None:
        """Contrôle numérique : la requête retrouve-t-elle le vecteur de l'index ?

        Le nom du modèle et celui du backend sont des déclarations ; ceci est
        une mesure. C'est le seul contrôle qui attrape deux bibliothèques — ou
        deux langages — produisant des vecteurs différents sous le même nom :
        pooling divergent, quantification, conversion de poids. Sans lui, la
        recherche rend du bruit avec le même aplomb que des résultats justes.
        """
        if self.embed_temoin is None or vecteur is None:
            return  # index antérieur au témoin : rien à comparer.
        if len(vecteur) != len(self.embed_temoin):
            raise IndexMismatch(
                f"Témoin de dimension {len(self.embed_temoin)} dans l'index, "
                f"{len(vecteur)} à la requête. Reconstruis l'index."
            )
        v = np.asarray(vecteur, dtype=np.float32)
        v = v / max(float(np.linalg.norm(v)), 1e-9)
        cos = float(v @ self.embed_temoin)
        if cos < TEMOIN_MINIMUM:
            raise IndexMismatch(
                f"Le vecteur témoin ne concorde pas : cosinus {cos:.3f} "
                f"(minimum {TEMOIN_MINIMUM}).\n"
                f"L'index dit « {self.embed_model} » via « {self.embed_backend} », "
                f"et la requête produit d'autres vecteurs pour la même phrase.\n"
                f"Même nom de modèle ne veut pas dire mêmes vecteurs : pooling, "
                f"quantification ou conversion de poids diffèrent.\n"
                f"Reconstruis l'index avec l'implémentation qui interroge."
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
