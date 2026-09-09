#!/usr/bin/env bash
# Telecharge les modeles. A LANCER TANT QUE VOUS AVEZ DU RESEAU.
# Une fois les fichiers presents, plus rien n'a besoin d'internet.
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELES="$RACINE/modeles"
PROFIL="${1:-auto}"

mkdir -p "$MODELES"

# Detection du profil d'apres la memoire (memoire unifiee sur Apple Silicon).
if [ "$PROFIL" = "auto" ]; then
  if RAM=$(sysctl -n hw.memsize 2>/dev/null); then
    RAM_GO=$((RAM / 1024 / 1024 / 1024))
  else
    RAM_GO=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null || echo 16)
  fi
  if   [ "$RAM_GO" -ge 28 ]; then PROFIL=confort
  elif [ "$RAM_GO" -ge 12 ]; then PROFIL=standard
  else                            PROFIL=leger
  fi
  echo "Memoire detectee : ${RAM_GO} Go -> profil $PROFIL"
fi

case "$PROFIL" in
  leger)
    DEPOT="Qwen/Qwen3-1.7B-GGUF";                              FICHIER="Qwen3-1.7B-Q4_K_M.gguf" ;;
  standard)
    DEPOT="unsloth/Qwen3-4B-Instruct-2507-GGUF";               FICHIER="Qwen3-4B-Instruct-2507-Q4_K_M.gguf" ;;
  confort)
    DEPOT="unsloth/Mistral-Small-3.2-24B-Instruct-2506-GGUF";  FICHIER="Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf" ;;
  *)
    echo "Profil inconnu : $PROFIL (attendu : leger, standard, confort)" >&2; exit 1 ;;
esac

EMB_DEPOT="bartowski/granite-embedding-107m-multilingual-GGUF"
EMB_FICHIER="granite-embedding-107m-multilingual-f16.gguf"

telecharger() {
  local depot="$1" fichier="$2" cible="$MODELES/$2"
  if [ -f "$cible" ]; then
    echo "Deja present : $fichier"
    return
  fi
  echo "Telechargement de $fichier ..."
  # -C - reprend un telechargement interrompu : utile sur une liaison instable.
  curl -fL -C - --retry 5 --retry-delay 4 \
       -o "$cible.partiel" \
       "https://huggingface.co/$depot/resolve/main/$fichier"
  mv "$cible.partiel" "$cible"
}

telecharger "$EMB_DEPOT" "$EMB_FICHIER"
telecharger "$DEPOT" "$FICHIER"

echo
echo "Modeles installes dans $MODELES"
du -h "$MODELES"/*.gguf
echo
echo "Etape suivante, hors ligne desormais possible :"
echo "  survie index"
