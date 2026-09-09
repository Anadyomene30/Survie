# SURVIE — pipeline hors-ligne
PY := uv run --

.PHONY: help setup corpus-check fetch ingest db ask eval test lint clean

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

setup:  ## Installe les dépendances (Python + extraction + MLX sur Mac)
	uv sync --extra extract --extra mlx --extra dev

corpus-check:  ## Vérifie que toutes les URLs du manifeste répondent (à lancer AVANT fetch)
	$(PY) python -m ingest.fetch --check-only

fetch:  ## Télécharge les sources libres de droit -> corpus/public/ + corpus/sources.lock
	$(PY) python -m ingest.fetch

zim:  ## Aperçu de la sélection d'une archive Kiwix : make zim Z=corpus/public/wikipedia_fr.zim
	$(PY) python -m ingest.zim "$(Z)"

ingest:  ## Extraction + OCR + découpage -> build/chunks.jsonl (+ vignettes de pages)
	$(PY) python -m ingest.extract
	$(PY) python -m ingest.chunk

db:  ## Vectorisation + construction de l'index -> build/survie.db
	$(PY) python -m ingest.embed
	$(PY) python -m ingest.build_db

ask:  ## Question ponctuelle : make ask Q="comment traiter une hypothermie"
	$(PY) survie ask "$(Q)"

eval:  ## Lance le jeu d'évaluation (citations, refus, sécurité identification)
	$(PY) survie eval eval/golden.yaml

test:  ## Tests unitaires (aucune dépendance lourde, aucun réseau)
	$(PY) pytest -q

lint:
	$(PY) ruff check . && $(PY) ruff format --check .

clean:
	rm -rf build/ .pytest_cache .ruff_cache
