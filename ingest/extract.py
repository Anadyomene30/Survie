"""Extraction du texte page par page, avec OCR de secours et vignettes.

La granularité « page » est structurante pour tout le projet : c'est l'unité
de citation. Une réponse renvoie vers `[source p.42]`, et l'application affiche
l'image de cette page — ce qui permet de lire le schéma d'origine (nœud,
attelle, planche botanique) et pas seulement sa transcription approximative.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config, manifest
from .manifest import Source


@dataclass
class Page:
    numero: int          # 1-indexé, tel qu'affiché à l'utilisateur
    texte: str
    ocr: bool = False
    qualite: float = 1.0  # 0..1, proportion de mots plausibles (voir _quality)
    image: str | None = None  # chemin relatif de la vignette


@dataclass
class Document:
    source_id: str
    titre: str
    pages: list[Page]

    def to_json(self) -> str:
        return json.dumps(
            {"source_id": self.source_id, "titre": self.titre,
             "pages": [asdict(p) for p in self.pages]},
            ensure_ascii=False,
        )


# --- Contrôle qualité -----------------------------------------------------

_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]{2,}")


def _quality(text: str) -> float:
    """Heuristique de qualité OCR : proportion de « mots » plausibles.

    L'OCR d'un scan raté produit des suites de caractères isolés et de
    ponctuation. Un texte propre a une forte densité de mots alphabétiques de
    longueur raisonnable. Ce n'est pas un correcteur orthographique, juste un
    détecteur de bouillie — suffisant pour signaler les pages à revoir.
    """
    if not text.strip():
        return 0.0
    tokens = text.split()
    if not tokens:
        return 0.0
    words = [t for t in tokens if _WORD.fullmatch(t.strip(".,;:()[]«»\"'"))]
    return round(len(words) / len(tokens), 3)


def _clean(text: str) -> str:
    """Normalisation minimale : césures de fin de ligne, espaces, lignes vides."""
    text = text.replace("­", "")                      # trait d'union conditionnel
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)           # mot coupé en fin de ligne
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --- Extracteurs par format ----------------------------------------------

def _extract_pdf(src: Source, path: Path) -> list[Page]:
    try:
        import fitz  # pymupdf
    except ImportError:
        print(f"  ! pymupdf absent — {src.id} ignoré (pip install 'survie[extract]')")
        return []

    doc = fitz.open(path)
    pages: list[Page] = []
    img_dir = config.PAGES_DIR / src.id
    if config.PAGE_IMAGES:
        img_dir.mkdir(parents=True, exist_ok=True)

    for i, page in enumerate(doc, start=1):
        text = _clean(page.get_text("text"))
        used_ocr = False

        if len(text) < config.OCR_TEXT_THRESHOLD and config.OCR_ENABLED:
            ocr_text = _ocr_page(page)
            if len(ocr_text) > len(text):
                text, used_ocr = _clean(ocr_text), True

        image_rel = None
        if config.PAGE_IMAGES and text:
            image_rel = f"{src.id}/{i:05d}.png"
            out = config.PAGES_DIR / image_rel
            if not out.exists():
                zoom = config.PAGE_IMAGE_DPI / 72
                page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(out)

        if text:
            pages.append(Page(i, text, used_ocr, _quality(text), image_rel))

    doc.close()
    return pages


def _ocr_page(page) -> str:
    """OCR d'une page via Tesseract. Renvoie "" si l'outil est absent."""
    if not shutil.which("tesseract"):
        return ""
    import fitz

    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
    try:
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", config.OCR_LANGS, "--psm", "1"],
            input=pix.tobytes("png"), capture_output=True, timeout=120,
        )
        return proc.stdout.decode("utf-8", "replace")
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _extract_epub(src: Source, path: Path) -> list[Page]:
    """EPUB : pas de pagination physique, on numérote les chapitres.

    Les numéros renvoyés sont donc des « pages logiques ». C'est explicite dans
    l'interface, qui affiche « ch. 4 » plutôt que « p. 4 » pour ces sources.
    """
    try:
        from bs4 import BeautifulSoup
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError:
        print(f"  ! ebooklib/bs4 absents — {src.id} ignoré")
        return []

    book = epub.read_epub(str(path))
    pages = []
    for i, item in enumerate(book.get_items_of_type(ITEM_DOCUMENT), start=1):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for tag in soup(["script", "style", "nav"]):
            tag.decompose()
        text = _clean(soup.get_text("\n"))
        if len(text) > 200:
            pages.append(Page(i, text, False, _quality(text), None))
    return pages


def _extract_markdown_dir(src: Source, path: Path) -> list[Page]:
    """Pack régional : un fichier .md = une « page » citable.

    Le nom du fichier sert d'ancre de citation lisible ([bouriane p.3] est
    opaque ; l'interface résout le numéro vers le titre de la fiche).
    """
    pages = []
    for i, md in enumerate(sorted(path.glob("*.md")), start=1):
        text = _clean(md.read_text(encoding="utf-8"))
        if text:
            pages.append(Page(i, text, False, 1.0, None))
    return pages


def extract(src: Source) -> Document | None:
    path = src.local_path()
    if path is None or not path.exists():
        return None

    if src.is_local_dir:
        pages = _extract_markdown_dir(src, path)
    elif path.suffix.lower() == ".pdf":
        pages = _extract_pdf(src, path)
    elif path.suffix.lower() == ".epub":
        pages = _extract_epub(src, path)
    elif path.suffix.lower() in (".txt", ".md"):
        text = _clean(path.read_text(encoding="utf-8", errors="replace"))
        pages = [Page(1, text, False, _quality(text), None)] if text else []
    else:
        print(f"  ! format non géré pour {src.id} ({path.suffix})")
        return None

    return Document(src.id, src.titre, pages) if pages else None


def main(argv: list[str] | None = None) -> int:
    config.ensure_dirs()
    sources = manifest.load()
    present = manifest.available(sources)

    if not present:
        print("Aucune source sur disque. Lance d'abord `make fetch`,")
        print("et dépose tes ouvrages sous droits dans corpus/private/.")
        return 1

    print(f"Extraction de {len(present)} source(s)…\n")
    suspect: list[tuple[str, int, float]] = []

    for src in present:
        doc = extract(src)
        if doc is None:
            print(f"  --   {src.id}: rien d'extractible")
            continue

        out = config.TEXT_DIR / f"{src.id}.json"
        out.write_text(doc.to_json(), encoding="utf-8")

        ocr_pages = sum(1 for p in doc.pages if p.ocr)
        low = [p for p in doc.pages if p.qualite < 0.55]
        flag = "  " if not low else "!!"
        print(f"{flag} {src.id:32} {len(doc.pages):5} pages"
              f"  ocr={ocr_pages:<5} qualité<0.55: {len(low)}")
        if low:
            suspect.append((src.id, len(low), sum(p.qualite for p in low) / len(low)))

    if suspect:
        print("\n── Pages de qualité douteuse ──")
        print("  L'OCR est le plafond de qualité du système. Les guides")
        print("  botaniques scannés sont les plus fragiles (noms latins, tableaux).")
        for sid, n, avg in suspect:
            print(f"  {sid}: {n} pages, qualité moyenne {avg:.2f}")
        print("\n  Si une source est massivement touchée, cherche une meilleure")
        print("  numérisation (EPUB ou PDF texte natif) plutôt que de l'indexer telle quelle.")

    print(f"\nTexte extrait dans {config.TEXT_DIR.relative_to(config.ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
