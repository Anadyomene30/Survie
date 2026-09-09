"""Tests du registre des doctrines périmées.

Deux risques symétriques, et le second est le plus insidieux :

- ne pas avertir alors qu'un manuel de 1992 recommande de desserrer un garrot ;
- avertir sur tout, tout le temps. Un garde-fou qui crie sans cesse est un
  garde-fou qu'on apprend à ignorer, et le jour où il a raison, personne ne lit.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))

from survie.divergence import (  # noqa: E402
    charger, detecter, ecart_de_dates, encart, rendu_humain,
)
from survie.retrieve import Hit  # noqa: E402
from survie.store import Passage  # noqa: E402

REGISTRE = charger()


def hit(texte, date, source_id="src", section=""):
    p = Passage(chunk_id=f"{source_id}#1", source_id=source_id,
                source_titre="T", auteur="", date=date, licence="",
                page_debut=1, page_fin=1, section=section, texte=texte,
                qualite=1.0, image=None, priorite=2, langue="fr")
    return Hit(p, 1.0, 0, 0)


def test_registre_charge():
    assert len(REGISTRE) >= 8
    assert any(d.id == "garrot" for d in REGISTRE)
    assert all(d.ancienne and d.actuelle and d.bascule for d in REGISTRE)


def test_question_declenche_meme_sans_extrait_ancien():
    """Quand l'utilisateur nomme le sujet, on répond, quelle que soit la source.

    Il est en train de se poser la question ; c'est le moment de corriger.
    """
    d = detecter("faut-il desserrer un garrot", [hit("texte neutre", 2026)], REGISTRE)
    assert [x.id for x in d] == ["garrot"]


def test_extrait_recent_ne_declenche_pas():
    """Condition de fond : une doctrine périmée vient d'une source antérieure.

    Si tous les extraits datent d'après la bascule, il n'y a rien à corriger.
    """
    recent = hit("Jamais d'alcool en cas d'hypothermie, la vasodilatation trompe.", 2026)
    assert detecter("comment me réchauffer", [recent], REGISTRE) == []


def test_extrait_ancien_declenche():
    vieux = hit("En cas d'hypothermie, donner un alcool fort pour réchauffer.", 1957)
    ids = [d.id for d in detecter("comment me réchauffer", [vieux], REGISTRE)]
    assert "alcool-hypothermie" in ids


def test_mot_isole_ne_suffit_pas():
    """Une mention de passage ne doit pas déclencher.

    Régression : une fiche faune évoquant garrot, alcool et vomissement en
    passant déclenchait quatre avertissements sur une question de morsure,
    noyant le seul qui comptait.
    """
    passant = hit("Le garrot est mentionné une fois ici, sans plus de détail.", 1992)
    assert detecter("comment faire un feu sous la pluie", [passant], REGISTRE) == []


def test_plafond_des_avertissements():
    bavard = hit("garrot desserrer, aspirer le venin par succion, faire vomir, "
                 "alcool fort hypothermie, brûlure beurre, apnée hyperventilation", 1957)
    d = detecter("garrot venin faire vomir alcool brûlure apnée hyperventilation",
                 [bavard], REGISTRE)
    assert len(d) <= 3, "un mur d'avertissements n'est pas lu"


def test_critiques_en_premier():
    bavard = hit("x", 1957)
    d = detecter("garrot et brûlure", [bavard], REGISTRE)
    if len(d) >= 2:
        gravites = [x.gravite for x in d]
        assert gravites.index("critique") < len(gravites), "critiques relégués"
        assert d[0].critique


def test_ecart_de_dates():
    assert ecart_de_dates([hit("a", 1957), hit("b", 2024)]) == (1957, 2024)
    assert ecart_de_dates([hit("a", 2020), hit("b", 2024)]) is None
    assert ecart_de_dates([hit("a", None)]) is None


def test_encart_contient_les_deux_doctrines():
    d = detecter("faut-il desserrer un garrot", [hit("x", 2026)], REGISTRE)
    txt = encart(d)
    assert "PÉRIMÉ" in txt and "ACTUEL" in txt
    assert "JAMAIS desserré" in txt
    # L'encart est une consigne, pas un document : le modèle ne doit pas le citer.
    assert "pas à être cité" in txt


def test_encart_vide_si_rien():
    assert encart([], None) == ""


def test_rendu_humain_sans_modele():
    """Le mode extraits seuls doit afficher l'avertissement sans reformulation."""
    d = detecter("aspirer le venin", [hit("x", 2026)], REGISTRE)
    txt = rendu_humain(d)
    assert "Périmé" in txt and "Actuel" in txt
