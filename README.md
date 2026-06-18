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
```

The CLI (`init` / `save` / `search` / `show`) is the next milestone. For now the Python API works end to end:

```python
from akashic_codex import db, ingest
from akashic_codex.search import search

db.init_db()                 # create the database
conn = db.connect()

ingest.save_conversation(conn, open("chat.txt").read(), title="My chat", source="claude")
for hit in search(conn, "the database decision"):
    print(hit["id"], hit["title"])
```

## Status

Active development. The core is built and tested: storage, embeddings, hybrid search (SQLite FTS5 keyword + `sqlite-vec` semantic, merged with reciprocal rank fusion), and the ingest pipeline (`save_conversation`: summarize, tag, embed, store). CI runs ruff and pytest on every change. Next up is the CLI, then a REST API and an MCP server. See `docs/DESIGN.md` for the architecture and full roadmap.

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
