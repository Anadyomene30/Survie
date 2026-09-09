"""Tests du mode urgence.

Propriété centrale : ce chemin ne dépend de rien. Pas d'index, pas de vecteurs,
pas de modèle, pas de réseau. Si tout le reste est cassé, les gestes qui sauvent
doivent rester accessibles — et instantanément.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli"))

from survie.urgence import charger, chercher, rendu, sommaire  # noqa: E402

FICHES = charger()


def test_toutes_les_fiches_ont_un_entete():
    assert len(FICHES) >= 9
    for f in FICHES:
        assert f.titre and f.titre != f.nom, f"{f.nom} : titre manquant"
        assert f.declencheurs, f"{f.nom} : aucun déclencheur"
        assert len(f.corps) > 200, f"{f.nom} : corps trop court"


@pytest.mark.parametrize("question,attendu", [
    ("il saigne beaucoup du bras", "01-hemorragie"),
    ("elle ne répond pas", "02-inconscience"),
    ("il ne respire plus", "03-arret-cardiaque"),
    ("je tremble je suis trempé", "04-hypothermie"),
    ("il a mangé un champignon", "05-intoxication"),
    ("morsure de vipère", "06-morsure-piqure"),
    ("piqûre de frelon gorge qui gonfle", "06-morsure-piqure"),
    ("brûlure à la main", "07-brulure-noyade"),
    ("pas de réseau pour appeler", "08-alerte"),
    ("par où commencer", "00-lire-dabord"),
    ("garrot", "01-hemorragie"),
])
def test_routage(question, attendu):
    trouvees = chercher(question, FICHES)
    assert trouvees, f"aucune fiche pour « {question} »"
    assert trouvees[0][0].nom == attendu


def test_sans_accents_et_sans_ponctuation():
    """Une question tapée dans l'urgence n'a ni accents ni majuscules."""
    assert chercher("il saigne", FICHES)[0][0].nom == "01-hemorragie"
    assert chercher("HYPOTHERMIE", FICHES)[0][0].nom == "04-hypothermie"
    assert chercher("piqure de tique", FICHES)[0][0].nom == "06-morsure-piqure"


def test_gestes_a_ne_pas_faire_presents():
    """Les gestes nuisibles comptent autant que les gestes utiles.

    Chacun de ces points est une erreur courante, encore imprimée dans des
    manuels diffusés, et chacun peut tuer.
    """
    corpus = {f.nom: f.corps.lower() for f in FICHES}
    assert "jamais desserrer" in corpus["01-hemorragie"].replace("ne ", "")
    assert "pas d'incision" in corpus["06-morsure-piqure"]
    assert "jamais d'alcool" in corpus["04-hypothermie"]
    assert "ne pas faire vomir" in corpus["05-intoxication"]
    assert "ne pas percer les cloques" in corpus["07-brulure-noyade"]


def test_numeros_d_urgence_presents():
    alerte = [f for f in FICHES if f.nom == "08-alerte"][0]
    for numero in ("15", "18", "112", "114"):
        assert numero in alerte.corps


def test_aucune_dependance_lourde():
    """Le module ne doit importer ni numpy, ni sqlite, ni mlx."""
    source = (Path(__file__).resolve().parent.parent
              / "cli" / "survie" / "urgence.py").read_text(encoding="utf-8")
    for interdit in ("numpy", "sqlite3", "mlx", "import torch", "requests", "urllib"):
        assert interdit not in source, f"dépendance interdite : {interdit}"


def test_reponse_instantanee():
    """En urgence, la latence est une caractéristique de sûreté."""
    debut = time.perf_counter()
    for _ in range(20):
        chercher("il saigne beaucoup", FICHES)
    ecoule = (time.perf_counter() - debut) / 20
    assert ecoule < 0.02, f"{ecoule * 1000:.1f} ms par recherche, trop lent"


def test_rendu_et_sommaire():
    assert "HÉMORRAGIE" in rendu(FICHES[1]).upper()
    assert "01-hemorragie" in sommaire(FICHES)
