"""Tests du validateur de citations.

Le mode d'échec redouté n'est pas « le modèle refuse de répondre », c'est
« le modèle invente une référence plausible ». Une citation fabriquée donne à
une phrase fausse l'apparence d'une phrase vérifiée. Ces tests couvrent
précisément ce cas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))

from survie.retrieve import Hit  # noqa: E402
from survie.store import Passage  # noqa: E402
from survie.validate import verifier  # noqa: E402


def hit(source_id="bouriane", page_debut=2, page_fin=2):
    p = Passage(
        chunk_id=f"{source_id}#1", source_id=source_id, source_titre="Pack Bouriane",
        auteur="", date=2026, licence="cc-by-sa", page_debut=page_debut,
        page_fin=page_fin, section="Eau", texte="…", qualite=1.0, image=None,
        priorite=1, langue="fr",
    )
    return Hit(p, 1.0, 0, 0)


HITS = [hit("bouriane", 2, 3), hit("fm-21-76", 40, 40)]


def test_citation_valide():
    r = verifier("Sortir du vent avant tout, c'est la première chose à faire "
                 "en cas d'hypothermie. [bouriane p.2]", HITS)
    assert r.ok, r.problemes
    assert r.citations == 1 and r.valides == 1


def test_source_inventee_est_detectee():
    """Le cas central : une source qui n'a jamais été transmise."""
    r = verifier("Il faut administrer 500 mg d'amoxicilline toutes les huit "
                 "heures sans attendre. [merck-manual p.221]", HITS)
    assert not r.ok
    assert any(p.genre == "source-inconnue" for p in r.problemes)
    assert r.valides == 0


def test_page_hors_extrait_est_detectee():
    """Source réelle, page jamais transmise : la référence est fabriquée."""
    r = verifier("La dose recommandée est de deux comprimés par jour pendant "
                 "cinq jours au minimum. [bouriane p.99]", HITS)
    assert not r.ok
    assert any(p.genre == "page-hors-extrait" for p in r.problemes)


def test_plage_de_pages_acceptee():
    """Un fragment qui enjambe une fin de page autorise les deux pages."""
    for page in (2, 3):
        r = verifier(f"Cette affirmation porte sur un point technique précis "
                     f"et détaillé. [bouriane p.{page}]", HITS)
        assert r.ok, f"page {page} refusée à tort"


def test_phrase_sans_source_est_signalee():
    r = verifier("L'hypothermie s'installe bien au-dessus de zéro degré et "
                 "tue rapidement les personnes mouillées.", HITS)
    assert not r.ok
    assert any(p.genre == "phrase-sans-source" for p in r.problemes)


def test_formule_de_prudence_exemptee():
    """« Dans le doute, s'abstenir » est imposée par la règle de sûreté.

    L'exiger sourcée pousserait le modèle à lui coller une citation inventée
    pour satisfaire le validateur — l'inverse du but recherché.
    """
    r = verifier("Le colchique n'a aucune odeur alors que l'ail des ours sent "
                 "puissamment l'ail au froissement. [bouriane p.3] "
                 "Dans le doute, s'abstenir.", HITS)
    assert r.ok, r.problemes


def test_titres_et_listes_non_soumis():
    r = verifier("# Conduite à tenir\n- point\nSortir du vent immédiatement, "
                 "avant même de retirer les vêtements. [bouriane p.2]", HITS)
    assert r.ok, r.problemes


def test_taux_partiel():
    r = verifier("Première affirmation correctement sourcée ici. [bouriane p.2] "
                 "Seconde affirmation avec une source fabriquée. [faux p.1]", HITS)
    assert r.citations == 2 and r.valides == 1
    assert r.taux == 0.5


def test_espacement_tolere():
    r = verifier("Une affirmation suffisamment longue pour être contrôlée par "
                 "le validateur de citations. [bouriane p. 2]", HITS)
    assert r.citations == 1 and r.valides == 1
