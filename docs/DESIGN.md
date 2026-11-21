# AkashicCodex Design

## Goal

A local memory store for AI conversations that is owned by the user and independent of any model. Switch models freely; the history persists because it lives in the database, not the model.

Three design priorities, in order:

1. **Model-agnostic.** No model-specific logic in the store. Any model is a client.
2. **Local and private.** One file on the user's machine. Shared only when the user chooses.
3. **Useful daily.** Saving is one easy step; search actually finds the right thing.

## Layers

```
   AI model (Claude / Gemini / Ollama / ...)   <- generation only; just a client
                  |
        interface (CLI + REST + MCP)            <- stable contract: save, search, get
                  |
          core service (Python)                 <- ingest, embed, search
                  |
        database layer (db.py)                  <- the ONLY SQLite-specific code
                  |
          SQLite + sqlite-vec  (data/akashic.db)
```

The model does generation only. The service owns storage, summarization-at-ingest, the single fixed embedding model, and search. The model asks "what do I know about X", gets summaries back, and requests the full log only when it wants it. Nothing in the database knows which model asked.

## Data model

`conversations` (id, title, summary, source, created_at, full_log)
`tags` (id, name) and `conversation_tags` (many-to-many)
`conversations_fts` (FTS5 over title + summary) for keyword search
`summary_vectors` (vec0, embedding of the summary) for semantic search

See `schema.sql`.

## Dependency compatibility

Direct dependencies are listed in `requirements.txt` with supported major
version ranges. CI runs weekly as well as on changes, installing the newest
releases within those ranges before linting and running the test suite. This
surfaces upstream compatibility breaks while keeping fresh installs away from
unreviewed major releases.

## Retrieval: two tiers + hybrid

Tier 1, cheap: rank over summaries. Tier 2, expensive: load full_log only on a match.

Hybrid ranking combines keyword search (FTS5, high precision, exact terms) with semantic search (vectors, high recall, catches rephrasings). Merge and de-duplicate into one ranked list. Return lightweight rows from search; never return full_log from the search call.

Tags are suggested once during ingest from frequent transcript keywords. The
offline extractor lowercases words, ignores punctuation and common English
stopwords, then returns up to five keywords with deterministic alphabetical
tie-breaking. Tags complement search metadata and require no model service.

## The embedding rule

Pick ONE embedding model and use it for everything written to and queried against the store. Vectors from different models are not comparable. Use a local model (`all-MiniLM-L6-v2`, 384 dims, via sentence-transformers) to stay vendor-independent. Store the model name so future-you can re-embed if you ever switch. The schema vector dimension must match the model.

Summaries can be regenerated with `cli resummarize [--empty|--all] [--yes]`.
The default scope repairs missing or whitespace-only summaries; `--all` rebuilds
the entire summary corpus. The command writes a database backup first and updates
each corresponding vector with the active embedder. The Claude Code hook uses the
offline extractive summarizer if its configured backend fails, preserving the raw
transcript and recording the fallback provenance. Manual saves remain fail-loud.

The Claude Code auto-save hook also skips transcripts shorter than
`AKASHIC_MIN_SESSION_CHARS` (default `200`). The check runs against the flattened
transcript before summarization or database access; skipped sessions can be saved
on a later turn once the cumulative transcript reaches the threshold. Set the
value to `0` to save every session.

`AKASHIC_SUMMARY_POLICY` defaults to `each_turn`, preserving the original Stop
hook behavior. Set it to `session_end` and register the hook for both `Stop` and
`SessionEnd`: Stop upserts the raw `full_log` while preserving the current title,
summary, and vector, and SessionEnd runs the full derived-data pipeline. The first
qualifying Stop still creates a searchable row. This reduces repeated generation
and embedding work while keeping the transcript current throughout the session.
Session-keyed writes update the existing conversation row first and insert only
for a new session. This avoids consuming an AUTOINCREMENT id on each subsequent
turn without changing the schema or requiring a migration.

Database snapshots written by `reembed`, `retitle`, and `resummarize` are
retained per operation label. `AKASHIC_BACKUP_RETENTION` sets the positive number
to keep, defaulting to 5; each new snapshot prunes older snapshots only for its
own label.

## Two AI backends, two different rules

The system uses AI in two places, and they have opposite swap rules. Do not conflate them.

- **Summarizer (pluggable, optional, local-capable).** Generates a conversation's summary. Summaries are plain text, so any backend is interchangeable: default to a local model (e.g. Ollama) to avoid paid tokens, allow switching via config, and keep generation optional (save raw now, summarize on demand later, e.g. a `/summarize` command). Never hardcode one provider, never make it mandatory. Use the env-var-plus-default config pattern (see `embeddings.py`).
- **Embedder (fixed, swappable only via full re-embed).** Turns a summary into a vector for semantic search. Vectors only have meaning relative to the model that made them, so the whole store must use one model. The config mechanism looks identical to the summarizer (env var + default), but the rule is set-once-before-first-ingest, not change-freely. Switching is allowed only by re-embedding the entire corpus at once (see stretch ideas), which may also require recreating the vector table at the new dimension.

## Why SQLite

Local-first, single file the user owns, zero server to run or secure, single-user so the one-writer limit never bites. The only tradeoff is that vector search comes from the `sqlite-vec` add-on rather than being built in. All SQLite code is isolated in `db.py`, so a future move to Postgres + pgvector is a contained change, not a rewrite.

## Schema Versioning & Migrations

To safely evolve the database schema over time without data loss or breaking existing stores, AkashicCodex records a `schema_version` in `store_meta`. `init_db()` runs forward-only migration steps defined in `src/akashic_codex/migrations.py` that are newer than the store's recorded version, bumping the version in the same transaction as each step. A fresh database gets the current schema directly; an unversioned older store is identified from its existing columns and upgraded from that version. Invalid or newer-than-supported versions fail clearly rather than being overwritten. Migration 1 adds summarizer provenance and migration 2 adds session and thread identifiers.

## Build roadmap

1. **Core storage.** Implement `db.connect` / `db.init_db`. Save and read a conversation. Prove the round trip with a test.
2. **Keyword search.** Wire up FTS5; `search()` returns summary rows for a query.
3. **Embeddings.** Implement `embeddings.embed`; add `sqlite-vec`; store and query summary vectors.
4. **Hybrid search.** Merge keyword + semantic results into one ranked list.
5. **Ingest pipeline.** `summarize` + `suggest_tags`, wired into `save_conversation`.
6. **CLI.** Make init / save / search / show all work end to end.
7. **REST API.** Wrap the core in FastAPI so any client can call it.
8. **MCP server.** Expose `search_memory` and `get_conversation` as MCP tools so any MCP-capable model can use the store directly.
9. **Polish.** Small web view or TUI for demos; README screenshots.

## Stretch ideas

Structured messages instead of an opaque `full_log` blob: a `messages` table (conversation_id, turn_index, role, content, model) so a conversation is a sequence of turns rather than one text document. Motivation is twofold. First, per-turn model attribution: the current conversation-level `source` cannot record that turn 1 was Claude and turn 3 was Gemini, but the project's goal is to let users swap models mid-conversation, so model belongs on the message, not the conversation. Second, context re-injection: the store exists to feed memory back into live conversations once they exceed a model's context window. Summaries are the compact fallback, but ideally you pass back whatever full context a given section needs, and structured turns let you select and re-inject precise spans rather than whole blobs. Keep `full_log` as the source of truth regardless: structure can be derived from the raw log, but a lost raw log cannot be recovered from structure. Deferred; search does not benefit (retrieval stays conversation-level) and nothing in the current roadmap needs it. Natural trigger: the import adapters (which already parse exports into turns) or a render/chat UI.

Re-embedding command for switching embedding models: re-embed every summary with the new model in one shot, replace all vectors, update the stored model name, and (if dimensions change) drop and recreate the vector table. All-or-nothing; never mix two models' vectors. Prerequisite (step zero of this feature): the store must record its own embedder identity (model name + dimension), which it does not yet. Add a small `store_meta` table for this, written via generic `db.get_meta`/`set_meta` helpers so `db.py` stays decoupled from the embeddings layer. This is what lets search verify the active embedder matches the stored vectors and refuse to silently mix maps, and what gives the re-embed command an old model to migrate from. Add it before any store you care about exists; backfilling identity onto existing vectors means assuming the model they were built with. This is what makes the embedder "drag-and-drop" swappable for the user while staying internally consistent. If a paid backend (embedder or summarizer) is configured, estimate and surface token/cost before running so the user opts in knowingly; local backends report zero. Import adapters for Claude/Gemini/ChatGPT export formats. Encryption at rest. A "related conversations" link graph.
