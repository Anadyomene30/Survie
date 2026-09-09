"""Ingestion sélective des archives Kiwix (ZIM).

Wikipédia FR complet représente environ 2,5 millions d'articles. L'ingérer tel
quel serait contre-productif, pour deux raisons — et la latence n'en fait pas
partie, contrairement à ce qu'on suppose spontanément.

La première, décisive : le bruit noierait les ouvrages de référence. Un article
encyclopédique généraliste remonterait devant un manuel de médecine de terrain,
et le déclassement en priorité 3 n'y suffirait pas face à deux ordres de
grandeur d'écart en volume.

La seconde : la matrice de vecteurs occuperait environ 2 Go de mémoire vive, en
concurrence directe avec les 13 Go du modèle sur une machine de 32 Go.

Mesuré, à 1024 dimensions : 40 000 fragments coûtent 164 Mo et 3,3 ms par
requête ; 115 000 fragments (ouvrages plus 25 000 articles) 471 Mo et 9,7 ms ;
500 000 fragments 2 Go et 47,7 ms. La recherche exhaustive tient donc largement
à l'échelle visée.

La sélection par semences thématiques n'est donc pas une optimisation, c'est une
condition de fonctionnement. Les articles retenus sont en outre forcés en
priorité 3, ce qui les déclasse derrière tout ouvrage de référence : ils servent
de repli quand rien d'autre ne couvre la question.

Deux stratégies de sélection, dans cet ordre :

1. L'index plein texte de l'archive, quand elle en possède un. On interroge le
   ZIM avec chaque semence et on récolte les résultats. C'est rapide et ciblé.
2. Le balayage des titres, sinon. Plus lent, mais sans dépendance à l'index.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import config

SEEDS = config.CORPUS / "zim-seeds.yaml"

# Nombre de résultats demandés par semence lors de la recherche plein texte.
# Assez large pour couvrir un sujet, assez étroit pour ne pas ramener la moitié
# de l'encyclopédie sur un terme courant.
RESULTATS_PAR_SEMENCE = 120


@dataclass
class Reglages:
    max_articles: int = 25000
    min_caracteres: int = 400
    max_caracteres: int = 60000
    namespaces: tuple[str, ...] = ("C", "A")
    exclusions: tuple[str, ...] = ()
    semences: tuple[tuple[str, int], ...] = ()   # (terme, poids)


def charger_reglages(path: Path | None = None) -> Reglages:
    path = path or SEEDS
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    semences: list[tuple[str, int]] = []
    for groupe in data.get("groupes", {}).values():
        poids = int(groupe.get("poids", 1))
        for terme in groupe.get("termes", []):
            semences.append((terme, poids))
    return Reglages(
        max_articles=int(data.get("max_articles", 25000)),
        min_caracteres=int(data.get("min_caracteres", 400)),
        max_caracteres=int(data.get("max_caracteres", 60000)),
        namespaces=tuple(data.get("namespaces", ["C", "A"])),
        exclusions=tuple(data.get("exclusions", [])),
        semences=tuple(semences),
    )


# --- Conversion HTML -> texte ---------------------------------------------

_BALISE = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"[ \t]+")
_LIGNES = re.compile(r"\n{3,}")
# Ces blocs doivent partir AVEC leur contenu. Retirer seulement les balises
# laisserait « alert(1) » ou des règles CSS dans le texte indexé : le corpus se
# retrouverait pollué par du code, qui remonterait ensuite dans des extraits.
_BLOCS_CODE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.S | re.I)


def html_vers_texte(html: str) -> str:
    """Extrait le texte d'un article.

    On passe par BeautifulSoup si disponible — il gère proprement les entités,
    les scripts et les tableaux. Le repli par expression régulière permet au
    module de fonctionner sans dépendance supplémentaire, au prix d'un texte
    un peu plus sale.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "table"]):
            tag.decompose()
        # Les boîtes de navigation et d'homonymie de Wikipédia n'apportent rien.
        for cls in ("navbox", "homonymie", "bandeau", "metadata", "reference"):
            for tag in soup.select(f".{cls}"):
                tag.decompose()
        texte = soup.get_text("\n")
    except ImportError:
        texte = _BLOCS_CODE.sub(" ", html)
        texte = _BALISE.sub(" ", texte)
        # Entités les plus courantes ; le repli ne prétend pas être exhaustif.
        for entite, car in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                            ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
            texte = texte.replace(entite, car)

    texte = _ESPACES.sub(" ", texte)
    return _LIGNES.sub("\n\n", texte).strip()


# --- Sélection -------------------------------------------------------------

def _exclu(titre: str, reglages: Reglages) -> bool:
    return any(x.lower() in titre.lower() for x in reglages.exclusions)


def _chemins_par_recherche(archive, reglages: Reglages) -> dict[str, int]:
    """Chemins d'articles trouvés via l'index plein texte du ZIM.

    Renvoie {chemin: poids}. Un article trouvé par plusieurs semences, ou par
    une semence de poids élevé, sera préféré si le plafond est atteint.
    """
    from libzim.search import Query, Searcher

    searcher = Searcher(archive)
    trouves: dict[str, int] = {}
    for terme, poids in reglages.semences:
        try:
            recherche = searcher.search(Query().set_query(terme))
            total = min(recherche.getEstimatedMatches(), RESULTATS_PAR_SEMENCE)
            for chemin in recherche.getResults(0, total):
                trouves[chemin] = trouves.get(chemin, 0) + poids
        except Exception:
            # Une semence qui échoue ne doit pas interrompre la récolte.
            continue
    return trouves


def _chemins_par_balayage(archive, reglages: Reglages) -> dict[str, int]:
    """Repli : on balaye les titres. Lent, mais sans index requis."""
    termes = [(t.lower(), p) for t, p in reglages.semences]
    trouves: dict[str, int] = {}
    for i in range(archive.all_entry_count):
        try:
            entree = archive._get_entry_by_id(i)
        except Exception:
            continue
        if entree.is_redirect:
            continue
        titre = entree.title
        if not titre or _exclu(titre, reglages):
            continue
        bas = titre.lower()
        poids = sum(p for t, p in termes if t in bas or bas in t)
        if poids:
            trouves[entree.path] = poids
    return trouves


def selectionner(archive, reglages: Reglages) -> list[str]:
    """Chemins d'articles à ingérer, les mieux notés d'abord."""
    if archive.has_fulltext_index:
        trouves = _chemins_par_recherche(archive, reglages)
    else:
        print("  (pas d'index plein texte dans l'archive : balayage des titres)")
        trouves = _chemins_par_balayage(archive, reglages)

    classes = sorted(trouves.items(), key=lambda kv: (-kv[1], kv[0]))
    return [chemin for chemin, _ in classes[: reglages.max_articles]]


# --- Extraction ------------------------------------------------------------

def extraire(chemin_zim: Path, reglages: Reglages | None = None) -> list[dict]:
    """Articles retenus, au format « page » du pipeline.

    Chaque article devient une page numérotée. Le numéro n'a pas de sens
    physique — c'est un identifiant de citation stable, et l'interface affiche
    le titre de l'article plutôt que « p. 42 » pour ces sources.
    """
    from libzim.reader import Archive

    reglages = reglages or charger_reglages()
    archive = Archive(str(chemin_zim))
    chemins = selectionner(archive, reglages)

    pages: list[dict] = []
    ignores_courts = 0
    for chemin in chemins:
        try:
            entree = archive.get_entry_by_path(chemin)
            if entree.is_redirect:
                continue
            item = entree.get_item()
            if not str(item.mimetype).startswith("text/html"):
                continue
            texte = html_vers_texte(bytes(item.content).decode("utf-8", "replace"))
        except Exception:
            continue

        if len(texte) < reglages.min_caracteres:
            ignores_courts += 1
            continue
        if len(texte) > reglages.max_caracteres:
            texte = texte[: reglages.max_caracteres]

        pages.append({
            "numero": len(pages) + 1,
            "texte": f"{entree.title}\n\n{texte}",
            "ocr": False,
            "qualite": 1.0,
            "image": None,
            "titre_article": entree.title,
        })

    if ignores_courts:
        print(f"  {ignores_courts} article(s) trop court(s) écarté(s)")
    if len(pages) >= reglages.max_articles:
        print(f"  ! plafond de {reglages.max_articles} articles atteint.")
        print("    Resserre les semences dans corpus/zim-seeds.yaml plutôt que")
        print("    de relever le plafond : au-delà, le bruit noie les ouvrages")
        print("    de référence, ce qui est exactement ce qu'on veut éviter.")
    return pages


def main(argv: list[str] | None = None) -> int:
    if len(sys.argv) < 2:
        print("usage : python -m ingest.zim <archive.zim>")
        return 2
    pages = extraire(Path(sys.argv[1]))
    print(f"{len(pages)} articles retenus")
    for p in pages[:5]:
        print(f"  {p['titre_article']}  ({len(p['texte'])} caractères)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
