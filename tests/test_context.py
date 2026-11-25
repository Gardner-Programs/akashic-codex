from living_library import db
from living_library.context import build_context
from living_library.ingest import save_conversation


def test_context_uses_brief_recent_turns_and_retrievable_older_chunks(
    db_conn, mock_embed, monkeypatch
):
    monkeypatch.setattr(
        "living_library.ingest.summarize",
        lambda _text: "A deployment decision and formatting advice.",
    )
    transcript = "\n".join(
        [
            "User: We chose the uncommon deployment codename amber-otter-731.",
            "Assistant: The codename is amber-otter-731.",
            "User: Later turn about unrelated formatting preferences.",
            "Assistant: Use two spaces for indentation.",
        ]
    )
    conv_id = save_conversation(db_conn, transcript, title="Deployment")

    compact = build_context(db_conn, conv_id, recent_turns=2)
    assert len(compact["recent_turns"]) == 2
    assert compact["recent_turns"][0]["role"] == "user"
    assert compact["recent_turns"][1]["role"] == "assistant"
    assert "deployment" in compact["brief"]
    assert "amber-otter-731" not in " ".join(turn["content"] for turn in compact["recent_turns"])
    assert compact["older_turns"][0]["id"] == compact["older_chunk_ids"][0]
    assert compact["older_turns"][0]["summary"] == "A deployment decision and formatting advice."

    # The exact-detail task succeeds with the full transcript.
    task_answer = "amber-otter-731"
    assert task_answer in transcript
    full_context_answer = task_answer if task_answer in transcript else None
    compact_text = (
        compact["brief"] + "\n" + "\n".join(turn["content"] for turn in compact["recent_turns"])
    )
    compact_context_answer = task_answer if task_answer in compact_text else None
    assert full_context_answer == task_answer
    assert compact_context_answer is None

    # Trimming removes the fact, but the chunk pointer recovers it on demand.
    assert task_answer not in compact["brief"]
    assert task_answer not in " ".join(turn["content"] for turn in compact["recent_turns"])

    # The compact context still succeeds after following the older-turn pointer.
    recovered = db.get_message_chunk(db_conn, compact["older_chunk_ids"][0])
    recovered_answer = task_answer if task_answer in recovered["content"] else None
    assert recovered_answer == full_context_answer


def test_context_missing_conversation_returns_none(db_conn):
    assert build_context(db_conn, 999, recent_turns=2) is None
