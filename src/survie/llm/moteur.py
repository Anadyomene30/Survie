"""Chargement du LLM local via llama.cpp.

L'absence de modele n'est pas une erreur : le systeme bascule alors en mode
recherche documentaire, qui reste utile. C'est le deuxieme des quatre niveaux
de degradation prevus.
"""

from __future__ import annotations

from pathlib import Path

from survie.llm.prompts import SYSTEME


class LLMIndisponible(RuntimeError):
    """llama-cpp-python absent, ou fichier de modele manquant."""


class Moteur:
    def __init__(self, chemin_modele: Path, contexte: int = 8192) -> None:
        if not chemin_modele.exists():
            raise LLMIndisponible(
                f"Modele absent : {chemin_modele}\n"
                "Lancez scripts/telecharger_modeles.sh tant que vous avez du reseau."
            )
        try:
            from llama_cpp import Llama
        except ImportError as erreur:
            raise LLMIndisponible(
                "llama-cpp-python n'est pas installe. Sur Apple Silicon :\n"
                '  CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python'
            ) from erreur

        self._modele = Llama(
            model_path=str(chemin_modele),
            n_ctx=contexte,
            n_gpu_layers=-1,   # tout sur le GPU Metal quand il est disponible
            verbose=False,
        )

    def repondre(self, invite: str, max_tokens: int = 700) -> str:
        reponse = self._modele.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEME},
                {"role": "user", "content": invite},
            ],
            # Temperature basse : on veut une restitution fidele des extraits,
            # pas de la variete.
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return reponse["choices"][0]["message"]["content"].strip()
