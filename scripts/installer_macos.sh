#!/usr/bin/env bash
# Installation complete sur macOS Apple Silicon (M1/M2/M3/M4).
# Necessite du reseau : a lancer avant la crise, pas pendant.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RACINE"

echo "== 1/4 Outils de compilation =="
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Les Command Line Tools sont requis pour compiler llama-cpp-python."
  echo "Lancez : xcode-select --install    puis relancez ce script."
  exit 1
fi

echo "== 2/4 Environnement Python =="
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --quiet --upgrade pip

echo "== 3/4 Dependances (llama.cpp compile avec Metal) =="
pip install --quiet -e .
# GGML_METAL : l'inference s'execute sur le GPU integre. Sans cette option,
# tout tourne sur le CPU et le modele est plusieurs fois plus lent.
CMAKE_ARGS="-DGGML_METAL=on" pip install --quiet llama-cpp-python
pip install --quiet fastapi uvicorn

echo "== 4/4 Modeles et index =="
bash scripts/telecharger_modeles.sh "${1:-auto}"
survie index

echo
echo "Installation terminee. Verifiez avec :"
echo "  source .venv/bin/activate"
echo "  survie etat"
echo
echo "Vous pouvez maintenant couper le reseau : tout fonctionne hors ligne."
