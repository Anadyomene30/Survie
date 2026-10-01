"""Vectorisation des fragments.

Le backend est enfichable, pour une raison précise : l'index et les requêtes
DOIVENT être produits par le même modèle. Un index construit avec bge-m3 puis
interrogé avec e5 ne renvoie pas de mauvaises réponses, il renvoie du bruit —
sans rien signaler. Le nom du modèle est donc écrit dans la base, et le runtime
refuse de démarrer en cas de désaccord (voir build_db.py et cli/survie/store.py).
"""

from __future__ import annotations

import hashlib
import json
import sys

import numpy as np

from . import config


# Phrase témoin. Son vecteur est écrit dans l'index, et toute implémentation
# qui interroge cet index doit le retrouver.
#
# Pourquoi un contrôle numérique et pas seulement un nom. Mesuré le 11 septembre
# 2026 : « BAAI/bge-m3 » chargé par sentence-transformers et le même modèle
# converti pour MLX rendent, sur cette phrase, des vecteurs à cosinus 0,78. Le
# nom concorde, la dimension concorde, et pourtant les vecteurs ne sont pas
# comparables. Aucun contrôle textuel ne peut attraper cela ; celui-ci, si.
#
# Le texte doit rester identique à `Store.phraseTemoin` côté Swift, au
# caractère près.
PHRASE_TEMOIN = "hypothermie : sortir du vent, isoler du sol, réchauffer le tronc"


class Embedder:
    """Interface commune. `name` et `backend` sont écrits dans la base et
    vérifiés au runtime.

    Le nom du modèle ne suffit pas à identifier un index. Deux bibliothèques
    peuvent charger « BAAI/bge-m3 » et en tirer des vecteurs différents — il
    suffit que l'une prenne le token CLS et l'autre la moyenne des tokens. Les
    dimensions concordent, le nom concorde, la vérification passe, et la
    recherche rend du bruit. Le backend est donc consigné avec le nom.
    """

    name: str
    backend: str
    dim: int

    def encode(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        raise NotImplementedError


class HashingEmbedder(Embedder):
    """Backend déterministe sans modèle — tests et intégration continue.

    Projette des n-grammes de caractères dans un espace de dimension fixe. La
    similarité obtenue est purement lexicale : suffisante pour vérifier que la
    plomberie fonctionne de bout en bout, inutilisable en production. Le nom
    porte le préfixe « hashing- » pour qu'un index de test ne puisse jamais
    être confondu avec un index réel.
    """

    backend = "hashing"

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def encode(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            low = _fold(text)
            for n in (3, 4, 5):
                for j in range(len(low) - n + 1):
                    gram = low[j:j + n]
                    h = int.from_bytes(hashlib.blake2b(gram.encode(), digest_size=8).digest(), "big")
                    out[i, h % self.dim] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.maximum(norms, 1e-9)


class SentenceTransformerEmbedder(Embedder):
    """Repli portable (CPU/CUDA/MPS). Plus lent que MLX sur Apple Silicon."""

    backend = "st"

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.name = model_name
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        prefix = config.EMBED_QUERY_PREFIX if is_query else config.EMBED_DOC_PREFIX
        if prefix:
            texts = [prefix + t for t in texts]
        vecs = self.model.encode(texts, batch_size=config.EMBED_BATCH,
                                 normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)


class MLXEmbedder(Embedder):
    """Backend de production sur Apple Silicon."""

    backend = "mlx"

    def __init__(self, model_name: str):
        from mlx_embeddings.utils import load  # type: ignore

        self.model, self.tokenizer = load(model_name)
        self.name = model_name
        self.dim = int(self.model.config.hidden_size)

    def encode(self, texts: list[str], *, is_query: bool = False) -> np.ndarray:
        import mlx.core as mx

        prefix = config.EMBED_QUERY_PREFIX if is_query else config.EMBED_DOC_PREFIX
        if prefix:
            texts = [prefix + t for t in texts]
        out = []
        for i in range(0, len(texts), config.EMBED_BATCH):
            batch = texts[i:i + config.EMBED_BATCH]
            enc = self.tokenizer.batch_encode_plus(
                batch, return_tensors="mlx", padding=True, truncation=True, max_length=8192
            )
            res = self.model(enc["input_ids"], attention_mask=enc["attention_mask"])
            # mx.eval() force l'évaluation paresseuse et ne REND rien : passer
            # son résultat à np.asarray donnait un tableau de dimension zéro,
            # et la vectorisation échouait au premier lot.
            vecteurs = res.text_embeds
            mx.eval(vecteurs)
            out.append(np.asarray(vecteurs, dtype=np.float32))
        vecs = np.concatenate(out, axis=0)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.maximum(norms, 1e-9)


def _fold(text: str) -> str:
    """Minuscules sans accents — le repli lexical ne doit pas buter sur « à »."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def modele_par_defaut(backend: str) -> str:
    """Le dépôt à charger dépend du backend, et ce n'est pas un détail.

    `BAAI/bge-m3` ne publie que `pytorch_model.bin` : mlx-embeddings n'y trouve
    aucun safetensors et refuse de charger. La conversion MLX du même modèle
    (`mlx-community/bge-m3-mlx-fp16`) en fournit. Un utilisateur qui force
    SURVIE_EMBED_MODEL garde la main ; sans quoi on prend celui qui marche.
    """
    if config.EMBED_MODEL_EXPLICITE:
        return config.EMBED_MODEL
    return "mlx-community/bge-m3-mlx-fp16" if backend == "mlx" else config.EMBED_MODEL


def get_embedder(backend: str | None = None) -> Embedder:
    backend = backend or config.EMBED_BACKEND
    if backend == "auto":
        backend = "mlx" if sys.platform == "darwin" else "st"

    if backend == "hashing":
        return HashingEmbedder(config.EMBED_DIM)
    if backend == "mlx":
        try:
            return MLXEmbedder(modele_par_defaut("mlx"))
        except Exception as e:
            print(f"  ! MLX indisponible ({e}); repli sur sentence-transformers")
            backend = "st"
    if backend == "st":
        return SentenceTransformerEmbedder(modele_par_defaut("st"))
    raise ValueError(f"backend d'embeddings inconnu : {backend}")


def main(argv: list[str] | None = None) -> int:
    config.ensure_dirs()
    if not config.CHUNKS.exists():
        print("Aucun fragment. Lance d'abord `make ingest`.")
        return 1

    rows = [json.loads(line) for line in config.CHUNKS.read_text(encoding="utf-8").splitlines() if line]
    emb = get_embedder()
    print(f"Vectorisation de {len(rows)} fragments avec « {emb.name} » (dim {emb.dim})…")

    # Le titre de section est préfixé au texte : « Hypothermie » n'apparaît
    # souvent que dans le titre, jamais dans le corps du paragraphe qui la traite.
    texts = [f"{r['section']}\n{r['texte']}".strip() if r.get("section") else r["texte"]
             for r in rows]

    vecs = np.zeros((len(texts), emb.dim), dtype=np.float32)
    step = max(1, len(texts) // 20)
    for i in range(0, len(texts), config.EMBED_BATCH):
        batch = texts[i:i + config.EMBED_BATCH]
        vecs[i:i + len(batch)] = emb.encode(batch)
        if i % step < config.EMBED_BATCH:
            print(f"  {100 * i // max(1, len(texts)):3d}%", end="\r", flush=True)

    np.save(config.VECTORS, vecs)
    temoin = emb.encode([PHRASE_TEMOIN])[0]
    temoin = temoin / max(float(np.linalg.norm(temoin)), 1e-9)
    (config.BUILD / "embedder.json").write_text(
        json.dumps({"name": emb.name, "backend": emb.backend, "dim": emb.dim,
                    "count": len(rows), "temoin": [round(float(x), 6) for x in temoin]},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n{vecs.shape[0]} vecteurs de dimension {vecs.shape[1]} -> "
          f"{config.VECTORS.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
