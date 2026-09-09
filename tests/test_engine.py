"""Test d'intégration : corpus -> index -> question -> réponse.

Construit un index miniature dans un répertoire temporaire et vérifie les
invariants de bout en bout. Aucun réseau, aucun modèle : le backend
d'embeddings de test suffit à valider la plomberie.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cli"))

from ingest.chunk import chunk_document  # noqa: E402
from ingest.embed import HashingEmbedder  # noqa: E402
from survie.engine import Engine  # noqa: E402
from survie.llm import NoLLM  # noqa: E402
from survie.store import IndexMismatch  # noqa: E402

FICHES = {
    "eau": """# Eau en terrain karstique

Le piège du karst

En terrain karstique, l'eau circule vite dans des fissures sans filtration.
Une source peut sortir limpide tout en étant chargée en bactéries. La
limpidité n'est pas un indice de potabilité, c'est même l'inverse.

Traitement

Porter l'eau à gros bouillons est la méthode la plus sûre et la moins
dépendante du matériel disponible sur le terrain.
""",
    "froid": """# Hypothermie

Signes précoces

Frissons incontrôlables, maladresse des mains, élocution ralentie. La personne
nie souvent son état car la confusion fait partie du tableau clinique observé.

Conduite à tenir

Sortir du vent avant toute chose. Retirer les vêtements mouillés. Isoler du
sol, qui pompe la chaleur bien plus vite que l'air ambiant ne le fait.
""",
}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """Construit un index complet dans un répertoire temporaire."""
    import sqlite3

    from ingest.build_db import SCHEMA

    d = tmp_path_factory.mktemp("survie")
    pages = [{"numero": i, "texte": t, "qualite": 1.0, "image": f"f/{i:05d}.png"}
             for i, t in enumerate(FICHES.values(), start=1)]
    chunks = chunk_document({"source_id": "fiches", "titre": "Fiches", "pages": pages})
    assert chunks, "le découpage n'a produit aucun fragment"

    emb = HashingEmbedder(256)
    vecs = emb.encode([f"{c.section}\n{c.texte}" for c in chunks])

    path = d / "survie.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                ("fiches", "Fiches de test", "SURVIE", 2026, "fr", "cc-by-sa",
                 json.dumps(["eau", "froid"]), 1, ""))
    con.executemany(
        "INSERT INTO chunks (rowid_, chunk_id, source_id, page_debut, page_fin,"
        " section, texte, tokens, qualite, image, priorite, langue, embedding)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(i, c.chunk_id, c.source_id, c.page_debut, c.page_fin, c.section,
          c.texte, c.tokens, c.qualite, c.image, 1, "fr", vecs[i].tobytes())
         for i, c in enumerate(chunks)])
    con.executemany("INSERT INTO meta VALUES (?,?)", [
        ("schema_version", "1"), ("embed_model", emb.name),
        ("embed_dim", str(emb.dim)), ("chunk_count", str(len(chunks)))])
    con.commit()
    con.close()
    return path


@pytest.fixture(scope="module")
def engine(db):
    return Engine(db, NoLLM(), HashingEmbedder(256))


def test_question_couverte_nest_pas_refusee(engine):
    rep = engine.ask("l'eau de la source est claire, est-elle potable")
    assert not rep.refus
    assert rep.hits


def test_question_hors_corpus_est_refusee(engine):
    rep = engine.ask("quelle est la capitale du Kazakhstan")
    assert rep.refus
    assert "kazakhstan" in rep.texte.lower(), "le refus doit nommer le terme inconnu"


def test_refus_explique_les_termes_inconnus(engine):
    rep = engine.ask("explique la transformée de Fourier")
    assert rep.refus
    assert "fourier" in rep.texte.lower()


def test_citations_pointent_vers_des_pages_reelles(engine):
    """Toute page citable doit exister dans la source."""
    rep = engine.ask("comment rendre l'eau potable")
    for h in rep.hits:
        assert 1 <= h.passage.page_debut <= len(FICHES)
        assert h.passage.page_debut <= h.passage.page_fin


def test_question_identification_est_signalee(engine):
    rep = engine.ask("ce champignon est-il comestible")
    assert rep.identification


def test_index_avec_autre_modele_est_refuse(db):
    """Un embedder différent produirait du bruit sans le moindre signal d'erreur."""
    with pytest.raises(IndexMismatch):
        Engine(db, NoLLM(), HashingEmbedder(512))


def test_morphologie_francaise(engine):
    """« frissonne » doit trouver « frissons » malgré l'absence de racinisation FTS5."""
    rep = engine.ask("il ne frissonne plus et devient somnolent")
    textes = " ".join(h.passage.texte for h in rep.hits).lower()
    assert "frissons" in textes


def test_recherche_sans_vecteurs(db):
    """Le mode plein texte seul doit fonctionner sans aucun modèle."""
    eng = Engine(db, NoLLM(), None)
    rep = eng.ask("hypothermie vêtements mouillés")
    assert not rep.refus and rep.hits
    eng.close()


def test_pas_de_socket_reseau(engine):
    """Garde-fou : le moteur ne doit ouvrir aucune connexion réseau."""
    import socket

    original = socket.socket

    class Interdit(original):  # type: ignore[misc,valid-type]
        def __init__(self, *a, **k):
            raise AssertionError("le moteur a tenté d'ouvrir une socket réseau")

    socket.socket = Interdit  # type: ignore[misc]
    try:
        engine.ask("comment traiter l'eau d'une source")
    finally:
        socket.socket = original  # type: ignore[misc]


def test_refus_est_un_filtre_rapide_pas_une_garantie(engine):
    """Documente une limite assumée, pour qu'on ne la « corrige » pas à tort.

    Le refus lexical attrape le grossier. Il laisse passer les homographes —
    « capitale du Kazakhstan » quand le corpus contient « l'heure est capitale »,
    « soufflé au fromage » quand il contient « le souffle sur la joue ». C'est
    structurel : la forme ne dit rien du sens.

    Le réflexe serait de durcir le seuil. Ce serait une erreur : cela
    provoquerait des faux refus, qui privent d'aide quelqu'un dont la question
    EST couverte — l'erreur la plus grave des deux. Le vrai garde-fou est en
    aval : le modèle, en mode RAG strict, refuse de lui-même sur des extraits
    hors sujet, et lui ne se dégrade pas avec la taille du corpus.

    Ce test verrouille donc le comportement voulu : aucun faux refus sur des
    questions couvertes, quitte à laisser passer des questions qui ne le sont pas.
    """
    for question in ["comment rendre l'eau potable",
                     "il ne frissonne plus et devient somnolent",
                     "hypothermie vêtements mouillés"]:
        assert not engine.ask(question).refus, f"faux refus : {question}"
