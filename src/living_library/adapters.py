import json
from typing import Any


def _read_json(path: str) -> Any:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _role_log(turns: list[tuple[str, str, str | None]]) -> str:
    lines = []
    for role, content, model in turns:
        prefix = role.capitalize()
        if model and role == 'assistant':
            prefix += f' [model={model}]'
        lines.append(f'{prefix}: {content}')
    return '\n'.join(lines)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ' '.join(_text(v) for v in value)
    if isinstance(value, dict):
        if 'text' in value:
            return value['text']
        if 'content' in value:
            return _text(value['content'])
    return ''


def _claude_conversation(item: dict) -> dict[str, str | None]:
    messages = item.get('chat_messages', [])
    turns = []
    for msg in messages:
        role = msg.get('role') or msg.get('sender')
        content = _text(msg.get('content') if 'content' in msg else msg.get('text'))
        model = msg.get('model')
        if role == 'human':
            role = 'user'
        if role in ('user', 'assistant') and content:
            turns.append((role, content, model))
    title = item.get('title') or item.get('name') or item.get('uuid')
    return {'full_log': _role_log(turns), 'title': title}


def claude_export(path: str) -> list[dict[str, str | None]]:
    data = _read_json(path)
    if isinstance(data, list):
        return [_claude_conversation(item) for item in data]
    return [_claude_conversation(data)]


def gemini_export(path: str) -> list[dict[str, str | None]]:
    data = _read_json(path)
    conversations = data.get('conversations', [])
    if not conversations and isinstance(data, list):
        conversations = data
    results = []
    for conv in conversations:
        messages = conv.get('messages', [])
        turns = []
        for msg in messages:
            role = msg.get('role')
            content = _text(msg.get('parts') if 'parts' in msg else msg.get('text'))
            if not content and 'content' in msg:
                content = _text(msg.get('content'))
            if role in ('user', 'model') and content:
                mapped_role = 'assistant' if role == 'model' else 'user'
                turns.append((mapped_role, content, None))
        if turns:
            results.append({'full_log': _role_log(turns), 'title': conv.get('title')})
    return results


def _chatgpt_text(message: dict) -> str:
    content = message.get('content')
    if isinstance(content, dict):
        parts = content.get('parts')
        if isinstance(parts, list):
            return ' '.join(str(p) for p in parts if p)
    return str(content) if content else ''


def chatgpt_export(path: str) -> list[dict[str, str | None]]:
    data = _read_json(path)
    results = []
    for conv in data:
        mapping = conv.get('mapping', {})
        turns = []
        for node in mapping.values():
            msg = node.get('message')
            if not msg:
                continue
            role = msg.get('author', {}).get('role')
            content = _chatgpt_text(msg)
            if role in ('user', 'assistant') and content:
                model = msg.get('metadata', {}).get('model_slug') if role == 'assistant' else None
                turns.append((role, content, model))
        if turns:
            results.append({'full_log': _role_log(turns), 'title': conv.get('title')})
    return results


def claude_transcript_to_log(transcript_path: str) -> str:
    turns = []
    with open(transcript_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_type = entry.get('type')
            message = entry.get('message', {})
            content = message.get('content')
            model = message.get('model')
            if msg_type == 'user':
                if isinstance(content, str):
                    turns.append(('user', content, None))
                elif isinstance(content, list):
                    text = ' '.join(
                        str(block.get('text', ''))
                        for block in content
                        if block.get('type') == 'text'
                    )
                    if text:
                        turns.append(('user', text, None))
            elif msg_type == 'assistant':
                if isinstance(content, str):
                    turns.append(('assistant', content, model))
                elif isinstance(content, list):
                    for block in content:
                        if block.get('type') == 'text':
                            turns.append(('assistant', block.get('text', ''), model))
    return _role_log(turns)
