from akashic_codex.ingest import save_conversation, save_session
from akashic_codex.memory import build_context, get_message_chunk, search_chunks


def test_trimmed_context_recovers_old_detail_with_summary_first(db_conn, mock_embed):
    full_log = "\n".join(
        [
            "User: The archival project keeps notes about historical files and records "
            "in a collection that tracks dates, sources, and cross references for later review, "
            "including scanned notes, paper folders, archive labels, and handwritten indexes, "
            "where the codeword amber-orchid-731 identifies the archival project.",
            "Assistant: I will remember that codeword for the archival project.",
            *[
                line
                for i in range(8)
                for line in (
                    f"User: Record routine progress item number {i}.",
                    f"Assistant: Progress item {i} is recorded in the project notes.",
                )
            ],
            "User: Give a brief summary of the design.",
            "Assistant: Keep a running brief, recent exchanges, and searchable older summaries.",
        ]
    )
    conv_id = save_conversation(db_conn, full_log, "Agent context design")

    full_context = full_log
    expected_answer = "amber-orchid-731"
    assert expected_answer in full_context

    trimmed = build_context(db_conn, conv_id, recent_turns=1)
    assert trimmed is not None
    trimmed_text = " ".join(
        [trimmed["brief"]]
        + [row["summary"] for row in trimmed["older_turns"]]
        + [row["content"] for row in trimmed["recent_turns"]]
    )
    assert expected_answer not in trimmed_text
    assert len(trimmed_text) < len(full_context)

    match = search_chunks(db_conn, "archival project codeword")
    assert match
    recovered = get_message_chunk(db_conn, match[0]["id"])
    assert recovered is not None
    assert expected_answer in recovered["content"]


def test_build_context_keeps_recent_chunks_and_older_pointers(db_conn, mock_embed):
    conv_id = save_conversation(
        db_conn,
        "User: First question about migration.\nAssistant: First answer.\n"
        "User: Second question about summaries.\nAssistant: Second answer.",
        "Migration notes",
    )
    context = build_context(db_conn, conv_id, recent_turns=1)
    assert len(context["older_turns"]) == 1
    assert len(context["recent_turns"]) == 1
    assert "content" not in context["older_turns"][0]
    assert "Second answer" in context["recent_turns"][0]["content"]


def test_session_upsert_preserves_existing_message_ids(db_conn, mock_embed):
    first = "User: First request.\nAssistant: First answer."
    conv_id = save_session(db_conn, "session-1", first)
    original_id = db_conn.execute(
        "SELECT id FROM message_chunks WHERE conversation_id = ?", (conv_id,)
    ).fetchone()["id"]

    save_session(db_conn, "session-1", first + "\nUser: Next request.\nAssistant: Next answer.")

    preserved = get_message_chunk(db_conn, original_id)
    assert preserved is not None
    assert "First answer" in preserved["content"]
