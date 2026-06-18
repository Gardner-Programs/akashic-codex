# AkashicCodex: Handoff

Paste this to a fresh Claude instance to continue the project.

## What this is

AkashicCodex is a local, model-agnostic memory store for AI conversations. The point: conversation history lives in a database the user owns, not inside any one model, so the user can switch between Claude, Gemini, a local Ollama model, etc., and keep their context. The memory IS the database.

## Decisions already made (don't relitigate)

- **Name:** AkashicCodex (repo folder `akashic-codex`, package `akashic_codex`).
- **Database:** SQLite, single local file. Chosen for local-first ownership, privacy, zero server, single-user. All SQLite code is isolated in `db.py` so a future Postgres + pgvector move is contained.
- **Semantic search:** via the `sqlite-vec` extension.
- **Embeddings:** ONE fixed local model (`all-MiniLM-L6-v2`, 384 dims, sentence-transformers). Vectors from different models are not comparable, so this never changes mid-store. This is the project's core rule.
- **Language:** Python throughout.
- **This is a portfolio piece** meant to prove SQL + Python skill, and a tool the user actually uses daily.

## Architecture

Layers: model (client, generation only) -> interface (CLI now, then REST, then MCP) -> core service (ingest/embed/search) -> `db.py` (only SQLite-specific code) -> SQLite + sqlite-vec.

Retrieval is two-tier and hybrid: search ranks lightweight summaries first (keyword via FTS5 + semantic via vectors), then loads the full transcript only on a confirmed match. Summaries, tags, and embeddings are generated ONCE at ingest, never at query time.

## Current state

Roadmap steps 1-5 done and tested: core storage, FTS5 keyword search, embeddings + semantic vector search, hybrid search (reciprocal rank fusion), and the ingest pipeline (`save_conversation` end to end). `summarize`/`suggest_tags` are simple placeholders behind a seam for a future local model. Public repo on GitHub (`Gardner-Programs/akashic-codex`) with CI (ruff + pytest) and an issue/PR workflow. The `data/*.db` file is gitignored.

## Files

`schema.sql`, `src/akashic_codex/{db,embeddings,ingest,search,cli}.py`, `tests/{test_smoke,conftest}.py`, `docs/DESIGN.md` (full 9-step roadmap), `.github/workflows/ci.yml`.

## Next step

Step 6: the CLI. Wire `init` / `save` / `search` / `show` into a command-line entry point (`cli.py`) over the existing core. The user writes the implementation themselves; do NOT dump full implementations unprompted, guide and review.

## User preferences

Concise and direct. No em dashes or obvious AI formatting.
