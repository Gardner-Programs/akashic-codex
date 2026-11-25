#!/usr/bin/env bash
#
# Reproducible terminal demo used to generate docs/images/demo.gif.
#
# Record and convert (from the repo root, with the venv set up):
#   asciinema rec --overwrite --command "docs/demo.sh" demo.cast
#   agg --speed 1.3 demo.cast docs/images/demo.gif
#   rm demo.cast
#
# It runs against a throwaway database, so it never touches your real store.

set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate

# Quiet third-party noise (model download checks, tokenizer + progress bars)
# so the recording shows only the tool's own output. The model is loaded from
# the local cache, so HF_HUB_OFFLINE is safe here.
export HF_HUB_OFFLINE=1
export TRANSFORMERS_VERBOSITY=error
export TQDM_DISABLE=1
export TOKENIZERS_PARALLELISM=false

# Throwaway, repeatable store.
export LIVING_LIBRARY_DB_PATH=/tmp/living-library-demo.db
rm -f "$LIVING_LIBRARY_DB_PATH"

# Print a command with a typed-out effect, run it, then pause.
run() {
    printf '$ '
    local s="$1" i
    for ((i = 0; i < ${#s}; i++)); do
        printf '%s' "${s:i:1}"
        sleep 0.025
    done
    printf '\n'
    sleep 0.4
    eval "$s"
    echo
    sleep 1.3
}

clear || true
sleep 0.6
run 'python -m living_library.cli init'
run 'python -m living_library.cli save examples/sqlite_decision.txt --title "Why we chose SQLite" --source claude'
run 'python -m living_library.cli save examples/semantic_search.txt --title "How semantic search works" --source gemini'
run 'python -m living_library.cli save examples/weeknight_pasta.txt --title "Weeknight pasta" --source ollama'
run 'python -m living_library.cli search "what database did we pick for local storage"'
run 'python -m living_library.cli show 1'
sleep 2.5
