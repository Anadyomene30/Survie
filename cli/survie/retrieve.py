"""Recherche hybride : plein texte + vectoriel, fusionnés par RRF.

Pourquoi les deux. La recherche vectorielle attrape les reformulations
(« j'ai froid et je tremble » -> hypothermie) mais rate les termes rares et
exacts. La recherche plein texte fait l'inverse : elle excelle sur
« Cortinarius orellanus » ou « 114 » et échoue sur une paraphrase. En survie,
les deux cas se présentent — la question est tapée dans l'urgence, avec les
mots de celui qui la pose, et elle peut porter sur un nom latin précis.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import numpy as np

from .store import Passage, Store

# Constante usuelle de la fusion réciproque de rangs. Elle amortit l'écart
# entre les premiers rangs, ce qui évite qu'une seule méthode n'impose son
# premier résultat contre l'avis de l'autre.
RRF_K = 60

CANDIDATS = 50   # par méthode, avant fusion
RETENUS = 8      # transmis au modèle

# Sièges garantis : les N premiers de CHAQUE méthode entrent dans le résultat
# final, même si la fusion les classe mal.
#
# La fusion RRF récompense l'accord entre méthodes, et c'est ce qu'on veut la
# plupart du temps. Mais elle sacrifie l'excellence dans une seule : un passage
# premier en plein texte et absent du classement vectoriel ne reçoit qu'une
# contribution, et se fait battre par des passages médiocres dans les deux, qui
# en cumulent deux.
#
# Mesuré : sur « quelle méthode pour rendre l'eau potable », la section
# « Traitement » — qui contient la réponse — sortait RANG 2 en BM25 et
# n'apparaissait pas dans les huit extraits transmis.
#
# En survie, un terme exact est souvent décisif : « ébullition »,
# « Cortinarius orellanus », « 114 ». On ne peut pas se permettre de perdre le
# meilleur résultat lexical au profit d'un consensus tiède.
SIEGES_GARANTIS = 2

# Mots vides français + interrogatifs : ils font remonter n'importe quoi en BM25.
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "a", "à",
    "au", "aux", "en", "dans", "sur", "pour", "par", "avec", "sans", "que", "qui",
    "quoi", "dont", "est", "sont", "ce", "cette", "ces", "il", "elle", "on", "je",
    "tu", "nous", "vous", "ils", "se", "sa", "son", "ses", "mon", "ma", "mes",
    "comment", "pourquoi", "quand", "où", "combien", "quel", "quelle", "quels",
    "quelles", "faire", "fait", "faut", "peut", "puis", "dois", "doit", "y",
    "n", "l", "s", "j", "c", "qu", "si", "plus", "moins", "être", "avoir",
}


def fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def terms(query: str) -> list[str]:
    raw = re.findall(r"[0-9a-zà-öø-ÿ]{2,}", query.lower())
    kept = [t for t in raw if fold(t) not in STOPWORDS]
    # Une requête entièrement composée de mots vides (« que faire ? ») ne doit
    # pas produire une recherche vide : on retombe sur les mots bruts.
    return kept or raw


def fts_term(t: str) -> str:
    """Un terme, échappé, avec correspondance par préfixe si le mot est long.

    FTS5 ne fait aucune racinisation. Sans préfixe, « frissonne » ne trouve pas
    « frissons », « tremblements » ne trouve pas « tremble » : la morphologie
    française rend la recherche exacte très fragile. On n'applique le préfixe
    qu'aux mots d'au moins 5 caractères, en dessous desquels il ramènerait
    n'importe quoi (« eau » attraperait tout mot commençant par « eau »).
    """
    esc = t.replace('"', '""')
    if len(t) < 5:
        return f'"{esc}"'
    # Au-delà de 6 caractères on tronque : le préfixe seul ne suffit pas, car
    # il ne va que dans un sens. « frissonne »* ne trouve pas « frissons » ;
    # « frisso »* trouve les deux. Racinisation grossière mais efficace en
    # français, où la variation porte surtout sur la terminaison.
    return f'"{esc[:6]}"*' if len(t) > 6 else f'"{esc}"*'


def fts_query(query: str) -> str:
    """Construit une requête FTS5 sûre.

    Les termes sont mis entre guillemets : un utilisateur qui tape « eau ? »
    ou « OR » ne doit pas déclencher une erreur de syntaxe FTS5, ni pire, une
    requête inattendue.
    """
    return " OR ".join(fts_term(t) for t in terms(query))


@dataclass
class Signaux:
    """Indices de couverture, pour décider d'un refus.

    Le score RRF ne peut PAS servir à cela : il est calculé sur des rangs, si
    bien qu'une question totalement hors sujet obtient le même score qu'une
    question bien couverte, du simple fait qu'un passage arrive toujours
    premier. Mesuré sur le corpus : 0,019 hors sujet contre 0,039 dedans, plages
    trop proches pour un seuil fiable.

    On mesure donc deux choses qui, elles, ont un sens absolu :
    - la couverture lexicale : combien des termes de la question existent
      quelque part dans le corpus. Indépendante du modèle d'embeddings, et
      explicable à l'utilisateur (« kazakhstan n'apparaît nulle part »).
    - la similarité cosinus maximale, fiable avec un vrai modèle sémantique.
    """

    termes: list[str]
    termes_connus: list[str]
    termes_inconnus: list[str]
    n_lexical: int
    cos_max: float
    poids: dict[str, float] = field(default_factory=dict)

    @property
    def couverture(self) -> float:
        """Part du « poids informationnel » de la question couverte par le corpus.

        Une fraction brute de termes trompe : dans « qui a gagné la coupe du
        monde en 1998 », « coupe » et « monde » existent dans un corpus de
        survie (coupes forestières, « dans le monde ») et donnent 40 % de
        couverture apparente. Pondérer chaque terme par sa rareté (IDF) réduit
        la contribution des mots passe-partout et fait ressortir les termes
        décisifs — ceux qui, absents, signent une question hors sujet.
        """
        if not self.termes:
            return 0.0
        total = sum(self.poids.get(t, 1.0) for t in self.termes)
        connu = sum(self.poids.get(t, 1.0) for t in self.termes_connus)
        return connu / total if total else 0.0


@dataclass
class Hit:
    passage: Passage
    score: float
    rang_lexical: int | None
    rang_vectoriel: int | None

    @property
    def methodes(self) -> str:
        m = []
        if self.rang_lexical is not None:
            m.append(f"texte#{self.rang_lexical + 1}")
        if self.rang_vectoriel is not None:
            m.append(f"vect#{self.rang_vectoriel + 1}")
        return "+".join(m)


def _lexical(store: Store, query: str, k: int) -> list[int]:
    q = fts_query(query)
    if not q:
        return []
    rows = store.con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
        "ORDER BY bm25(chunks_fts, 1.0, 2.0) LIMIT ?",
        (q, k),
    ).fetchall()
    return [r["rowid"] for r in rows]


def _vector(store: Store, qvec: np.ndarray, k: int) -> list[int]:
    mat, ids = store.vectors()
    if mat.shape[0] == 0:
        return []
    sims = mat @ qvec.astype(np.float32)
    top = np.argpartition(-sims, min(k, len(sims) - 1))[:k]
    top = top[np.argsort(-sims[top])]
    return [ids[i] for i in top]


def _boost(p: Passage) -> float:
    """Pondération éditoriale, volontairement faible.

    Elle départage des passages de pertinence comparable ; elle ne doit jamais
    faire remonter un passage hors sujet. D'où des coefficients proches de 1.
    """
    b = 1.0
    b *= {1: 1.12, 2: 1.0, 3: 0.88}.get(p.priorite, 1.0)   # source de référence
    if p.langue == "fr":
        b *= 1.05                                           # à pertinence égale
    if p.qualite < 0.6:
        b *= 0.85                                           # OCR douteux
    return b


def signaux(store: Store, query: str, qvec: np.ndarray | None = None) -> Signaux:
    import math

    n_total = max(1, int(store.meta.get("chunk_count", "1")))
    toks = terms(query)
    connus, inconnus, poids = [], [], {}
    for t in toks:
        df = store.con.execute(
            "SELECT count(*) c FROM chunks_fts WHERE chunks_fts MATCH ?",
            (fts_term(t),),
        ).fetchone()["c"]
        poids[t] = math.log(1 + n_total / (1 + df))
        (connus if df else inconnus).append(t)

    cos = 0.0
    if qvec is not None:
        mat, _ = store.vectors()
        if mat.shape[0]:
            cos = float((mat @ qvec.astype(np.float32)).max())

    return Signaux(toks, connus, inconnus, len(_lexical(store, query, CANDIDATS)),
                   cos, poids)


def search(store: Store, query: str, qvec: np.ndarray | None = None,
           k: int = RETENUS, candidats: int = CANDIDATS) -> list[Hit]:
    lex = _lexical(store, query, candidats)
    vec = _vector(store, qvec, candidats) if qvec is not None else []

    scores: dict[int, float] = {}
    rangs: dict[int, list[int | None]] = {}
    for rid in set(lex) | set(vec):
        rangs[rid] = [None, None]
    for i, rid in enumerate(lex):
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + i + 1)
        rangs[rid][0] = i
    for i, rid in enumerate(vec):
        scores[rid] = scores.get(rid, 0.0) + 1.0 / (RRF_K + i + 1)
        rangs[rid][1] = i

    passages = store.passages(list(scores))
    par_rowid: dict[int, Hit] = {
        rid: Hit(p, scores[rid] * _boost(p), rangs[rid][0], rangs[rid][1])
        for rid, p in passages.items()
    }
    classe = sorted(par_rowid.items(), key=lambda kv: -kv[1].score)

    garantis = lex[:SIEGES_GARANTIS] + vec[:SIEGES_GARANTIS]
    return _avec_sieges(classe, garantis, k)


def _avec_sieges(classe: list[tuple[int, Hit]], garantis: list[int],
                 k: int) -> list[Hit]:
    """Complète le classement fusionné avec les têtes de chaque méthode.

    Les garantis conservent leur score de fusion : ils obtiennent une place
    assurée, pas la première. Le classement reste celui du RRF.
    """
    retenus = classe[:k]
    presents = {rid for rid, _ in retenus}
    manquants = [(rid, par) for rid, par in classe
                 if rid in garantis and rid not in presents]
    if not manquants:
        return [h for _, h in retenus]
    # On évince les derniers du classement fusionné, jamais les premiers.
    garde = retenus[:max(0, k - len(manquants))]
    fusion = garde + manquants[:k]
    fusion.sort(key=lambda kv: -kv[1].score)
    return [h for _, h in fusion[:k]]
