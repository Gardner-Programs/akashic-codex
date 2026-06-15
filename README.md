# AkashicCodex

A local, model-agnostic memory store for AI conversations.

The idea: your conversation history shouldn't live inside any one AI. AkashicCodex keeps it in a database you own, on your own machine, so you can switch freely between Claude, Gemini, a local Ollama model, or whatever comes next, and your context follows you. When one model runs out of usage, you switch to another and the memory is still there, because the memory *is* the database, not the model.

## How it works

Conversations are stored with a title, auto-generated topic tags, and a short summary alongside the full transcript. Search happens in two tiers: first it ranks the lightweight summaries (fast and cheap), then it loads the full transcript only for a match (expensive, done rarely). Search is hybrid: keyword search via SQLite FTS5 for precision, plus semantic vector search via `sqlite-vec` so it finds the right conversation even when you phrase things differently than you did before.

Any model talks to the same simple interface (save, search, get). No model-specific logic lives in the store, which is what makes models swappable.

## Stack

SQLite (single local file you own) + `sqlite-vec` for semantic search + a fixed local embedding model so vectors stay comparable and vendor-independent. Python throughout. The database layer is isolated in one module so migrating to Postgres + pgvector later, if ever needed, is a contained change.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python -m akashic_codex.cli init                       # create the database
python -m akashic_codex.cli save chat.txt --source claude
python -m akashic_codex.cli search "the database decision"
python -m akashic_codex.cli show 1
```

## Status

Scaffold stage. Structure, schema, and stubs are in place; the implementation is being built out module by module. See `docs/DESIGN.md` for the architecture and the build roadmap.

## Layout

```
schema.sql                 database schema
src/akashic_codex/
  db.py                    all SQLite-specific code (swap point for Postgres)
  embeddings.py            single fixed embedding model
  ingest.py                save pipeline: summarize, tag, embed, store
  search.py                two-tier hybrid retrieval
  cli.py                   command-line entry point
tests/                     pytest
docs/DESIGN.md             architecture and roadmap
```
