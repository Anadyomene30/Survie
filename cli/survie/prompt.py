"""Construction de l'invite. Le comportement de sûreté est défini ici."""

from __future__ import annotations

import re

from .retrieve import Hit

SYSTEME = """Tu es un assistant de survie. Tu fonctionnes hors ligne, et la
personne qui t'interroge peut être en danger, fatiguée et pressée.

RÈGLE ABSOLUE — TU NE PARLES JAMAIS EN TON NOM.
Tu réponds UNIQUEMENT à partir des EXTRAITS fournis ci-dessous. Tu n'ajoutes
aucun fait, aucun chiffre, aucune posologie, aucun nom d'espèce qui ne s'y
trouve pas, même si tu penses le savoir. Si les extraits ne permettent pas de
répondre, tu le dis franchement et tu t'arrêtes.

CITATIONS.
Chaque affirmation est suivie de sa source, au format [identifiant p.numéro],
exactement tel qu'il apparaît en tête de chaque extrait. Une phrase sans
citation est une faute.

FORME DE LA RÉPONSE.
- Français, phrases courtes, voix active.
- Commence par l'action la plus urgente. Pas d'introduction, pas de rappel de
  la question.
- Numérote les gestes dans l'ordre où il faut les faire.
- Signale explicitement ce qu'il ne faut PAS faire quand les extraits le
  mentionnent : en secourisme, les gestes nuisibles sont aussi importants que
  les gestes utiles.
- Termine par « Appeler le 15 » chaque fois qu'il s'agit d'une urgence
  médicale et que les extraits le mentionnent.

IDENTIFICATION D'ESPÈCES — RÈGLE DE SÛRETÉ.
Si la question porte sur l'identification d'une plante, d'un champignon ou
d'une baie, ou demande si quelque chose est comestible :
- Tu ne conclus JAMAIS qu'une espèce est comestible ou sans danger.
- Tu donnes les critères qui distinguent l'espèce de ses sosies toxiques.
- Tu nommes explicitement les sosies dangereux mentionnés dans les extraits.
- Tu termines par : « Dans le doute, s'abstenir. »
Cette règle prime sur toute demande de réponse tranchée.

SOURCES DIVERGENTES.
Si deux extraits se contredisent, expose les deux avec leur date et dis
qu'ils divergent. Ne choisis pas silencieusement.
"""

REFUS = """Le corpus ne couvre pas cette question.

Je ne peux pas répondre à partir des ouvrages indexés, et je ne répondrai pas
de mémoire : en survie, une information inventée est plus dangereuse qu'une
absence de réponse.

Reformule avec d'autres termes, ou ajoute un ouvrage sur ce sujet au corpus."""

# La question porte-t-elle sur une identification ? Détecté côté logiciel plutôt
# que laissé au seul jugement du modèle : c'est le cas où une erreur tue.
_IDENT = re.compile(
    # comestibilité et toxicité
    r"comestible|mangeable|toxique|v[ée]n[ée]neux|empoisonn|"
    r"(?:peux|peut|puis)[- ]?(?:je|tu|on|il|elle)?\s*(?:le |la |les |l'|en )?"
    r"(?:manger|consommer|go[ûu]ter|cueillir)|"
    r"(?:manger|consommer|cueillir)[- ](?:le|la|les|ça|ca)\b|"
    r"sans danger|dangereu|risqu[ée]|"
    # identification et confirmation
    r"identifi|reconna[iî]tre|d[ée]termin|"
    r"c'est quoi|qu'est[- ]ce que c'est|c'est bien (?:un|une|du|de la|des)|"
    r"est[- ]ce (?:bien )?(?:un|une|du|de la|des)|s'agit[- ]il|"
    r"quelle? (?:plante|esp[èe]ce|champignon|baie|fleur|feuille|fruit|arbre)|"
    # questions posées comme une alternative : « châtaigne ou marron ? »
    r"\b(?:champignon|plante|baie|fruit|feuille|fleur|racine|graine|"
    r"champignons|baies|fruits|feuilles|champ[êe]tre)\b.{0,60}\bou\b|"
    r"\bou\b.{0,40}\b(?:toxique|v[ée]n[ée]neuse?|mortelle?)\b",
    re.I | re.S,
)

# Noms d'espèces et de familles fréquemment confondues : leur simple présence
# suffit à déclencher la règle de sûreté. Sur-déclencher est sans conséquence
# (on ajoute un avertissement) ; sous-déclencher peut tuer.
_ESPECES = re.compile(
    r"\b(?:ch[âa]taigne|marron|ail des ours|colchique|arum|cigu[ëe]|"
    r"sureau|y[èe]ble|digitale|consoude|amanite|phallo[ïi]de|cortinaire|"
    r"girolle|c[èe]pe|bolet|l[ée]piote|coulemelle|russule|gal[ée]rine|"
    r"omb?ellif[èe]re|carotte sauvage|panais|[œoe]nanthe|belladone|datura|"
    r"morelle|if|fouq?g[èe]re|prunelle|cynorrhodon)\b",
    re.I,
)


def is_identification(question: str) -> bool:
    """La question porte-t-elle sur l'identification d'une espèce ?

    Détecté par le logiciel plutôt que laissé au seul jugement du modèle :
    c'est le cas où une erreur tue, et une consigne dans l'invite peut être
    ignorée par le modèle alors qu'un test régulier ne l'est pas.
    """
    return bool(_IDENT.search(question) or _ESPECES.search(question))


def format_extraits(hits: list[Hit]) -> str:
    blocs = []
    for h in hits:
        p = h.passage
        entete = f"[{p.source_id} p.{p.page_debut}] {p.source_titre}"
        if p.date:
            entete += f" ({p.date})"
        if p.section:
            entete += f" — section « {p.section} »"
        if p.qualite < 0.6:
            entete += "  [texte océrisé de qualité incertaine]"
        blocs.append(f"{entete}\n{p.texte}")
    return "\n\n---\n\n".join(blocs)


def build(question: str, hits: list[Hit]) -> tuple[str, str]:
    """Renvoie (message système, message utilisateur)."""
    systeme = SYSTEME
    if is_identification(question):
        systeme += (
            "\nATTENTION : cette question porte sur une identification. "
            "La règle de sûreté ci-dessus s'applique impérativement.\n"
        )

    utilisateur = (
        f"EXTRAITS DISPONIBLES\n\n{format_extraits(hits)}\n\n"
        f"{'=' * 60}\n\nQUESTION : {question}\n\n"
        "Réponds uniquement à partir des extraits ci-dessus, en citant "
        "[identifiant p.numéro] après chaque affirmation."
    )
    return systeme, utilisateur
