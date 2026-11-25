# living-library
Local, model-agnostic memory store for AI conversations (SQLite + FTS5 + sqlite-vec hybrid search); CLI, REST API and MCP server. Status: active. Python package is still `akashic_codex` (GitHub repo renamed Gardner-Programs/living-library).
Use when: saving, searching or retrieving past conversations across models; working on the memory store, its MCP server, or embeddings.

## Run
- MCP server `akashic-codex` (local scope, this folder only; other windows use tools/command-tower): `AKASHIC_DB_PATH=~/.akashic/akashic.db .venv/bin/python -m akashic_codex.cli serve_mcp`
- CLI: `.venv/bin/python -m akashic_codex.cli init|save|search|show|reembed|retitle|serve_api|serve_mcp`
- REST: `... cli serve_api --reload` (127.0.0.1:8000)
- Tests: `.venv/bin/python -m pytest -q`; lint: `ruff check`

## Layout
- src/akashic_codex/ - package (db.py is the only SQLite-specific code; cli.py entry point; core service, API, MCP)
- tests/ - pytest; schema.sql - DB schema; examples/ - sample transcripts
- docs/DESIGN.md - architecture and roadmap; HANDOFF.md - decisions already made (do not relitigate)
- data/ - repo-local DB (dev only); .env.example - config template (copy to .env)
- .venv/ - Python venv

## Gotchas
- One fixed embedding model per store (default all-MiniLM-L6-v2, 384 dims); changing `AKASHIC_EMBEDDING_MODEL` requires `reembed`.
- Real DB is ~/.akashic/akashic.db (private; not the repo's data/). The MCP venv path above is hardcoded in ~/.claude.json; recreate the venv and update it if the folder moves.
- `AKASHIC_TITLER`: heuristic (default) or ollama:<model>.
- If the akashic-codex MCP fails to connect, check the venv path and DB path first.
- Sibling worktree: ../living-library-fleet-49 (separate task).

## See also
- README.md - long human/GitHub page (setup, hook, API)
- docs/DESIGN.md, HANDOFF.md
