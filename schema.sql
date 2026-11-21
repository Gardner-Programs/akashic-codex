-- AkashicCodex schema (SQLite)
-- Two-tier retrieval: search lightweight summaries first, load full transcript only on a match.

-- One row per stored conversation.
CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    summary     TEXT,                          -- generated once at ingest time
    source      TEXT,                          -- which model/app it came from (claude, gemini, ollama, ...)
    summarizer  TEXT,                          -- which summarizer backend produced the summary
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    session_id  TEXT UNIQUE,                   -- per-session upsert key for auto-save (NULL for manual saves)
    thread_id   TEXT,                          -- logical conversation spanning sessions/models (NULL = own thread)
    full_log    TEXT NOT NULL                  -- the complete transcript
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

CREATE TABLE IF NOT EXISTS store_meta (
    key    TEXT PRIMARY KEY NOT NULL,
    value  TEXT NOT NULL
);

-- A chunk is normally one user/assistant exchange. It keeps stable retrieval
-- units for agents that need more detail than the conversation brief.
CREATE TABLE IF NOT EXISTS message_chunks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    turn_index      INTEGER NOT NULL,
    summary         TEXT NOT NULL,
    content         TEXT NOT NULL,
    UNIQUE (conversation_id, turn_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS message_chunks_fts USING fts5(
    summary,
    content='message_chunks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS message_chunks_ai AFTER INSERT ON message_chunks BEGIN
    INSERT INTO message_chunks_fts(rowid, summary) VALUES (new.id, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS message_chunks_ad AFTER DELETE ON message_chunks BEGIN
    INSERT INTO message_chunks_fts(message_chunks_fts, rowid, summary)
    VALUES ('delete', old.id, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS message_chunks_au AFTER UPDATE ON message_chunks BEGIN
    INSERT INTO message_chunks_fts(message_chunks_fts, rowid, summary)
    VALUES ('delete', old.id, old.summary);
    INSERT INTO message_chunks_fts(rowid, summary) VALUES (new.id, new.summary);
END;

-- Full-text search over title + summary (keyword search, high precision).
-- Kept in sync with conversations by the three triggers below (insert/delete/update).
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

CREATE TRIGGER IF NOT EXISTS conversations_ad
AFTER DELETE ON conversations
BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, title, summary)
    VALUES ('delete', old.id, old.title, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS conversations_au
AFTER UPDATE ON conversations
BEGIN
    INSERT INTO conversations_fts(conversations_fts, rowid, title, summary)
    VALUES ('delete', old.id, old.title, old.summary);
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
