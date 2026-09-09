"""Interface web locale.

Elle sert un cas concret : quand une seule machine porte la base, les autres
personnes doivent pouvoir la consulter depuis un telephone sur le meme reseau
(--hote 0.0.0.0). La page est autonome, sans CDN ni police distante : elle
doit s'afficher sans le moindre acces reseau sortant.
"""

from __future__ import annotations

import sys
from pathlib import Path

from survie import config as configuration

STATIQUE = Path(__file__).parent / "static"


def creer_application(nom_profil: str | None = None):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse, JSONResponse

    from survie.cli import _charger_moteur
    from survie.recherche.reponse import repondre

    config = configuration.charger(nom_profil)
    moteur_recherche, llm = _charger_moteur(config, avec_llm=True)

    application = FastAPI(title="Survie", docs_url=None, redoc_url=None)

    @application.get("/")
    def page():
        return FileResponse(STATIQUE / "index.html")

    @application.get("/api/demande")
    def demande(q: str, sources_seules: bool = False):
        if not q.strip():
            return JSONResponse({"erreur": "question vide"}, status_code=400)
        reponse = repondre(
            q,
            moteur_recherche,
            llm=None if sources_seules else llm,
            nombre_extraits=config.extraits,
            seuil=config.seuil_pertinence,
        )
        return {
            "mode": reponse.mode,
            "texte": reponse.texte,
            "fiches": reponse.fiches_citees,
            "extraits": [
                {
                    "reference": e.reference,
                    "titre": e.titre,
                    "texte": e.texte,
                    "criticite": e.criticite,
                }
                for e in reponse.extraits
            ],
        }

    @application.get("/api/etat")
    def etat():
        return {
            "profil": config.profil.nom,
            "llm": llm is not None,
            "fragments": len(moteur_recherche.index.fragments),
            "vectoriel": moteur_recherche.index.a_vecteurs,
        }

    return application


def lancer(nom_profil: str | None, hote: str, port: int) -> int:
    try:
        import uvicorn
    except ImportError:
        print(
            "Interface web indisponible : pip install fastapi uvicorn\n"
            "La ligne de commande reste utilisable : survie demande ...",
            file=sys.stderr,
        )
        return 1

    application = creer_application(nom_profil)
    if hote == "0.0.0.0":
        print(f"Accessible sur le reseau local : http://<ip-de-ce-mac>:{port}")
    uvicorn.run(application, host=hote, port=port, log_level="warning")
    return 0
