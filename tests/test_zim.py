"""Tests de l'ingestion sélective des archives ZIM.

Une archive miniature est fabriquée à la volée avec l'écrivain de libzim, ce
qui permet de vérifier la chaîne complète sans télécharger dix gigaoctets de
Wikipédia.

L'enjeu testé est la SÉLECTIVITÉ. Ingérer une encyclopédie entière noierait les
ouvrages de référence sous le bruit encyclopédique — un article généraliste
remonterait devant un manuel de médecine de terrain. Ces tests vérifient donc
autant ce qui est écarté que ce qui est retenu.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

libzim = pytest.importorskip("libzim", reason="libzim absent")

from ingest.zim import (  # noqa: E402
    Reglages, charger_reglages, extraire, html_vers_texte,
)

ARTICLES = {
    "Hypothermie": "<h1>Hypothermie</h1><p>" + (
        "L'hypothermie est un abaissement de la température centrale du corps "
        "en dessous de 35 degrés. Elle survient bien au-dessus de zéro degré, "
        "sur des vêtements humides et avec du vent. " * 6) + "</p>",
    "Amanite phalloïde": "<h1>Amanite phalloïde</h1><p>" + (
        "Champignon mortel responsable de la majorité des décès par ingestion "
        "de champignons en Europe. Volve en sac à la base du pied. " * 8) + "</p>",
    "Bouriane": "<h1>Bouriane</h1><p>" + (
        "Région naturelle du nord-ouest du département du Lot, aux sols "
        "siliceux couverts de châtaigniers, en bordure du Périgord noir. " * 8)
        + "</p>",
    "Bataille de Marignan": "<h1>Bataille de Marignan</h1><p>" + (
        "Affrontement militaire de septembre 1515 opposant le royaume de France "
        "aux mercenaires suisses dans le duché de Milan. " * 8) + "</p>",
    "Liste des communes du Lot": "<h1>Liste</h1><p>" + (
        "Énumération administrative des communes du département. " * 10) + "</p>",
    "Ébauche": "<h1>Ébauche</h1><p>Trop court.</p>",
}


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    from libzim.writer import Creator, Hint, Item, StringProvider

    class Article(Item):
        def __init__(self, titre, html):
            super().__init__()
            self.titre, self.html = titre, html

        def get_path(self):
            return self.titre.replace(" ", "_")

        def get_title(self):
            return self.titre

        def get_mimetype(self):
            return "text/html"

        def get_contentprovider(self):
            return StringProvider(self.html)

        def get_hints(self):
            return {Hint.FRONT_ARTICLE: True}

    chemin = tmp_path_factory.mktemp("zim") / "test.zim"
    with Creator(chemin).config_indexing(True, "fra") as creator:
        creator.set_mainpath("Hypothermie")
        for titre, html in ARTICLES.items():
            creator.add_item(Article(titre, html))
        for cle, valeur in (("Title", "Test"), ("Language", "fra"),
                            ("Creator", "SURVIE"), ("Publisher", "SURVIE"),
                            ("Date", "2026-01-01"), ("Description", "corpus de test"),
                            ("Name", "survie-test"), ("Scraper", "tests")):
            creator.add_metadata(cle, valeur)
    return chemin


@pytest.fixture(scope="module")
def reglages():
    r = charger_reglages()
    # Le fichier de semences réel, mais un plafond réduit pour le test.
    return Reglages(max_articles=50, min_caracteres=r.min_caracteres,
                    max_caracteres=r.max_caracteres, namespaces=r.namespaces,
                    exclusions=r.exclusions, semences=r.semences)


def test_semences_reelles_chargees():
    r = charger_reglages()
    assert len(r.semences) > 80, "le fichier de semences semble incomplet"
    termes = {t for t, _ in r.semences}
    assert "hypothermie" in termes
    assert "amanite phalloïde" in termes
    assert "Bouriane" in termes
    # Le milieu local doit peser plus que le reste : c'est le terrain réel.
    assert dict(r.semences)["Bouriane"] > dict(r.semences)["forge"]


def test_articles_pertinents_retenus(archive, reglages):
    pages = extraire(archive, reglages)
    titres = {p["titre_article"] for p in pages}
    assert "Hypothermie" in titres
    assert "Amanite phalloïde" in titres
    assert "Bouriane" in titres


def test_article_hors_sujet_ecarte(archive, reglages):
    """Le cœur du problème : une encyclopédie entière noierait le corpus."""
    titres = {p["titre_article"] for p in extraire(archive, reglages)}
    assert "Bataille de Marignan" not in titres


def test_ebauche_ecartee(archive, reglages):
    titres = {p["titre_article"] for p in extraire(archive, reglages)}
    assert "Ébauche" not in titres


def test_plafond_respecte(archive):
    r = charger_reglages()
    petit = Reglages(max_articles=2, min_caracteres=r.min_caracteres,
                     max_caracteres=r.max_caracteres, namespaces=r.namespaces,
                     exclusions=r.exclusions, semences=r.semences)
    assert len(extraire(archive, petit)) <= 2


def test_troncature_des_articles_fleuves(archive):
    r = charger_reglages()
    court = Reglages(max_articles=50, min_caracteres=100, max_caracteres=300,
                     namespaces=r.namespaces, exclusions=r.exclusions,
                     semences=r.semences)
    for p in extraire(archive, court):
        # +len(titre)+2 pour l'en-tête ajouté devant le corps.
        assert len(p["texte"]) <= 300 + len(p["titre_article"]) + 2


def test_pages_compatibles_avec_le_decoupage(archive, reglages):
    """Les pages ZIM doivent traverser le même pipeline que les PDF."""
    from ingest.chunk import chunk_document

    pages = extraire(archive, reglages)
    chunks = chunk_document({"source_id": "wikipedia-fr", "titre": "Wikipédia",
                             "pages": pages})
    assert chunks
    for c in chunks:
        assert 1 <= c.page_debut <= len(pages)
        assert c.texte.strip()


def test_html_vers_texte():
    html = "<h1>Titre</h1><script>alert(1)</script><p>Corps du texte.</p>"
    txt = html_vers_texte(html)
    assert "Corps du texte." in txt
    assert "alert" not in txt, "le script n'a pas été retiré"
    assert "<" not in txt
