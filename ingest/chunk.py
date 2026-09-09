"""Découpage du texte en fragments citables.

Deux principes :

1. Les fragments suivent la structure du document (titres, paragraphes) avant
   de suivre une longueur cible. Couper au milieu d'une liste de symptômes ou
   d'une suite d'étapes détruit précisément l'information qu'on cherche.

2. Un fragment peut chevaucher une fin de page. Une technique décrite à cheval
   sur deux pages est fréquente dans les manuels ; l'ignorer produirait deux
   moitiés inutilisables. Le fragment retient sa page de début (celle qui est
   citée) et sa page de fin.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass

from . import config, manifest

# Titres : numérotation (« 3.2 Hypothermie »), majuscules, ou Markdown.
_HEADING = re.compile(
    r"^(?:#{1,6}\s+\S.*"                             # markdown
    r"|\d+(?:\.\d+)*[.)]?\s+[A-ZÀ-Þ].{2,80}"          # « 3.2 Hypothermie »
    r"|[A-ZÀ-Þ][A-ZÀ-Þ0-9 ,'’\-]{6,70}"                # CAPITALES
    r"|[A-ZÀ-Þ][^.!?]{3,60})$"                        # « Signes précoces »
)

# Un titre en casse de titre ne se distingue d'un début de phrase que par
# l'absence de ponctuation finale et sa brièveté. On exige en plus qu'il tienne
# seul dans son paragraphe (vérifié par l'appelant) et qu'il ne se termine pas
# par une virgule ou une conjonction, pour éviter d'avaler une phrase coupée.
_NOT_HEADING_END = re.compile(r"[,;:]$|\b(et|ou|de|du|des|le|la|les|un|une|à|au)$", re.I)


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    page_debut: int
    page_fin: int
    section: str
    texte: str
    tokens: int
    qualite: float
    image: str | None


def estimate_tokens(text: str) -> int:
    """Estimation suffisante pour piloter un découpage.

    Le vrai comptage dépend du tokenizer du modèle, indisponible ici. Le
    français tourne autour de 3,5 caractères par token ; on majore légèrement
    pour ne pas dépasser la fenêtre en aval.
    """
    return max(1, len(text) // 4 + text.count(" ") // 8)


def _blocks(text: str) -> list[tuple[str, bool]]:
    """Découpe une page en (paragraphe, est_un_titre)."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        lines = para.split("\n")
        # Un titre isolé sur sa ligne ouvre une section.
        one_line = len(lines) == 1
        if one_line and _HEADING.match(lines[0]) and len(lines[0]) < 90 \
                and not _NOT_HEADING_END.search(lines[0].strip()):
            out.append((lines[0].lstrip("# ").strip(), True))
        else:
            out.append((" ".join(lines).strip(), False))
    return out


def chunk_document(doc: dict) -> list[Chunk]:
    source_id = doc["source_id"]
    images = {p["numero"]: p.get("image") for p in doc["pages"]}
    chunks: list[Chunk] = []

    # Le tampon porte des (texte, page, qualité). Faire porter la page par chaque
    # bloc plutôt que par une variable globale est ce qui garantit qu'un fragment
    # est toujours cité sur la page dont son premier mot provient — y compris
    # après un recouvrement qui enjambe une fin de page.
    buf: list[tuple[str, int, float]] = []
    buf_tokens = 0
    section = ""
    n = 0

    def flush(keep_overlap: bool = True, force: bool = False) -> bool:
        """Émet le tampon s'il est assez fourni. Renvoie True s'il a émis.

        Quand le tampon est trop court, il est laissé INTACT : l'appelant le
        fusionne avec la suite. Le jeter reviendrait à perdre les sections
        brèves — or « Signes de gravité » ou une checklist de trois lignes
        comptent parmi les passages les plus importants d'un manuel.
        """
        nonlocal buf, buf_tokens, n
        text = "\n\n".join(b[0] for b in buf).strip()
        if text and (force or buf_tokens >= config.CHUNK_MIN_TOKENS):
            n += 1
            pages = [b[1] for b in buf]
            qual = [b[2] for b in buf]
            chunks.append(Chunk(
                chunk_id=f"{source_id}#{n:05d}",
                source_id=source_id,
                page_debut=min(pages),
                page_fin=max(pages),
                section=section,
                texte=text,
                tokens=buf_tokens,
                qualite=round(sum(qual) / len(qual), 3),
                image=images.get(min(pages)),
            ))
            # Recouvrement : le dernier paragraphe repart avec le fragment suivant
            # pour lui donner son contexte immédiat. On ne le fait jamais par-dessus
            # un titre : le contexte d'une autre section serait trompeur.
            budget = config.CHUNK_TARGET_TOKENS * config.CHUNK_OVERLAP_RATIO
            if keep_overlap and len(buf) > 1 and estimate_tokens(buf[-1][0]) <= budget:
                buf = [buf[-1]]
                buf_tokens = estimate_tokens(buf[-1][0])
                return True
            buf, buf_tokens = [], 0
            return True
        return False

    for page in doc["pages"]:
        pno = page["numero"]
        pqual = page.get("qualite", 1.0)
        for block, is_heading in _blocks(page["texte"]):
            if is_heading:
                if flush(keep_overlap=False):
                    # Le tampon est parti : le titre ouvre proprement un fragment.
                    section = block
                else:
                    # Section trop brève pour tenir seule : on la fusionne avec la
                    # suivante et on garde le titre dans le corps du texte, pour
                    # qu'il reste trouvable par la recherche plein texte. Le
                    # fragment reste étiqueté par le PREMIER titre qu'il couvre.
                    if buf:
                        buf.append((block, pno, pqual))
                        buf_tokens += estimate_tokens(block)
                    else:
                        section = block
                continue

            btoks = estimate_tokens(block)

            # Paragraphe plus long que la fenêtre : on le fend par phrases.
            if btoks > config.CHUNK_MAX_TOKENS:
                flush()
                for piece in _split_long(block):
                    buf.append((piece, pno, pqual))
                    buf_tokens += estimate_tokens(piece)
                    if buf_tokens >= config.CHUNK_TARGET_TOKENS:
                        flush()
                continue

            if buf and buf_tokens + btoks > config.CHUNK_MAX_TOKENS:
                flush()
            buf.append((block, pno, pqual))
            buf_tokens += btoks
            if buf_tokens >= config.CHUNK_TARGET_TOKENS:
                flush()

    # En fin de document, on émet le reliquat quelle que soit sa taille : la
    # dernière page d'un manuel n'est pas moins citable que les autres.
    flush(keep_overlap=False, force=True)
    return chunks


def _split_long(text: str) -> list[str]:
    """Fend un paragraphe hors-norme sur les fins de phrase."""
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    out, cur, cur_t = [], [], 0
    for s in sentences:
        t = estimate_tokens(s)
        if cur and cur_t + t > config.CHUNK_TARGET_TOKENS:
            out.append(" ".join(cur))
            cur, cur_t = [], 0
        cur.append(s)
        cur_t += t
    if cur:
        out.append(" ".join(cur))
    return out


def main(argv: list[str] | None = None) -> int:
    config.ensure_dirs()
    files = sorted(config.TEXT_DIR.glob("*.json"))
    if not files:
        print("Aucun texte extrait. Lance d'abord `make ingest`.")
        return 1

    # priorite/langue viennent du manifeste : ils pondèrent le retrieval.
    meta = {s.id: s for s in manifest.load()}

    total = 0
    with config.CHUNKS.open("w", encoding="utf-8") as out:
        for f in files:
            doc = json.loads(f.read_text(encoding="utf-8"))
            chunks = chunk_document(doc)
            src = meta.get(doc["source_id"])
            for c in chunks:
                row = asdict(c)
                if src:
                    row["priorite"] = src.priorite
                    row["langue"] = src.langue
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
            total += len(chunks)
            avg = sum(c.tokens for c in chunks) / len(chunks) if chunks else 0
            print(f"  {doc['source_id']:32} {len(chunks):6} fragments (moy. {avg:.0f} tokens)")

    print(f"\n{total} fragments -> {config.CHUNKS.relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
