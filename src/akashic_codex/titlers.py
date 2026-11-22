"""Titles: a short human-readable name for each conversation.

Same seam pattern as the summarizer: AKASHIC_TITLER picks the backend.
`heuristic` (default) is offline and deterministic; `ollama:<model>` asks a
local model. Unlike the summarizer, a failing Ollama does NOT fail the save: a
title is cosmetic and can be regenerated later with ``cli retitle``, so losing
a conversation over it would be the wrong trade.
"""

import json
import os
import re
import urllib.request

from akashic_codex import db
from akashic_codex.summarizers import AKASHIC_OLLAMA_HOST

TITLER = os.environ.get("AKASHIC_TITLER", "heuristic")
TITLE_MAX_CHARS = 80
UNTITLED = "Untitled"

PROMPT = (
    "Write a short, specific title (3 to 7 words) for a conversation with this summary. "
    "Reply with the title only, no quotes.\n\nSummary:\n{}"
)


def make_title(summary: str) -> str:
    """Return a title for a conversation from its summary.

    Parameters
    ----------
    summary : str
        The conversation's summary (titles are built from it, not the full log).

    Returns
    -------
    str
        A short title, or "Untitled" if there is nothing to title.

    Raises
    ------
    ValueError
        If AKASHIC_TITLER names an unknown backend.
    """
    if not summary or not summary.strip():
        return UNTITLED
    backend, _, detail = TITLER.partition(":")
    if backend == "heuristic":
        return _heuristic(summary)
    if backend == "ollama":
        try:
            return _ollama(summary, detail) or _heuristic(summary)
        except Exception:
            return _heuristic(summary)
    raise ValueError(f"Unknown titler backend: {TITLER}")


def _clean(text: str) -> str:
    return text.strip().strip("\"'*#`").rstrip(".").strip()[:TITLE_MAX_CHARS]


def _heuristic(summary: str) -> str:
    """First sentence of the summary, trimmed to a word boundary."""
    first = re.split(r"(?<=[.?!])\s", summary.strip(), maxsplit=1)[0]
    if len(first) > TITLE_MAX_CHARS:
        first = first[:TITLE_MAX_CHARS].rsplit(" ", 1)[0]
    return _clean(first) or UNTITLED


def _ollama(summary: str, model: str) -> str:
    """Ask a local Ollama model for a title; raises on any request failure."""
    body = json.dumps(
        {"model": model, "prompt": PROMPT.format(summary[:2000]), "stream": False}
    ).encode()
    req = urllib.request.Request(
        f"{AKASHIC_OLLAMA_HOST}/api/generate", body, {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        text = json.load(resp)["response"].strip()
    lines = [line for line in text.splitlines() if line.strip()]
    return _clean(lines[0]) if lines else ""


def retitle_store(conn, all_rows: bool = False) -> dict:
    """Regenerate titles with the active titler, after backing up the store.

    Parameters
    ----------
    conn : sqlite3.Connection
        Open database connection.
    all_rows : bool, optional
        Retitle every conversation; by default only "Untitled" or empty ones.

    Returns
    -------
    dict
        ``count`` (titles changed), ``scanned`` (rows considered), ``backup``.
    """
    backup_path = db.backup(conn, "pre-retitle")
    rows = db.list_for_retitle(conn, only_untitled=not all_rows)
    changed = 0
    for row in rows:
        title = make_title(row["summary"])
        if title != UNTITLED and title != row["title"]:
            db.set_title(conn, row["id"], title)
            changed += 1
    return {"count": changed, "scanned": len(rows), "backup": backup_path}
