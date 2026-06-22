# AkashicCodex: Handoff

Paste this to a fresh Claude instance to continue the project.

## What this is

AkashicCodex is a local, model-agnostic memory store for AI conversations. The point: conversation history lives in a database the user owns, not inside any one model, so the user can switch between Claude, Gemini, a local Ollama model, etc., and keep their context. The memory IS the database.

## Decisions already made (don't relitigate)

- **Name:** AkashicCodex (repo folder `akashic-codex`, package `akashic_codex`).
- **Database:** SQLite, single local file. Chosen for local-first ownership, privacy, zero server, single-user. All SQLite code is isolated in `db.py` so a future Postgres + pgvector move is contained.
- **Semantic search:** via the `sqlite-vec` extension.
- **Embeddings:** ONE fixed local model (`all-MiniLM-L6-v2`, 384 dims, sentence-transformers). Vectors from different models are not comparable, so this never changes mid-store. The user is free to choose a different model, but it is fixed for a store's lifetime (changing it means re-embedding everything). This is the project's core rule.
- **Language:** Python throughout.
- **This is a portfolio piece** meant to prove SQL + Python skill, and a tool the user actually uses daily. Pinned on the user's GitHub profile.

## Architecture

Layers: model (client, generation only) -> interface (CLI and REST done, MCP next) -> core service (ingest/embed/search) -> `db.py` (only SQLite-specific code) -> SQLite + sqlite-vec.

Retrieval is two-tier and hybrid: search ranks lightweight summaries first (keyword via FTS5 + semantic via vectors), then loads the full transcript only on a confirmed match. Summaries, tags, and embeddings are generated ONCE at ingest, never at query time.

## Current state

Roadmap steps 1-7 done and tested: core storage, FTS5 keyword search, embeddings + semantic vector search, hybrid search (reciprocal rank fusion), the ingest pipeline (`save_conversation`), the CLI (`init` / `save` / `search` / `show` / `serve`), and the REST API (FastAPI: `POST /conversations`, `GET /search`, `GET /conversations/{id}`, interactive `/docs`). `summarize`/`suggest_tags` are still simple placeholders behind a seam for a future local model. Public repo (`Gardner-Programs/akashic-codex`) with CI (ruff check + ruff format --check + pytest), an issue/PR workflow, and a polished README (CI badge, checkbox roadmap, `/docs` screenshot). 24 tests pass. The `data/*.db` file is gitignored.

## Files

`schema.sql`, `src/akashic_codex/{db,embeddings,ingest,search,cli,api}.py`, `tests/{test_smoke,test_cli,test_api,conftest}.py`, `docs/DESIGN.md` (full 9-step roadmap + deferred-decision notes), `.github/workflows/ci.yml`.

## Testing approach

Tests mock the embedder for speed and to stay offline: a `mock_embed` fixture in `conftest.py` patches `embed` at its usage sites (`ingest.embed`, `search.embed`, the from-import binding, not `embeddings.embed`) with a deterministic 384-dim vector, wired into the `cli_db` (test_cli) and `client` (test_api) isolation fixtures. Three semantic tests in `test_smoke.py` keep the REAL model as integration coverage; never mock those. CLI tests drive `main()` via patched `sys.argv`; API tests use FastAPI `TestClient` + `dependency_overrides` on `get_conn`.

## Deferred decisions (logged in DESIGN.md, build later)

- **Embedder identity / `store_meta`:** the store does not record which embedder built its vectors. This is the prerequisite (step zero) for the re-embed / model-swap feature. Add a small `store_meta` table via generic `db.get_meta`/`set_meta` helpers, before any store the user cares about exists.
- **Structured messages:** conversations are an opaque `full_log` blob; a `messages` table (role + per-turn `model`) would support swapping models mid-conversation and precise context re-injection once a chat exceeds a model's window. Keep `full_log` as the source of truth. Trigger: import adapters or a render/chat UI.

## Next step

Step 8: the MCP server. Expose `search_memory` and `get_conversation` as MCP tools over the existing core, so any MCP-capable model can use the store directly. Same pattern as the CLI and API: a thin interface over the core, no storage/search logic in the interface layer. The user writes the implementation themselves; do NOT dump full implementations unprompted, guide and review.

## Conventions

- **Commits and PRs carry NO Claude attribution** (this is a portfolio piece): authored as the user, no `Co-Authored-By: Claude`, no "Generated with Claude Code" footer. Ship via feature branch -> PR -> CI green -> squash merge.
- Ruff: `select = E,W,F,I,UP,B,SIM`, line length 100. Bugbear `extend-immutable-calls` allows FastAPI `Depends`/`Query` in argument defaults. CI runs both `ruff check` and `ruff format --check`. A narrow `filterwarnings` silences Starlette's third-party httpx2 deprecation.
- Tests: descriptive names that read as the spec, no per-test docstrings (module + fixture docstrings only).
- Source docstrings: numpy-style on the core (`db`/`ingest`/`search`/`embeddings`); light one-line docstrings on thin interface handlers (`cli` commands, `api` endpoints).

## User preferences

Concise and direct. No em dashes or obvious AI formatting. The user writes the implementation themselves; guide and review, do not dump full code unprompted.
