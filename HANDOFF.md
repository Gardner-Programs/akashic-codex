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

Layers: model (client, generation only) -> interface (CLI, REST, and MCP done) -> core service (ingest/embed/search) -> `db.py` (only SQLite-specific code) -> SQLite + sqlite-vec.

Retrieval is two-tier and hybrid: search ranks lightweight summaries first (keyword via FTS5 + semantic via vectors), then loads the full transcript only on a confirmed match. Summaries, tags, and embeddings are generated ONCE at ingest, never at query time.

## Current state

Roadmap steps 1-9 done and tested, plus two quality-of-life features shipped since. Core: storage, FTS5 keyword search, embeddings + semantic vector search, hybrid search (reciprocal rank fusion), the ingest pipeline (`save_conversation`), the CLI (`init` / `save` / `search` / `show` / `serve_api` / `serve_mcp` / `claude-hook`), the REST API (FastAPI: `POST /conversations`, `GET /search`, `GET /conversations/{id}`, interactive `/docs`), and the MCP server (MCPServer over stdio, read-only tools `search_memory` and `get_conversation`).

Shipped since the numbered roadmap:
- **Embedder identity + search guard (PR #16):** a generic `store_meta(key, value)` table with `db.get_meta`/`set_meta` (upsert via `ON CONFLICT`). `ingest.ensure_embedder_identity` stamps `embedding_model` + `embedding_dim` once at first ingest (dimension taken from the real vector; `db.py` never imports `embeddings`, staying decoupled). `search.assert_active_embedder` raises `RuntimeError` if the active model differs from the stored one, lenient (no-op) when unstamped.
- **Real pluggable summarizer (PR #22):** replaced the `full_log[:200]` placeholder. `src/akashic_codex/summarizers.py` exposes an `AKASHIC_SUMMARIZER` seam. Default `extractive`: sentence-split, embed each, rank by cosine similarity to the centroid of all sentence vectors, select within a ~300-char budget in document order (offline, no new deps). Optional `ollama:<model>`: abstractive via a local Ollama server over stdlib `urllib`, fail-loud (`RuntimeError`) on error, `AKASHIC_OLLAMA_HOST` overrides the endpoint. Each conversation records its `summarizer` backend in a new column (the summarizer may vary between saves, unlike the fixed embedder). `suggest_tags` is still a placeholder seam.
- **Auto-save via a Claude Code hook (#19):** live sessions are captured automatically instead of via manual `cli save`. Schema gained nullable `session_id` (UNIQUE) + `thread_id` on `conversations`, plus AFTER UPDATE/DELETE FTS triggers so the keyword index tracks in-place edits. `db.upsert_conversation` upserts by `session_id` (`ON CONFLICT ... DO UPDATE ... RETURNING id`); `db.delete_vector` lets a fresh embedding replace the old one on update; `ingest.save_session` is the session-keyed sibling of `save_conversation` (upsert + replace-vector). Capture is quarantined in `adapters.py`: `claude_transcript_to_log` flattens Claude Code's JSONL transcript into a `full_log` (keeps `user`/`assistant` text, drops thinking/tool/noise). The `claude-hook` CLI command reads the hook's stdin JSON (`session_id` + `transcript_path`), calls the adapter, and upserts with `source="claude-code"`. Platform-specific parsing lives ONLY in adapters (Gemini/ChatGPT are #21); the store and `save_session` stay format-agnostic. `thread_id` rides on the row but nothing sets it yet (see linking follow-up). README documents enabling the hook.

**Re-embed command (#18):** `reembed.py` + `cli reembed [--yes]`. Embeds every summary with the active model outside any transaction (so the live hook is not blocked), then under `BEGIN IMMEDIATE` embeds anything that changed mid-run and calls `db.replace_all_vectors`, which drops and recreates `summary_vectors` at the new dimension and upserts the identity in `store_meta`, all in one transaction. `ensure_embedder_identity` now also refuses a model mismatch on write, and runs before the row is inserted so a refused save writes nothing.

**Titles + retitle:** `titlers.py` (`AKASHIC_TITLER`: `heuristic` default, `ollama:<model>` with heuristic fallback on failure). `save_conversation`/`save_session` title from the summary when none is given; `cli retitle [--all] [--yes]` backs up then regenerates. The live hook runs with `AKASHIC_TITLER=ollama:gemma4:12b`.

**Resummarize + hook fallback (#33):** `cli resummarize [--empty|--all] [--yes]` backs up the database, regenerates empty summaries by default or every summary with `--all`, and replaces matching vectors. Claude hook summarization errors fall back to the offline extractive backend so the raw transcript is still saved; manual saves remain fail-loud.

80 tests, ruff clean. Public repo (`Gardner-Programs/akashic-codex`) with CI (ruff check + ruff format --check + pytest), an issue/PR workflow, and a polished README. `data/*.db` is gitignored.

## Files

`schema.sql`, `src/akashic_codex/{db,embeddings,ingest,search,reembed,resummarize,summarizers,adapters,cli,api,mcp_server}.py`, `tests/{test_smoke,test_cli,test_api,test_mcp,test_reembed,test_resummarize,conftest}.py`, `docs/DESIGN.md` (full 9-step roadmap + deferred-decision notes), `.github/workflows/ci.yml`.

## Commands

- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`, then `cp .env.example .env`.
- Tests: `pytest -q`. Lint: `ruff check src tests` and `ruff format --check src tests`.
- CLI: `python -m akashic_codex.cli {init | save <file> --title "..." | search <query> | show <id> | reembed [--yes] | retitle [--all] [--yes] | resummarize [--empty|--all] [--yes] | serve_api | serve_mcp | claude-hook}`. (`claude-hook` reads a Claude Code Stop-hook payload on stdin; not run by hand.)
- Config (env vars, see `.env.example`): `AKASHIC_DB_PATH`, `AKASHIC_EMBEDDING_MODEL` (fixed per store), `AKASHIC_SUMMARIZER` (`extractive` | `ollama:<model>`), `AKASHIC_OLLAMA_HOST`.

## Testing approach

A `mock_embed` fixture in `conftest.py` patches `embed` at its usage sites (`ingest.embed`, `search.embed`, not `embeddings.embed`) with a deterministic 384-dim vector, wired into the `cli_db` (test_cli) and `client` (test_api) isolation fixtures. `test_smoke.py` uses the REAL model as integration coverage (including the extractive summarizer). The Ollama backend is tested offline by monkeypatching `urllib.request.urlopen` (a `BytesIO` holding fake JSON for the success case, a function raising `URLError` for fail-loud), so CI never needs a server. Dispatch tests monkeypatch the module-level `summarizers.SUMMARIZER`. CLI tests drive `main()` via patched `sys.argv`; API tests use FastAPI `TestClient` + `dependency_overrides` on `get_conn`.

## Deferred decisions (logged in DESIGN.md)

- **Embedder identity / `store_meta`: DONE (PR #16).** Re-embed (#18) built on it.
- **Structured messages:** conversations are an opaque `full_log` blob; a `messages` table (role + per-turn `model`) would support swapping models mid-conversation and precise context re-injection once a chat exceeds a model's window. Keep `full_log` as the source of truth. Trigger: import adapters or a render/chat UI. Backlog #20.
- **Schema versioning and migrations (#25): DONE.** `init_db()` tracks `schema_version` in `store_meta` and applies ordered forward-only migrations from `src/akashic_codex/migrations.py`. Unversioned stores are classified by their existing conversation columns, and invalid/newer versions fail clearly.

## Next step

**#19 auto-save is DONE** (built this session; see the auto-save bullet under Current state). The store now captures live Claude Code sessions automatically. Follow-ups that fell out of the work:

- **Thread linking (verbatim first):** `thread_id` exists on the row but nothing sets it. This is the cross-model continuity goal (run out of usage on Claude, continue on Gemini, come back to Claude with no gap). Agreed design: when a new session's transcript *contains* an existing conversation's text, auto-link them under one `thread_id`. Do **verbatim** overlap detection first (strong textual proof, safe to auto-link silently); leave semantic/suggested linking as a later, lower-confidence tier. Its own issue; do not fold into the core.
- **Summarizer toggle for auto-save:** the `Stop` hook re-summarizes every turn. Cheap for the default extractive, heavy for Ollama. Add an `each_turn` vs `session_end` policy where the raw `full_log` still upserts every turn but the summary recompute is gated.
- **#25 schema versioning + migrations** (filed this session): `init` cannot alter an existing table; needed before real data accumulates.

**Existing backlog:** #20 structured messages (per-turn role + model), #21 import adapters (Gemini/ChatGPT, siblings to the new Claude adapter in `adapters.py`), #23 summarizer follow-ups (extractive fragments on structured/dialogue text; Ollama needs a soft length cap).

**As of 2026-11-21 Claude drives this repo.** The user handed implementation over; Claude writes the code, tests, and docs and ships via PR. The earlier guide-and-review mode no longer applies unless the user reframes a specific piece as learning.

## Conventions

- **Attribution:** commits through PR #26 carry none. From 2026-11-21 commits end with `Co-Authored-By: Claude` and PR bodies with the Claude Code footer (the user's call). Ship via feature branch (in a worktree) -> PR -> CI green -> squash merge.
- Ruff: `select = E,W,F,I,UP,B,SIM`, line length 100. Bugbear `extend-immutable-calls` allows FastAPI `Depends`/`Query` in argument defaults. CI runs both `ruff check` and `ruff format --check`. A narrow `filterwarnings` silences Starlette's third-party httpx2 deprecation.
- Tests: descriptive names that read as the spec, no per-test docstrings (module + fixture docstrings only).
- Source docstrings: numpy-style on the core (`db`/`ingest`/`search`/`embeddings`); light one-line docstrings on thin interface handlers (`cli` commands, `api` endpoints).

## User preferences

Concise and direct. No em dashes or obvious AI formatting.
