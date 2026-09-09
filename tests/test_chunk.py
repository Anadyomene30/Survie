"""Tests du découpage.

L'exactitude de la page citée est l'invariant central du projet : une réponse
qui renvoie vers la mauvaise page est plus dangereuse qu'une absence de réponse,
parce qu'elle est vérifiable en apparence et fausse en réalité.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingest.chunk import chunk_document, estimate_tokens  # noqa: E402
from ingest import config  # noqa: E402

FILLER = ("Il faut donc juger sur les signes observés et non sur ce que la "
          "personne affirme ressentir. ")


def doc_deux_pages():
    return {
        "source_id": "test",
        "titre": "Test",
        "pages": [
            {"numero": 1, "qualite": 1.0, "image": "test/00001.png", "texte":
             "3.2 Hypothermie\n\n"
             "L'hypothermie s'installe bien au-dessus de zéro degré. Un vent "
             "modéré sur des vêtements humides suffit, même à dix degrés.\n\n"
             "Signes précoces\n\n"
             "Frissons incontrôlables, maladresse des mains, élocution "
             "ralentie.\n\n" + FILLER * 12},
            {"numero": 2, "qualite": 0.9, "image": "test/00002.png", "texte":
             "Conduite à tenir\n\n"
             "Sortir du vent avant toute chose. Retirer les vêtements mouillés. "
             "Isoler du sol, qui pompe la chaleur bien plus vite que l'air.\n\n"
             "CONSERVATION DES ALIMENTS\n\n"
             "Le botulisme se développe en anaérobie dans les conserves mal "
             "acidifiées, sans produire ni odeur ni bombement systématique."},
        ],
    }


def test_page_citee_contient_le_texte():
    """Régression : un fragment était cité sur la page précédant son contenu.

    Le recouvrement conservait le dernier paragraphe de la page N sans mettre à
    jour la page de début, si bien qu'un fragment entièrement situé en page N+1
    était cité « p. N » et affichait la vignette de la page N.
    """
    doc = doc_deux_pages()
    pages = {p["numero"]: p["texte"] for p in doc["pages"]}

    for c in chunk_document(doc):
        # Le premier paragraphe du fragment doit se trouver dans la page citée.
        premier = c.texte.split("\n\n")[0][:60]
        assert premier in pages[c.page_debut], (
            f"{c.chunk_id} cité p.{c.page_debut} mais son texte n'y est pas : {premier!r}"
        )


def test_vignette_correspond_a_la_page_citee():
    for c in chunk_document(doc_deux_pages()):
        assert c.image == f"test/{c.page_debut:05d}.png"


def test_les_trois_formes_de_titre_sont_reconnues():
    """Titre numéroté, capitales, casse de titre.

    Un titre trop court pour porter un fragment à lui seul est fusionné avec la
    suite, mais son texte est alors conservé dans le corps : il reste trouvable
    par la recherche plein texte. On vérifie donc la présence, pas l'étiquette.
    """
    chunks = chunk_document(doc_deux_pages())
    vus = {c.section for c in chunks} | {c.texte for c in chunks}
    for titre in ("3.2 Hypothermie", "CONSERVATION DES ALIMENTS", "Conduite à tenir"):
        assert any(titre in v for v in vus), f"titre perdu : {titre}"


def test_aucune_perte_de_contenu():
    """L'invariant le plus fort : tout paragraphe se retrouve dans un fragment.

    Un manuel de survie amputé silencieusement d'un paragraphe est un piège :
    le système répondra avec assurance sur la base d'un texte incomplet.
    """
    doc = doc_deux_pages()
    concat = "\n".join(c.texte for c in chunk_document(doc))
    for page in doc["pages"]:
        for para in page["texte"].split("\n\n"):
            para = " ".join(para.split()).strip()
            if len(para) < 20:
                continue
            # Les très longs paragraphes sont fendus par phrases : on teste le début.
            assert para[:80] in concat, f"paragraphe perdu : {para[:60]!r}"


def test_pas_de_recouvrement_par_dessus_un_titre():
    """Le recouvrement donne du contexte ; à travers un titre il donne un faux contexte.

    Si le dernier paragraphe d'« Hypothermie » repartait dans le fragment
    « Conservation des aliments », une recherche sur le botulisme remonterait
    un texte parlant de vêtements mouillés.
    """
    doc = {"source_id": "t", "titre": "t", "pages": [{
        "numero": 1, "qualite": 1.0, "image": None,
        "texte": "PREMIERE SECTION\n\n" + FILLER * 40
                 + "\n\nSECONDE SECTION\n\n"
                 + "Le botulisme se développe en anaérobie. " * 30,
    }]}
    for c in chunk_document(doc):
        if "botulisme" in c.texte:
            assert "signes observés" not in c.texte, "fuite de la section précédente"


def test_fenetre_respectee():
    for c in chunk_document(doc_deux_pages()):
        assert c.tokens <= config.CHUNK_MAX_TOKENS
        assert c.page_debut <= c.page_fin


def test_paragraphe_hors_norme_est_fendu():
    doc = {"source_id": "x", "titre": "x", "pages": [
        {"numero": 1, "qualite": 1.0, "image": None, "texte": FILLER * 200}]}
    chunks = chunk_document(doc)
    assert len(chunks) > 1
    assert all(c.tokens <= config.CHUNK_MAX_TOKENS for c in chunks)


def test_estimation_tokens_croissante():
    assert estimate_tokens("a") < estimate_tokens("a" * 100)
