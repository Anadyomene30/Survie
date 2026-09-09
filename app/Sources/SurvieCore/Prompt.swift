import Foundation

/// Invite système et règles de sûreté. Doit rester identique à `cli/survie/prompt.py`.
public enum Prompt {

    public static let systeme = """
    Tu es un assistant de survie. Tu fonctionnes hors ligne, et la personne qui
    t'interroge peut être en danger, fatiguée et pressée.

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
    - Commence par l'action la plus urgente. Pas d'introduction.
    - Numérote les gestes dans l'ordre où il faut les faire.
    - Signale explicitement ce qu'il ne faut PAS faire quand les extraits le
      mentionnent : en secourisme, les gestes nuisibles sont aussi importants
      que les gestes utiles.
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

    public static let refus = """
    Le corpus ne couvre pas cette question.

    Je ne peux pas répondre à partir des ouvrages indexés, et je ne répondrai pas
    de mémoire : en survie, une information inventée est plus dangereuse qu'une
    absence de réponse.

    Reformule avec d'autres termes, ou ajoute un ouvrage sur ce sujet au corpus.
    """

    /// Détecté par le logiciel plutôt que laissé au seul jugement du modèle :
    /// c'est le cas où une erreur tue, et une consigne dans l'invite peut être
    /// ignorée par le modèle alors qu'un test régulier ne l'est pas.
    /// Sur-déclencher est sans conséquence — on ajoute un avertissement ;
    /// sous-déclencher peut tuer.
    static let motifsIdentification = [
        "comestible", "mangeable", "toxique", "veneneux", "empoisonn",
        "puis-je manger", "je peux le manger", "je peux la manger",
        "peut-on manger", "peux-tu manger", "consommer", "cueillir",
        "sans danger", "dangereu", "identifi", "reconnaitre", "determin",
        "c'est quoi", "qu'est-ce que c'est", "c'est bien un", "c'est bien une",
        "c'est bien du", "c'est bien de la", "est-ce un", "est-ce une",
        "est-ce du", "est-ce de la", "s'agit-il", "quelle plante",
        "quelle espece", "quel champignon", "quelle baie",
    ]

    static let especesSensibles = [
        "chataigne", "marron", "ail des ours", "colchique", "arum", "cigue",
        "sureau", "yeble", "digitale", "consoude", "amanite", "phalloide",
        "cortinaire", "girolle", "cepe", "bolet", "lepiote", "coulemelle",
        "russule", "galerine", "ombellifere", "carotte sauvage", "panais",
        "oenanthe", "belladone", "datura", "morelle", "prunelle", "cynorrhodon",
    ]

    public static func estIdentification(_ question: String) -> Bool {
        let q = Retrieve.plier(question)
        if motifsIdentification.contains(where: { q.contains($0) }) { return true }
        if especesSensibles.contains(where: { q.contains($0) }) { return true }
        // Question posée comme une alternative : « châtaigne ou marron ? »
        let objets = ["champignon", "plante", "baie", "fruit", "feuille", "fleur", "racine"]
        return objets.contains(where: { q.contains($0) }) && q.contains(" ou ")
    }

    public static func formaterExtraits(_ hits: [Retrieve.Hit]) -> String {
        hits.map { h in
            let p = h.passage
            var entete = "[\(p.sourceID) p.\(p.pageDebut)] \(p.sourceTitre)"
            if let d = p.date { entete += " (\(d))" }
            if !p.section.isEmpty { entete += " — section « \(p.section) »" }
            if p.qualite < 0.6 { entete += "  [texte océrisé de qualité incertaine]" }
            return "\(entete)\n\(p.texte)"
        }
        .joined(separator: "\n\n---\n\n")
    }

    /// `encart` porte l'avertissement sur les doctrines ayant changé. Il est
    /// placé AVANT les extraits : ce qui suit doit être lu à sa lumière, et un
    /// avertissement relégué en fin d'invite pèse moins qu'un texte de manuel
    /// bien tourné.
    public static func construire(question: String, hits: [Retrieve.Hit],
                                  encart: String = "") -> (systeme: String, utilisateur: String) {
        var sys = systeme
        if estIdentification(question) {
            sys += "\n\nATTENTION : cette question porte sur une identification. " +
                   "La règle de sûreté ci-dessus s'applique impérativement.\n"
        }
        let tete = encart.isEmpty ? "" : "\(encart)\n\n\(String(repeating: "=", count: 60))\n\n"
        let user = """
        \(tete)EXTRAITS DISPONIBLES

        \(formaterExtraits(hits))

        \(String(repeating: "=", count: 60))

        QUESTION : \(question)

        Réponds uniquement à partir des extraits ci-dessus, en citant \
        [identifiant p.numéro] après chaque affirmation.
        """
        return (sys, user)
    }
}
