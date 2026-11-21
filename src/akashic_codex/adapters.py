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
from pathlib import Path


def _read_json(path: str) -> object:
    """Read a provider export JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _role_log(turns: list[tuple[str, str, str | None]]) -> str:
    """Render normalized (role, content, model) turns for the ingest parser."""
    lines = []
    for role, content, model in turns:
        content = content.strip()
        if not content:
            continue
        label = role.capitalize()
        if model:
            label += f" [model={model}]"
        lines.append(f"{label}: {content}")
    return "\n".join(lines)


def _text(value: object) -> str:
    """Extract plain text from provider content represented as strings or blocks."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                candidate = block.get("text") or block.get("content")
                if isinstance(candidate, str):
                    parts.append(candidate)
        return "\n".join(parts)
    return ""


def _claude_conversation(item: dict) -> dict[str, str | None]:
    turns = []
    for message in item.get("chat_messages", item.get("messages", [])):
        if not isinstance(message, dict):
            continue
        sender = message.get("sender") or message.get("role")
        role = {"human": "user", "assistant": "assistant"}.get(sender, sender)
        if role not in {"user", "assistant", "system"}:
            continue
        turns.append(
            (role, _text(message.get("text", message.get("content"))), message.get("model"))
        )
    return {"title": item.get("name") or item.get("title"), "full_log": _role_log(turns)}


def claude_export(path: str) -> list[dict[str, str | None]]:
    """Parse Claude's account export JSON into conversations."""
    data = _read_json(path)
    if isinstance(data, dict):
        data = data.get("conversations", [data])
    if not isinstance(data, list):
        raise ValueError("Claude export must be a JSON array or an object with conversations")
    return [_claude_conversation(item) for item in data if isinstance(item, dict)]


def gemini_export(path: str) -> list[dict[str, str | None]]:
    """Parse Gemini conversation JSON exports (including Takeout-style wrappers)."""
    data = _read_json(path)
    if isinstance(data, dict):
        data = data.get("conversations", data.get("chats", [data]))
    if not isinstance(data, list):
        raise ValueError("Gemini export must be a JSON array or contain conversations")
    conversations = []
    for item in data:
        if not isinstance(item, dict):
            continue
        turns = []
        for message in item.get("messages", item.get("turns", [])):
            if not isinstance(message, dict):
                continue
            role = message.get("role") or message.get("author") or message.get("sender")
            if isinstance(role, dict):
                role = role.get("role") or role.get("name")
            role = str(role or "").lower()
            role = (
                "assistant"
                if role in {"model", "gemini", "assistant"}
                else "user"
                if role in {"user", "human"}
                else role
            )
            if role not in {"user", "assistant"}:
                continue
            content = message.get("text", message.get("content", message.get("message")))
            turns.append((role, _text(content), message.get("model")))
        conversations.append(
            {
                "title": item.get("title") or item.get("name"),
                "full_log": _role_log(turns),
            }
        )
    return conversations


def _chatgpt_text(message: dict) -> str:
    content = message.get("content") or {}
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return _text(content)
    parts = content.get("parts")
    return _text(parts) if parts is not None else _text(content.get("text"))


def chatgpt_export(path: str) -> list[dict[str, str | None]]:
    """Parse ChatGPT conversations.json, ordering messages by their parent chain."""
    data = _read_json(path)
    if isinstance(data, dict):
        data = data.get("conversations", [data])
    if not isinstance(data, list):
        raise ValueError("ChatGPT export must be a JSON array or contain conversations")
    conversations = []
    for item in data:
        if not isinstance(item, dict):
            continue
        mapping = item.get("mapping")
        turns = []
        if isinstance(mapping, dict):
            nodes = mapping
            roots = [
                key
                for key, node in nodes.items()
                if isinstance(node, dict) and not node.get("parent")
            ]
            ordered = []
            key = roots[0] if roots else None
            visited = set()
            while key in nodes and key not in visited:
                visited.add(key)
                node = nodes[key]
                ordered.append(node)
                children = node.get("children") or []
                key = children[0] if children else None
            ordered.extend(node for node in nodes.values() if node not in ordered)
            for node in ordered:
                message = node.get("message") or {}
                author = message.get("author") or {}
                role = author.get("role") if isinstance(author, dict) else author
                if role not in {"user", "assistant", "system"}:
                    continue
                metadata = message.get("metadata") or {}
                turns.append((role, _chatgpt_text(message), metadata.get("model_slug")))
        else:
            for message in item.get("messages", []):
                if isinstance(message, dict):
                    role = message.get("role") or message.get("author")
                    if isinstance(role, dict):
                        role = role.get("role")
                    if role in {"user", "assistant", "system"}:
                        turns.append(
                            (
                                role,
                                _text(message.get("content", message.get("text"))),
                                message.get("model"),
                            )
                        )
        conversations.append(
            {
                "title": item.get("title") or item.get("name"),
                "full_log": _role_log(turns),
            }
        )
    return conversations


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
