import json
import os
import re
import urllib.request
from urllib.error import URLError
from urllib.request import Request

from .embeddings import embed

LIVING_LIBRARY_SUMMARIZER = os.environ.get('LIVING_LIBRARY_SUMMARIZER', 'extractive')
LIVING_LIBRARY_OLLAMA_HOST = os.environ.get('LIVING_LIBRARY_OLLAMA_HOST', 'http://localhost:11434')
LIVING_LIBRARY_SUMMARY_MAX_CHARS = 300
LIVING_LIBRARY_OLLAMA_SUMMARY_MAX_CHARS = 1200


def summarize(full_log: str) -> str:
    backend = os.environ.get('LIVING_LIBRARY_SUMMARIZER', LIVING_LIBRARY_SUMMARIZER)
    if backend.startswith('ollama:'):
        model = backend.split(':', 1)[1]
        return _ollama(full_log, model)
    if backend == 'extractive':
        return _extractive(full_log)
    raise ValueError(f'Unknown summarizer backend: {backend}')


def _extractive(full_log: str) -> str:
    units = _extractive_units(full_log)
    if not units:
        return ''

    unit_vectors = [embed(u) for u in units]
    import numpy as np

    centroid = np.mean(unit_vectors, axis=0)
    similarities = [float(np.dot(v, centroid)) for v in unit_vectors]
    ranked = sorted(zip(units, similarities, strict=True), key=lambda x: x[1], reverse=True)
    budget = LIVING_LIBRARY_SUMMARY_MAX_CHARS
    selected = []
    total = 0
    for unit, _ in ranked:
        if total + len(unit) <= budget:
            selected.append(unit)
            total += len(unit)
    selected.sort(key=lambda u: full_log.index(u))
    return ' '.join(selected)


def _extractive_units(full_log: str) -> list[str]:
    lines = full_log.split('\n')
    units = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            continue
        speaker = re.match(r'^(User|Assistant|System|Tool):\s*', line)
        if speaker:
            line = line[speaker.end() :]
        line = re.sub(r'^[-*]\s*', '', line)
        line = re.sub(r'^\d+\.\s*', '', line)
        if speaker:
            if line.strip():
                units.append(line.strip())
            continue
        if len(line) < 20:
            continue
        sentences = re.split(r'(?<=[.!?])\s+', line)
        for s in sentences:
            s = s.strip()
            if len(s) >= 20:
                units.append(s)
    return units


def _ollama(full_log: str, model: str) -> str:
    prompt = (
        'Summarize this conversation in 3-5 sentences, capturing the key topics and decisions:\n\n'
        f'{full_log}'
    )
    data = json.dumps({'model': model, 'prompt': prompt, 'stream': False}).encode()
    req = Request(
        f'{LIVING_LIBRARY_OLLAMA_HOST}/api/generate',
        data=data,
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return _soft_cap_ollama(result.get('response', '').strip())
    except URLError as e:
        raise RuntimeError(f'Ollama request failed: {e}') from e


def _soft_cap_ollama(summary: str) -> str:
    cap = LIVING_LIBRARY_OLLAMA_SUMMARY_MAX_CHARS
    if len(summary) <= cap:
        return summary
    sentences = re.split(r'(?<=[.!?])\s+', summary)
    total = 0
    kept = []
    for s in sentences:
        if len(s) > cap:
            return s
        separator = 1 if kept else 0
        if total + separator + len(s) <= cap:
            kept.append(s)
            total += separator + len(s)
        else:
            break
    if kept:
        return ' '.join(kept)
    return summary
