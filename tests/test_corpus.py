"""Validation du corpus lui-meme.

Ces tests portent sur les fiches, pas sur le code : une fiche mal formee ou
non relue est un defaut au meme titre qu'un bug.
"""

from __future__ import annotations

import datetime as dt

import pytest

from survie.config import DOSSIER_CONNAISSANCES
from survie.corpus.chunker import decouper
from survie.corpus.loader import charger_fiches
from survie.corpus.schema import FicheInvalide, analyser_entete, valider

FICHES = charger_fiches(DOSSIER_CONNAISSANCES)


def test_le_corpus_n_est_pas_vide():
    assert len(FICHES) >= 30


@pytest.mark.parametrize("fiche", FICHES, ids=lambda f: f.identifiant)
def test_chaque_fiche_est_exploitable(fiche):
    """En-tete valide, corps non vide, date de relecture plausible."""
    assert fiche.titre.strip()
    assert len(fiche.corps) > 200, "fiche trop courte pour etre utile"
    relecture = dt.date.fromisoformat(fiche.verifie_le)
    assert dt.date(2024, 1, 1) <= relecture <= dt.date.today()


@pytest.mark.parametrize("fiche", FICHES, ids=lambda f: f.identifiant)
def test_chaque_fiche_produit_des_fragments(fiche):
    fragments = decouper(fiche)
    assert fragments, "aucun fragment indexable"
    for fragment in fragments:
        assert fiche.titre in fragment.texte_indexable


def test_les_domaines_vitaux_sont_couverts():
    domaines = {f.domaine for f in FICHES}
    for indispensable in ("eau", "sante", "agriculture", "hygiene", "urgence"):
        assert indispensable in domaines


def test_il_existe_des_fiches_vitales_immediates():
    """La commande 'survie urgence' repose sur leur existence."""
    vitales = [f for f in FICHES if f.criticite == "vitale" and f.delai == "immediat"]
    assert len(vitales) >= 5


def test_entete_absent_rejete():
    with pytest.raises(FicheInvalide):
        analyser_entete("Pas d'en-tete du tout.")


def test_criticite_inconnue_rejetee():
    metadonnees, _ = analyser_entete(
        "---\ntitre: T\ndomaine: d\ncriticite: moyenne\ndelai: jours\n"
        "verifie_le: 2026-01-01\n---\nCorps."
    )
    with pytest.raises(FicheInvalide, match="criticite"):
        valider(metadonnees)


def test_date_invalide_rejetee():
    metadonnees, _ = analyser_entete(
        "---\ntitre: T\ndomaine: d\ncriticite: vitale\ndelai: jours\n"
        "verifie_le: hier\n---\nCorps."
    )
    with pytest.raises(FicheInvalide, match="verifie_le"):
        valider(metadonnees)


def test_liste_en_ligne_analysee():
    metadonnees, corps = analyser_entete(
        "---\ntitre: T\ndomaine: d\ncriticite: vitale\ndelai: jours\n"
        "prerequis: [feu, recipient]\nverifie_le: 2026-01-01\n---\nLe corps."
    )
    assert valider(metadonnees)["prerequis"] == ["feu", "recipient"]
    assert corps == "Le corps."
