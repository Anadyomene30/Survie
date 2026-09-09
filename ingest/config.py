"""Chemins et paramètres partagés par tout le pipeline."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CORPUS = ROOT / "corpus"
MANIFEST = CORPUS / "manifest.yaml"
PUBLIC = CORPUS / "public"
PRIVATE = CORPUS / "private"
LOCKFILE = CORPUS / "sources.lock"

BUILD = ROOT / "build"
PAGES_DIR = BUILD / "pages"          # vignettes PNG, une par page indexée
TEXT_DIR = BUILD / "text"            # texte extrait, une entrée JSON par source
CHUNKS = BUILD / "chunks.jsonl"
VECTORS = BUILD / "vectors.npy"
DB = BUILD / "survie.db"

# --- Découpage ------------------------------------------------------------
# Fenêtres volontairement courtes : en survie, une réponse doit pointer vers
# un geste précis, pas vers un chapitre entier.
CHUNK_TARGET_TOKENS = 550
CHUNK_MAX_TOKENS = 800
CHUNK_MIN_TOKENS = 60
CHUNK_OVERLAP_RATIO = 0.15

# --- Embeddings -----------------------------------------------------------
# Le backend est choisi par SURVIE_EMBEDDER :
#   mlx     -> Apple Silicon, production (défaut sur macOS arm64)
#   st      -> sentence-transformers, repli portable
#   hashing -> déterministe, sans modèle : tests et CI uniquement
EMBED_BACKEND = os.environ.get("SURVIE_EMBEDDER", "auto")
EMBED_MODEL = os.environ.get("SURVIE_EMBED_MODEL", "BAAI/bge-m3")
EMBED_DIM = int(os.environ.get("SURVIE_EMBED_DIM", "1024"))
EMBED_BATCH = 16

# Préfixes d'instruction. bge-m3 n'en utilise pas ; e5 en exige.
EMBED_QUERY_PREFIX = os.environ.get("SURVIE_QUERY_PREFIX", "")
EMBED_DOC_PREFIX = os.environ.get("SURVIE_DOC_PREFIX", "")

# --- Vignettes de pages ---------------------------------------------------
PAGE_IMAGE_DPI = 150
PAGE_IMAGES = os.environ.get("SURVIE_PAGE_IMAGES", "1") not in ("0", "false", "")

# --- OCR ------------------------------------------------------------------
# Sous ce nombre de caractères par page, la page est considérée comme scannée.
OCR_TEXT_THRESHOLD = 120
OCR_LANGS = "fra+eng"
OCR_ENABLED = os.environ.get("SURVIE_OCR", "1") not in ("0", "false", "")


def ensure_dirs() -> None:
    for d in (PUBLIC, PRIVATE, BUILD, PAGES_DIR, TEXT_DIR):
        d.mkdir(parents=True, exist_ok=True)
