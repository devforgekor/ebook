import json
import os
from pathlib import Path

from common_lib.azure.claude_sessions import (
    build_messages_from_jsonl,
    extract_claude_metadata,
    push_unpublished_sessions,
)


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n")


def test_build_messages_from_jsonl_parses_claude_session(tmp_path):
    jsonl_path = tmp_path / "session.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "type": "permission-mode",
                "message": {"content": "skip me"},
            },
            {
                "type": "user",
                "uuid": "u1234567",
                "timestamp": "2026-05-13T07:00:00Z",
                "message": {"content": "Hello"},
                "model": "sonnet",
                "cwd": "/workspace",
                "version": "1",
                "gitBranch": "main",
            },
            {
                "type": "assistant",
                "uuid": "a1234567",
                "timestamp": "2026-05-13T07:00:01Z",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "draft"},
                        {"type": "text", "text": "Answer"},
                        {"type": "tool_use", "name": "shell", "input": {"cmd": "ls"}},
                    ]
                },
                "model": "sonnet",
                "cwd": "/workspace",
                "version": "1",
                "gitBranch": "main",
            },
            {
                "type": "system",
                "uuid": "s1234567",
                "timestamp": "2026-05-13T07:00:02Z",
                "message": {"content": "system"},
            },
        ],
    )

    messages = build_messages_from_jsonl(jsonl_path, user_id="user-1")

    assert [message["role"] for message in messages] == ["user", "assistant", "system"]
    assert messages[0]["session_id"] == "session"
    assert messages[1]["thought_text"] == "draft"
    assert "tool_use: shell" in messages[1]["content"]


def test_extract_claude_metadata_only_for_claude_source():
    claude = {
        "source": "dev-claude-cli-mac",
        "session_id": "abc",
        "model": "sonnet",
        "cwd": "/workspace",
        "version": "1",
        "gitBranch": "main",
    }
    non_claude = {"source": "browser-plugin"}

    assert extract_claude_metadata(claude) == {
        "session_id": "abc",
        "model": "sonnet",
        "cwd": "/workspace",
        "version": "1",
        "gitBranch": "main",
    }
    assert extract_claude_metadata(non_claude) == {}


def test_push_unpublished_sessions_dry_run(tmp_path):
    project_dir = tmp_path / "projects" / "seedling"
    project_dir.mkdir(parents=True)
    jsonl_path = project_dir / "session.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "type": "user",
                "uuid": "u1234567",
                "timestamp": "2026-05-13T07:00:00Z",
                "message": {"content": "Hello"},
            }
        ],
    )
    track_file = project_dir / ".pushed_sessions"
    track_file.write_text("")
    old_time = 1_700_000_000
    os.utime(jsonl_path, (old_time, old_time))

    result = push_unpublished_sessions(project_dir=project_dir, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["messages"] == 1
