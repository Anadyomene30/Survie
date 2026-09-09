#!/usr/bin/env bash
# Prepare une archive autonome pour cle USB ou disque externe :
# code, corpus, index, modeles, roues Python deja compilees, et une version
# imprimable des fiches vitales.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$RACINE/bundle"
cd "$RACINE"

rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/survie" "$BUNDLE/roues"

echo "== Code, corpus et index =="
cp -R src config connaissances scripts pyproject.toml README.md "$BUNDLE/survie/"
[ -d index ]   && cp -R index   "$BUNDLE/survie/"
[ -d modeles ] && cp -R modeles "$BUNDLE/survie/"

echo "== Roues Python (reinstallation sans reseau ni compilateur) =="
# Les roues compilees sont liees a l'architecture : celles-ci ne valent que
# pour une machine de meme architecture (arm64 pour Apple Silicon).
pip download --quiet --dest "$BUNDLE/roues" \
  numpy llama-cpp-python fastapi uvicorn 2>/dev/null \
  || echo "  (roues non recuperees : reinstallation avec reseau necessaire)"

echo "== Fiches vitales, version imprimable =="
IMPRIMABLE="$BUNDLE/fiches-vitales.md"
{
  echo "# Fiches vitales — version papier"
  echo
  echo "Dernier recours : si la machine ne demarre plus, ces pages suffisent."
  echo "Imprimer et conserver avec les documents importants."
  echo
} > "$IMPRIMABLE"

PYTHONPATH="$RACINE/src" python3 - >> "$IMPRIMABLE" <<'PYEOF'
from survie.config import DOSSIER_CONNAISSANCES
from survie.urgence.protocoles import fiches_vitales

for fiche in fiches_vitales(DOSSIER_CONNAISSANCES):
    print(f"\n\n---\n\n# {fiche.titre}\n")
    print(f"*{fiche.identifiant} — relu le {fiche.verifie_le}*\n")
    print(fiche.corps)
PYEOF

cat > "$BUNDLE/LISEZ-MOI.txt" <<'TXT'
SURVIE — copie autonome

Cette cle contient tout le necessaire pour fonctionner sans internet.

1. Copier le dossier survie/ sur la machine.
2. Installer sans reseau :
      cd survie
      python3 -m venv .venv && source .venv/bin/activate
      pip install --no-index --find-links ../roues numpy llama-cpp-python
      pip install -e .
3. Verifier :  survie etat
4. Utiliser :  survie demande "comment desinfecter l'eau"

Si rien de tout cela ne fonctionne : ouvrir fiches-vitales.md dans
n'importe quel editeur de texte, ou lire sa version imprimee.
TXT

echo
echo "Bundle pret : $BUNDLE"
du -sh "$BUNDLE"
