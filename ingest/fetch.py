"""Téléchargement des sources libres de droit.

Ne télécharge JAMAIS un ouvrage sous droits : ceux-là sont déposés à la main
dans corpus/private/. Chaque fichier obtenu est empreinté (SHA256) dans
corpus/sources.lock, ce qui rend le corpus reproductible et permet de détecter
qu'une URL sert désormais un contenu différent.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import config, manifest
from .manifest import Source

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) SURVIE/0.1 (corpus hors-ligne)"
TIMEOUT = 120


@dataclass
class Result:
    source: Source
    ok: bool
    detail: str
    sha256: str = ""
    size: int = 0

    @property
    def symbol(self) -> str:
        return "[green]OK[/green]" if self.ok else "[red]ÉCHEC[/red]"


def _opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    op.addheaders = [("User-Agent", UA), ("Accept", "*/*")]
    return op


def check(src: Source) -> Result:
    """Vérifie qu'une URL répond, sans rien écrire sur disque."""
    if not src.url:
        return Result(src, False, "pas d'URL")
    try:
        resp = _opener().open(urllib.request.Request(src.url), timeout=TIMEOUT)
        ctype = (resp.headers.get("Content-Type") or "?").split(";")[0]
        clen = resp.headers.get("Content-Length") or "?"
        head = resp.read(2048)
        resp.close()
        # Une page d'erreur HTML servie en 200 à la place d'un PDF est un piège
        # classique (paywall, redirection de consentement). On le détecte ici
        # plutôt qu'au moment de l'extraction, trois étapes plus loin.
        expects_pdf = src.url.lower().split("?")[0].endswith(".pdf")
        if expects_pdf and not head.startswith(b"%PDF"):
            return Result(src, False, f"attendu PDF, reçu {ctype} (le lien a peut-être changé)")
        return Result(src, True, f"{resp.status} {ctype} {clen} octets")
    except urllib.error.HTTPError as e:
        return Result(src, False, f"HTTP {e.code}")
    except Exception as e:  # réseau, DNS, TLS, proxy
        return Result(src, False, f"{type(e).__name__}: {e}")


def download(src: Source) -> Result:
    dest = src.local_path()
    if dest is None:
        return Result(src, False, "pas de destination")
    if dest.exists() and dest.stat().st_size > 0:
        digest, size = _digest(dest)
        return Result(src, True, "déjà présent", digest, size)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with _opener().open(urllib.request.Request(src.url), timeout=TIMEOUT) as resp:
            h = hashlib.sha256()
            size = 0
            with tmp.open("wb") as fh:
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
                    h.update(chunk)
                    size += len(chunk)
        if size == 0:
            tmp.unlink(missing_ok=True)
            return Result(src, False, "fichier vide")
        tmp.replace(dest)
        return Result(src, True, f"{size / 1e6:.1f} Mo", h.hexdigest(), size)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return Result(src, False, f"{type(e).__name__}: {e}")


def _digest(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def write_lock(results: list[Result]) -> None:
    lock = {
        r.source.id: {
            "titre": r.source.titre,
            "licence": r.source.licence,
            "url": r.source.url,
            "sha256": r.sha256,
            "taille": r.size,
        }
        for r in results
        if r.ok and r.sha256
    }
    config.LOCKFILE.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def report_private(sources: list[Source]) -> tuple[int, int]:
    """Affiche l'état des ouvrages sous droits attendus dans corpus/private/."""
    private = [s for s in sources if s.licence == "copyright"]
    present = [s for s in private if (p := s.local_path()) and p.exists()]
    missing = [s for s in private if s not in present]

    print(f"\n── Ouvrages sous droits ({len(present)}/{len(private)} présents) ──")
    for s in missing:
        star = "★ " if s.priorite == 1 else "  "
        print(f"  {star}manquant : {s.titre} — {s.auteur}")
        print(f"      déposer dans : {s.fichier_attendu}")
    if missing:
        print("\n  Ces ouvrages ne sont jamais téléchargés automatiquement.")
        print("  Procure-les légalement et dépose-les aux chemins ci-dessus,")
        print("  puis relance `make ingest`. Le pipeline est incrémental.")
    return len(present), len(private)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Récupère les sources libres du corpus SURVIE")
    ap.add_argument("--check-only", action="store_true",
                    help="vérifie les URLs sans rien télécharger")
    ap.add_argument("--only", nargs="*", metavar="ID", help="restreindre à ces identifiants")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args(argv)

    config.ensure_dirs()
    sources = manifest.load()
    free = [s for s in sources if s.is_free and s.url]
    if args.only:
        free = [s for s in free if s.id in set(args.only)]

    action = check if args.check_only else download
    verb = "Vérification" if args.check_only else "Téléchargement"
    print(f"{verb} de {len(free)} sources libres de droit…\n")

    results: list[Result] = []
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        for r in ex.map(action, free):
            flag = "OK  " if r.ok else "ÉCHEC"
            print(f"{flag} {r.source.id:32} {r.detail}")
            results.append(r)

    failed = [r for r in results if not r.ok]
    if not args.check_only:
        write_lock(results)
        print(f"\nEmpreintes écrites dans {config.LOCKFILE.relative_to(config.ROOT)}")

    report_private(sources)

    if failed:
        print(f"\n── {len(failed)} source(s) libre(s) inaccessible(s) ──")
        for r in failed:
            print(f"  {r.source.id}: {r.detail}")
            print(f"    {r.source.url}")
        print("\n  Les URLs de documents publics bougent (réorganisations de sites,")
        print("  retraits d'archive.org). Corrige l'URL dans corpus/manifest.yaml,")
        print("  ou dépose le fichier à la main dans corpus/public/<id>.pdf.")
        print("  Le corpus reste exploitable sans elles : le pipeline ignore")
        print("  les sources absentes plutôt que d'échouer.")

    return 1 if failed and args.check_only else 0


if __name__ == "__main__":
    sys.exit(main())
