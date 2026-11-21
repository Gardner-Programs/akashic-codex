"""Summarization: condense a conversation into the short text search ranks over.

One configurable seam (AKASHIC_SUMMARIZER), shaped like the embedder's. But
unlike the embedder, the summarizer may change freely between saves, so its
identity is recorded per conversation, not once per store. The default is a
local, offline, dependency-free extractive summarizer so a fresh clone and CI
work with no external services; other backends (for example Ollama) plug in
behind this same seam, selected by the env var.
"""

import json
import os
import re
import urllib.request

import numpy as np

from akashic_codex.embeddings import embed

# Active summarizer, as "backend" or "backend:detail" (e.g. "ollama:llama3").
# Also the value recorded as per-conversation provenance at ingest time.
SUMMARIZER = os.environ.get("AKASHIC_SUMMARIZER", "extractive")
AKASHIC_OLLAMA_HOST = os.environ.get("AKASHIC_OLLAMA_HOST", "http://localhost:11434").rstrip("/")

# Character budget for the extractive lead summary.
SUMMARY_MAX_CHARS = 300
# Ollama is asked for a short summary, but some models are verbose. This cap is
# intentionally generous and only applied at a sentence boundary.
OLLAMA_SUMMARY_MAX_CHARS = 1200
MIN_EXTRACTIVE_UNIT_CHARS = 20


def summarize(full_log: str) -> str:
    """Summarize a conversation using the configured backend.

    Reads SUMMARIZER (a "backend[:detail]" string), routes to the matching
    backend, and returns its summary. Should fail loud if the configured
    backend is unknown or unavailable, rather than silently storing a degraded
    summary that then gets embedded and indexed.

    Parameters
    ----------
    full_log : str
        The complete conversation transcript.

    Returns
    -------
    str
        A short summary of the conversation.
    """
    backend, _, detail = SUMMARIZER.partition(":")
    if backend == "extractive":
        return _extractive(full_log)
    elif backend == "ollama":
        return _ollama(full_log, detail)
    else:
        raise ValueError("Extraction method not recognized.")


def _extractive(full_log: str) -> str:
    """Lead-sentence extractive summary: no model, deterministic, offline.

    Take leading sentences up to SUMMARY_MAX_CHARS, stopping on a sentence
    boundary so the summary never cuts off mid-word. This is the default
    backend and the one tests run against.

    Parameters
    ----------
    full_log : str
        The complete conversation transcript.

    Returns
    -------
    str
        The lead-sentence summary.
    """

    sentences = _extractive_units(full_log)
    if not sentences:
        return ""
    if len(sentences) <= 1:
        return " ".join(sentences)[:SUMMARY_MAX_CHARS]
    sentences_vectors = [embed(sen) for sen in sentences]
    matrix = np.array(sentences_vectors)
    centroid = matrix.mean(axis=0)
    dots = matrix @ centroid
    row_norms = np.linalg.norm(matrix, axis=1)
    centroid_norm = np.linalg.norm(centroid)
    scores = dots / (row_norms * centroid_norm)
    ranked_idx = np.argsort(scores)[::-1]
    selected = []
    current_len = 0
    for idx in ranked_idx:
        current_sen = sentences[idx]
        if current_len + len(current_sen) <= SUMMARY_MAX_CHARS:
            selected.append(idx)
            current_len += len(current_sen) + 1
    if len(selected) == 0:
        return sentences[ranked_idx[0]][:SUMMARY_MAX_CHARS]
    return " ".join(sentences[i] for i in sorted(selected))


def _extractive_units(full_log: str) -> list[str]:
    """Split prose within lines/turns and discard structural fragments."""
    units = []
    for line in full_log.splitlines():
        # Markdown headings are labels for the content that follows, not
        # sentence candidates, even when the heading itself is long.
        if re.match(r"^\s*#{1,6}\s+", line):
            continue
        line = re.sub(r"^\s*(?:User|Assistant)\s*:\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", line)
        # A heading marker is formatting, while its text may still be useful.
        line = re.sub(r"^\s*#+\s*", "", line)
        for unit in re.split(r"(?<=[.?!])\s+", line.strip()):
            unit = unit.strip()
            if len(unit) >= MIN_EXTRACTIVE_UNIT_CHARS:
                units.append(unit)
    if not units:
        # Keep short, meaningful inputs usable, while punctuation-only labels
        # and markers still disappear.
        fragments = []
        for line in full_log.splitlines():
            if not line.strip() or re.match(r"^\s*#{1,6}\s+", line):
                continue
            line = re.sub(r"^\s*(?:User|Assistant)\s*:\s*", "", line.strip(), flags=re.IGNORECASE)
            line = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", line)
            fragments.append(line.strip())
        if len(fragments) == 1 and re.search(r"[A-Za-z]{3}", fragments[0]):
            return fragments
    return units


def _ollama(full_log: str, model: str) -> str:
    """Abstractive summary via a local Ollama model, behind the same seam.

    Fail loud (raise) if Ollama is unreachable or the request fails, so a
    misconfigured backend surfaces instead of quietly degrading the store.

    Parameters
    ----------
    full_log : str
        The complete conversation transcript.
    model : str
        The Ollama model name (the "detail" part of the SUMMARIZER value).

    Returns
    -------
    str
        The model's summary of the conversation.
    """
    prompt = (
        f"Summarize this conversation for a future LLM agents use only "
        f"two to three sentences. \n\n{full_log}"
    )
    payload = {"model": model, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{AKASHIC_OLLAMA_HOST}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return _soft_cap_ollama(json.load(response)["response"])
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama unreachable at {AKASHIC_OLLAMA_HOST}, is it running?") from e


def _soft_cap_ollama(summary: str) -> str:
    """Trim verbose output at the last sentence boundary within the soft cap."""
    summary = summary.strip()
    if len(summary) <= OLLAMA_SUMMARY_MAX_CHARS:
        return summary
    boundaries = list(re.finditer(r"[.!?](?:[\"')\]]*)?(?=\s|$)", summary))
    if not boundaries:
        return summary
    within_cap = [boundary for boundary in boundaries if boundary.end() <= OLLAMA_SUMMARY_MAX_CHARS]
    # Preserve at least one complete sentence when the first sentence itself
    # runs past the cap. This keeps the cap soft without retaining all later text.
    boundary = within_cap[-1] if within_cap else boundaries[0]
    return summary[: boundary.end()].rstrip()
