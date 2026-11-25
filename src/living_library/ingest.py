import os
import re
from collections import Counter

from .db import get_or_create_tag, link_conversation_tag
from .embeddings import embed, get_embedder_identity
from .summarizers import summarize

STOPWORDS = {
    'the',
    'a',
    'an',
    'and',
    'or',
    'but',
    'in',
    'on',
    'at',
    'to',
    'for',
    'of',
    'with',
    'by',
    'from',
    'is',
    'are',
    'was',
    'were',
    'be',
    'been',
    'being',
    'have',
    'has',
    'had',
    'do',
    'does',
    'did',
    'will',
    'would',
    'could',
    'should',
    'may',
    'might',
    'must',
    'can',
    'this',
    'that',
    'these',
    'those',
    'i',
    'you',
    'he',
    'she',
    'it',
    'we',
    'they',
    'me',
    'him',
    'her',
    'us',
    'them',
    'my',
    'your',
    'his',
    'its',
    'our',
    'their',
    'mine',
    'yours',
    'hers',
    'ours',
    'theirs',
}

TAG_PATTERN = re.compile(r'[a-zA-Z]{3,}')


def suggest_tags(full_log: str) -> list[str]:
    words = TAG_PATTERN.findall(full_log.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    counts = Counter(filtered)
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in top[:5]]


def ensure_embedder_identity(conn, vector: list[float]) -> None:
    from .db import get_meta, set_meta

    stored_model = get_meta(conn, 'embedding_model')
    stored_dim = get_meta(conn, 'embedding_dim')
    current_model, current_dim = get_embedder_identity()
    if stored_model is None:
        set_meta(conn, 'embedding_model', current_model)
        set_meta(conn, 'embedding_dim', str(len(vector)))
    elif stored_model != current_model:
        raise RuntimeError(
            f'Embedder mismatch: store has {stored_model} ({stored_dim} dims), '
            f'active is {current_model} ({current_dim} dims). '
            f"Run 'reembed' to switch models."
        )


def save_conversation(
    conn, full_log: str, title: str | None = None, source: str | None = None
) -> int:
    from .db import insert_conversation, insert_vector
    from .titlers import make_title

    ensure_embedder_identity(conn, embed(''))
    summary = summarize(full_log)
    vector = embed(summary)
    tags = suggest_tags(full_log)
    title = title or make_title(summary)
    conv_id = insert_conversation(
        conn,
        title or '',
        full_log,
        summarizer=os.environ.get('LIVING_LIBRARY_SUMMARIZER', 'extractive'),
        summary=summary,
        source=source,
    )
    for tag in tags:
        tag_id = get_or_create_tag(conn, tag)
        link_conversation_tag(conn, conv_id, tag_id)
    insert_vector(conn, conv_id, vector)
    conn.commit()
    return conv_id


def save_session(
    conn,
    session_id,
    full_log,
    title=None,
    source=None,
    thread_id=None,
    summary_override=None,
    summarizer_override=None,
) -> int:
    from .db import (
        assign_thread,
        delete_vector,
        find_transcript_overlaps,
        insert_vector,
        upsert_conversation,
    )
    from .titlers import make_title

    ensure_embedder_identity(conn, embed(''))
    summary = summary_override if summary_override is not None else summarize(full_log)
    vector = embed(summary)
    tags = suggest_tags(full_log)
    title = title or make_title(summary)
    summarizer = summarizer_override or os.environ.get('LIVING_LIBRARY_SUMMARIZER', 'extractive')
    conv_id = upsert_conversation(
        conn,
        session_id,
        title or '',
        full_log,
        summarizer=summarizer,
        summary=summary,
        source=source,
        thread_id=thread_id,
    )
    for tag in tags:
        tag_id = get_or_create_tag(conn, tag)
        link_conversation_tag(conn, conv_id, tag_id)
    delete_vector(conn, conv_id)
    insert_vector(conn, conv_id, vector)
    overlaps = find_transcript_overlaps(conn, session_id, full_log)
    if overlaps:
        all_ids = overlaps + [conv_id]
        if thread_id is None:
            import uuid

            thread_id = str(uuid.uuid4())
        assign_thread(conn, all_ids, thread_id)
    conn.commit()
    return conv_id
