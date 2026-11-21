"""Platform adapters: convert each source's transcript format into a plain
full_log string that ingest.save_session can store.

Capture is the one inherently platform-specific part of AkashicCodex: every
platform (Claude Code, Gemini, ChatGPT, ...) writes its transcript in its own
format. Each function here is the ONE place that understands a single platform's
format; everything downstream (upsert, embedding, search) is shared and
format-agnostic. New platforms (see issue #21) add a sibling function named for
that platform, they do not touch the core.
"""

import json


def claude_transcript_to_log(transcript_path: str) -> str:
    """Flatten a Claude Code transcript (JSONL) into a "Role: text" log.

    Claude Code writes one JSON object per line. Most lines are noise
    (queue-operation, attachment, file-history-snapshot, ai-title); the real
    messages have a top-level type of "user" or "assistant" and a "message"
    object whose "content" is either a plain string or a list of typed blocks
    (only the "text" blocks carry conversational text).

    Parameters
    ----------
    transcript_path : str
        Path to the session's .jsonl transcript, as handed to the Stop hook.

    Returns
    -------
    str
        The conversation as plain text, one "User: ..." / "Assistant: ..." line
        per turn.
    """
    lines = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("type") not in ("user", "assistant"):
                continue
            message = entry.get("message", None)
            content = message.get("content", None)
            role = message.get("role", None)
            if isinstance(content, str):
                text = content
            else:
                text = " ".join(b["text"] for b in content if b.get("type") == "text")
            if not text.strip():
                continue
            model = message.get("model")
            label = f"{role.capitalize()} [model={model}]" if model else role.capitalize()
            lines.append(f"{label}: {text}")
    return "\n".join(lines)
