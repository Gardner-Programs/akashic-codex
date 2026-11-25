"""Provider export adapters preserve turns in the canonical transcript format."""

import json

from living_library.adapters import chatgpt_export, claude_export, gemini_export


def write_export(tmp_path, data):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_claude_export_reads_chat_messages_and_models(tmp_path):
    path = write_export(
        tmp_path,
        [
            {
                "name": "Claude chat",
                "chat_messages": [
                    {"sender": "human", "text": "Hello"},
                    {"sender": "assistant", "text": "Hi", "model": "claude-sonnet"},
                ],
            }
        ],
    )

    result = claude_export(path)

    assert result == [
        {
            "title": "Claude chat",
            "full_log": "User: Hello\nAssistant [model=claude-sonnet]: Hi",
        }
    ]


def test_gemini_export_reads_roles_and_text_parts(tmp_path):
    path = write_export(
        tmp_path,
        {
            "conversations": [
                {
                    "title": "Gemini chat",
                    "messages": [
                        {"role": "user", "text": "Question"},
                        {"role": "model", "content": [{"text": "Answer"}]},
                    ],
                }
            ]
        },
    )

    assert gemini_export(path)[0]["full_log"] == "User: Question\nAssistant: Answer"


def test_chatgpt_export_walks_mapping_and_skips_non_chat_nodes(tmp_path):
    path = write_export(
        tmp_path,
        [
            {
                "title": "ChatGPT chat",
                "mapping": {
                    "root": {"parent": None, "children": ["u"], "message": None},
                    "u": {
                        "parent": "root",
                        "children": ["a"],
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["Question"]},
                        },
                    },
                    "a": {
                        "parent": "u",
                        "children": [],
                        "message": {
                            "author": {"role": "assistant"},
                            "metadata": {"model_slug": "gpt-x"},
                            "content": {"parts": ["Answer"]},
                        },
                    },
                },
            }
        ],
    )

    assert chatgpt_export(path)[0] == {
        "title": "ChatGPT chat",
        "full_log": "User: Question\nAssistant [model=gpt-x]: Answer",
    }
