"""Derive structured turns from the canonical plain-text transcript."""

import re

_TURN = re.compile(r"^(User|Assistant|System|Tool)(?:\s+\[model=([^\]]+)\])?:\s*(.*)$", re.I)


def parse_messages(full_log: str) -> list[dict[str, str | None]]:
    """Parse conventional role-prefixed transcript lines into turns.

    Continuation lines belong to the preceding turn. Unrecognized lines before
    the first role label are ignored because their role cannot be inferred.
    """
    messages: list[dict[str, str | None]] = []
    for line in full_log.splitlines():
        match = _TURN.match(line)
        if match:
            role, model, content = match.groups()
            messages.append(
                {
                    "role": role.lower(),
                    "model": model.strip() if model else None,
                    "content": content,
                }
            )
        elif messages:
            messages[-1]["content"] = f"{messages[-1]['content']}\n{line}"
    return messages
