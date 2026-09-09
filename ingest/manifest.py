"""Chargement et validation du catalogue de sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config

# Licences dont le pipeline peut télécharger le contenu lui-même.
FREE_LICENCES = {
    "public-domain",
    "libre-diffusion",
    "libre-acces",
    "licence-ouverte",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
}


@dataclass
class Source:
    id: str
    titre: str
    auteur: str = ""
    date: int | None = None
    langue: str = "fr"
    licence: str = "copyright"
    domaine: list[str] = field(default_factory=list)
    priorite: int = 2
    url: str | None = None
    chemin: str | None = None
    fichier_attendu: str | None = None
    format: str | None = None
    note: str = ""

    @property
    def is_free(self) -> bool:
        return self.licence in FREE_LICENCES

    @property
    def is_local_dir(self) -> bool:
        """Source rédigée dans le dépôt (pack régional)."""
        return self.format == "markdown-dir"

    @property
    def is_zim(self) -> bool:
        """Archive Kiwix, ingérée sélectivement (voir ingest/zim.py)."""
        return self.format == "zim"

    def local_path(self) -> Path | None:
        """Emplacement du fichier sur disque, une fois récupéré."""
        if self.chemin:
            return config.ROOT / self.chemin
        if self.fichier_attendu:
            return config.ROOT / self.fichier_attendu
        if self.is_zim:
            return None
        if self.url:
            suffix = Path(self.url.split("?")[0]).suffix.lower()
            if suffix not in (".pdf", ".epub", ".txt", ".md", ".html", ".zip"):
                suffix = ".pdf"
            return config.PUBLIC / f"{self.id}{suffix}"
        return None


class ManifestError(ValueError):
    pass


def load(path: Path | None = None) -> list[Source]:
    path = path or config.MANIFEST
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "sources" not in raw:
        raise ManifestError(f"{path} : clé 'sources' absente")

    known = set(Source.__dataclass_fields__)
    sources: list[Source] = []
    seen: set[str] = set()

    for entry in raw["sources"]:
        unknown = set(entry) - known
        if unknown:
            raise ManifestError(f"{entry.get('id', '?')} : champs inconnus {sorted(unknown)}")
        src = Source(**entry)
        if src.id in seen:
            raise ManifestError(f"identifiant dupliqué : {src.id}")
        seen.add(src.id)

        # Une source libre sans moyen de l'obtenir est une erreur de saisie.
        if src.format == "zim" and not src.chemin:
            raise ManifestError(f"{src.id} : format zim mais 'chemin' absent")
        if src.is_free and not (src.url or src.chemin):
            raise ManifestError(f"{src.id} : licence libre mais ni 'url' ni 'chemin'")
        if src.licence == "copyright" and not src.fichier_attendu:
            raise ManifestError(f"{src.id} : sous droits mais 'fichier_attendu' absent")
        if not 1 <= src.priorite <= 3:
            raise ManifestError(f"{src.id} : priorite doit valoir 1, 2 ou 3")

        sources.append(src)

    return sources


def available(sources: list[Source]) -> list[Source]:
    """Sources réellement présentes sur disque, prêtes à être extraites."""
    out = []
    for s in sources:
        p = s.local_path()
        if p and p.exists():
            out.append(s)
    return out
