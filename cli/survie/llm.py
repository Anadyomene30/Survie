"""Génération locale. Aucun appel réseau : le modèle est sur le disque."""

from __future__ import annotations

import os
import sys

# Modèles conseillés sur M1 Pro 32 Go, quantifiés 4 bits.
MODELES = {
    "defaut": "mlx-community/Mistral-Small-3.2-24B-Instruct-2506-4bit",
    "rapide": "mlx-community/Qwen3-30B-A3B-Instruct-2507-4bit",
    "batterie": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
}


class LLM:
    name: str

    def generate(self, systeme: str, utilisateur: str, max_tokens: int = 900) -> str:
        raise NotImplementedError


class MLXLLM(LLM):
    def __init__(self, model_id: str):
        from mlx_lm import generate, load  # type: ignore

        self._generate = generate
        self.model, self.tokenizer = load(model_id)
        self.name = model_id

    def generate(self, systeme: str, utilisateur: str, max_tokens: int = 900) -> str:
        messages = [
            {"role": "system", "content": systeme},
            {"role": "user", "content": utilisateur},
        ]
        prompt = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        return self._generate(
            self.model, self.tokenizer, prompt=prompt,
            max_tokens=max_tokens, verbose=False,
        )


class NoLLM(LLM):
    """Mode « extraits seuls » — aucun modèle chargé.

    Ce n'est pas un bouche-trou : c'est un mode de fonctionnement légitime, et
    le plus sûr de tous, puisque rien n'est reformulé. Il rend l'outil utilisable
    sur une machine sans modèle installé, et il sert de référence pour juger la
    recherche indépendamment de la génération.
    """

    name = "aucun (extraits bruts)"

    def generate(self, systeme: str, utilisateur: str, max_tokens: int = 900) -> str:
        return ""


def load(profil: str | None = None) -> LLM:
    profil = profil or os.environ.get("SURVIE_MODELE", "defaut")
    if profil in ("none", "aucun"):
        return NoLLM()
    model_id = MODELES.get(profil, profil)
    try:
        return MLXLLM(model_id)
    except ImportError:
        print("  mlx_lm absent : mode extraits seuls. "
              "Sur Mac : uv sync --extra mlx", file=sys.stderr)
        return NoLLM()
    except Exception as e:
        print(f"  modèle « {model_id} » indisponible ({e}) : mode extraits seuls.",
              file=sys.stderr)
        return NoLLM()
