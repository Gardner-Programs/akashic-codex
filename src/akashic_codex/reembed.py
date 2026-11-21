"""Re-embed: move the whole store onto the active embedding model in one shot.

The store's core rule is one embedding model for every vector. Switching models
therefore means rebuilding every vector at once, never a mix. Set
AKASHIC_EMBEDDING_MODEL to the new model, then run the re-embed. Running it with
the same model is also fine: it rebuilds the vector index from the summaries.

The expensive embedding happens outside any transaction so the live auto-save
hook is not blocked. The swap itself runs under the write lock and first embeds
anything that changed while the bulk pass was running, so a conversation saved
mid-run is not dropped from the index.
"""

import sqlite3

from akashic_codex import db
from akashic_codex.embeddings import MODEL_NAME, embed


def _embed_all(rows, cache: dict[str, list[float]]) -> dict[int, list[float]]:
    """Embed each row's summary, reusing vectors already computed for that text."""
    vectors = {}
    for row in rows:
        text = row["summary"] or ""
        if text not in cache:
            cache[text] = embed(text)
        vectors[row["id"]] = cache[text]
    return vectors


def plan_reembed(conn: sqlite3.Connection) -> dict:
    """Describe what a re-embed would do, without changing anything.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.

    Returns
    -------
    dict
        ``count`` (conversations to embed), ``old_model`` and ``old_dim`` (the
        stored identity, None if unstamped), ``new_model`` (the active model),
        and ``cost`` in dollars.
    """
    old_dim = db.get_meta(conn, "embedding_dim")
    return {
        "count": len(db.list_summaries(conn)),
        "old_model": db.get_meta(conn, "embedding_model"),
        "old_dim": int(old_dim) if old_dim else None,
        "new_model": MODEL_NAME,
        # The only embedder backend is local sentence-transformers. A paid
        # backend would estimate its token cost here so the user opts in knowingly.
        "cost": 0.0,
    }


def reembed_store(conn: sqlite3.Connection) -> dict:
    """Rebuild every summary vector with the active embedding model.

    Backs up the database first, then embeds all summaries, then atomically
    replaces the vector table (recreated at the new dimension) and stamps the
    new embedder identity in store_meta. If anything fails, the store keeps its
    old vectors and identity; the backup is a second line of defense.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection with no transaction in progress.

    Returns
    -------
    dict
        ``count`` (vectors written), ``model`` and ``dim`` (the new identity),
        and ``backup`` (path of the pre-run snapshot).
    """
    backup_path = db.backup(conn, "pre-reembed")
    cache: dict[str, list[float]] = {}
    _embed_all(db.list_summaries(conn), cache)

    conn.execute("BEGIN IMMEDIATE")
    try:
        # Catch anything saved or re-summarized during the bulk pass; only new
        # summary texts miss the cache, so this is cheap.
        vectors = _embed_all(db.list_summaries(conn), cache)
        dim = len(next(iter(vectors.values()))) if vectors else len(embed(""))
        db.replace_all_vectors(
            conn,
            vectors,
            dim,
            meta={"embedding_model": MODEL_NAME, "embedding_dim": str(dim)},
        )
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return {"count": len(vectors), "model": MODEL_NAME, "dim": dim, "backup": backup_path}
