-- AkashicCodex schema (SQLite)
-- Two-tier retrieval: search lightweight summaries first, load full transcript only on a match.

-- One row per stored conversation.
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    summary     TEXT,                         -- generated once at ingest time
    source      TEXT,                         -- which model/app it came from (claude, gemini, ollama, ...)
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    full_log    TEXT NOT NULL                 -- the complete transcript
);

-- Tags, many-to-many with conversations.
CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS conversation_tags (
    conversation_id  INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tag_id           INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (conversation_id, tag_id)
);

-- Full-text search over title + summary (keyword search, high precision).
-- TODO: keep this in sync with conversations via triggers, or rebuild on ingest.
CREATE VIRTUAL TABLE IF NOT EXISTS conversations_fts USING fts5(
    title,
    summary,
    content='conversations',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS conversations_ai
AFTER INSERT ON conversations
BEGIN
    INSERT INTO conversations_fts(rowid, title, summary)
    VALUES (new.id, new.title, new.summary);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS summary_vectors USING vec0(
    conversation_id INTEGER PRIMARY KEY,
    embedding FLOAT[384]
);

-- Semantic search over summary embeddings (vector similarity, high recall).
-- Requires the sqlite-vec extension to be loaded at connection time.
-- TODO: set the dimension to match your chosen embedding model
--       (all-MiniLM-L6-v2 = 384). Keep one model for the whole DB.

