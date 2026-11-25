# living-library
Local, model-agnostic memory store for AI conversations (SQLite + FTS5 + sqlite-vec hybrid search); CLI, REST API and MCP server. Status: active. Python package is still `living_library` (GitHub repo renamed Gardner-Programs/living-library).
Use when: saving, searching or retrieving past conversations across models; working on the memory store, its MCP server, or embeddings.

## Run
- MCP server `living-library` (local scope, this folder only; other windows use tools/command-tower): `LIVING_LIBRARY_DB_PATH=~/.akashic/akashic.db .venv/bin/python -m living_library.cli serve_mcp`
- CLI: `.venv/bin/python -m living_library.cli init|save|search|show|reembed|retitle|serve_api|serve_mcp`
- REST: `... cli serve_api --reload` (127.0.0.1:8000)
- Tests: `.venv/bin/python -m pytest -q`; lint: `ruff check`

## Layout
- src/living_library/ - package (db.py is the only SQLite-specific code; cli.py entry point; core service, API, MCP)
- tests/ - pytest; schema.sql - DB schema; examples/ - sample transcripts
- docs/DESIGN.md - architecture and roadmap; HANDOFF.md - decisions already made (do not relitigate)
- data/ - repo-local DB (dev only); .env.example - config template (copy to .env)
- .venv/ - Python venv

## Gotchas
- One fixed embedding model per store (default all-MiniLM-L6-v2, 384 dims); changing `LIVING_LIBRARY_EMBEDDING_MODEL` requires `reembed`.
- Real DB is ~/.akashic/akashic.db (private; not the repo's data/). The MCP venv path above is hardcoded in ~/.claude.json; recreate the venv and update it if the folder moves.
- `LIVING_LIBRARY_TITLER`: heuristic (default) or ollama:<model>.
- If the living-library MCP fails to connect, check the venv path and DB path first.
- Renamed from akashic-codex (#49). The `akashic_codex` package is a shim (same modules) and
  `AKASHIC_*` env vars still work, so old hooks/configs don't break; use the new names in new code.
  DB files keep the `akashic.db` name on purpose.

## See also
- README.md - long human/GitHub page (setup, hook, API)
- docs/DESIGN.md, HANDOFF.md
