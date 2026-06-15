"""Ingestion: turn a raw conversation into a stored, searchable record.

Do the expensive work ONCE here, at save time, so search stays fast and cheap.
The weak link in any memory system is how easily a conversation gets saved, so
keep this to a single simple step (paste, file drop, or batch export).
"""


def summarize(full_log: str) -> str:
    """Produce a short summary of a conversation.

    TODO: call whatever model you have handy. The summary is what search ranks
    over, so make it dense and topical. Store it once; never regenerate at query.
    """
    raise NotImplementedError


def suggest_tags(full_log: str) -> list[str]:
    """Propose topic tags from the content (don't hand-maintain a fixed list)."""
    raise NotImplementedError


def save_conversation(full_log: str, title: str | None = None, source: str | None = None) -> int:
    """Store a conversation end to end and return its id.

    TODO (the ingest pipeline):
      1. title  = title or generate one
      2. summary = summarize(full_log)
      3. tags    = suggest_tags(full_log)
      4. insert into conversations, conversation_tags, conversations_fts
      5. vector  = embeddings.embed(summary); insert into summary_vectors
    """
    raise NotImplementedError
