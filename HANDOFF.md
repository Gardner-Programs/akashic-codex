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

Scaffold only. Structure, `schema.sql`, README, `docs/DESIGN.md`, and stubbed modules are committed (first commit done). Package imports cleanly. Every stub raises `NotImplementedError` with TODOs describing what to build. The `data/*.db` file is gitignored.

## Files

`schema.sql`, `src/akashic_codex/{db,embeddings,ingest,search,cli}.py`, `tests/test_smoke.py`, `docs/DESIGN.md` (full 9-step roadmap).

## Next step

The user wants to write the implementation themselves with help as needed. Start at roadmap step 1: implement `db.connect` and `db.init_db`, then prove a save/read round trip with a test. Do NOT dump full implementations unprompted; guide and assist.

## User preferences

Concise and direct. No em dashes or obvious AI formatting.
