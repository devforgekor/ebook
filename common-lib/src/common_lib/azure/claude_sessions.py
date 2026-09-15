"""
azure/claude_sessions | Claude Code session JSONL parsing and Service Bus delivery | needs:azure-servicebus | get_project_dir(),read_pushed_sessions(),write_pushed_sessions(),build_messages_from_jsonl(),extract_claude_metadata(),send_to_service_bus(),push_unpublished_sessions()
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

DEFAULT_SOURCE = "dev-claude-cli-mac"
DEFAULT_QUEUE_NAME = "seedling-inbox"
DEFAULT_USER_ID = "dev-claude-cli-mac"
SKIPPED_ENTRY_TYPES = {"permission-mode", "file-history-snapshot", "ai-title"}


def get_project_dir(cwd: Optional[str] = None) -> Path:
    """Return the Claude project directory for the current working directory."""
    base = cwd or os.getcwd()
    slug = base.replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug


def read_pushed_sessions(track_file: Path) -> Set[str]:
    """Load the set of already-pushed session IDs."""
    if not track_file.exists():
        return set()
    content = track_file.read_text().strip()
    if not content:
        return set()
    return set(content.splitlines())


def write_pushed_sessions(track_file: Path, sessions: Set[str]) -> None:
    """Persist the set of already-pushed session IDs."""
    track_file.write_text("\n".join(sorted(sessions)) + "\n")


def _coerce_content_blocks(content: object) -> List[dict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return content
    return []


def extract_claude_metadata(data: Dict[str, object]) -> Dict[str, object]:
    """Extract Claude-specific metadata from a Service Bus payload."""
    if data.get("source") != DEFAULT_SOURCE:
        return {}

    metadata = {
        "session_id": data.get("session_id", ""),
        "model": data.get("model", ""),
        "cwd": data.get("cwd", ""),
        "version": data.get("version", ""),
        "gitBranch": data.get("gitBranch", ""),
    }
    return {key: value for key, value in metadata.items() if value}


def build_messages_from_jsonl(jsonl_path: Path, user_id: Optional[str] = None) -> List[dict]:
    """Convert a Claude JSONL session into Service Bus messages."""
    messages: List[dict] = []
    session_id = jsonl_path.stem
    source_user_id = user_id or DEFAULT_USER_ID

    with open(jsonl_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_type = entry.get("type", "")
            if entry_type in SKIPPED_ENTRY_TYPES:
                continue

            message = entry.get("message", {})
            msg_uuid = entry.get("uuid") or (message.get("id", "") if isinstance(message, dict) else "")
            timestamp = entry.get("timestamp", "")

            if entry_type == "user":
                content = message.get("content", "") if isinstance(message, dict) else str(message)
                if not content:
                    continue
                messages.append({
                    "userId": source_user_id,
                    "turn_id": f"cc-{str(msg_uuid)[:8]}",
                    "role": "user",
                    "content": content,
                    "source": DEFAULT_SOURCE,
                    "session_id": session_id,
                    "created_at": timestamp,
                    "model": entry.get("model", ""),
                    "cwd": entry.get("cwd", ""),
                    "version": entry.get("version", ""),
                    "gitBranch": entry.get("gitBranch", ""),
                })
                continue

            if entry_type == "assistant":
                if not isinstance(message, dict):
                    continue
                content_blocks = _coerce_content_blocks(message.get("content", []))
                thinking_parts: List[str] = []
                text_parts: List[str] = []

                for block in content_blocks:
                    block_type = block.get("type")
                    if block_type == "thinking":
                        thinking_parts.append(block.get("thinking", ""))
                    elif block_type == "text":
                        text_parts.append(block.get("text", ""))
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "unknown")
                        tool_input = json.dumps(block.get("input", {}), ensure_ascii=False)
                        text_parts.append(f"[tool_use: {tool_name}] {tool_input}")

                thought_text = "\n".join(thinking_parts).strip()
                answer_text = "\n".join(text_parts).strip()
                if answer_text:
                    messages.append({
                        "userId": source_user_id,
                        "turn_id": f"cc-{str(msg_uuid)[:8]}",
                        "role": "assistant",
                        "content": answer_text,
                        "thought_text": thought_text,
                        "source": DEFAULT_SOURCE,
                        "session_id": session_id,
                        "created_at": timestamp,
                        "model": entry.get("model", ""),
                        "cwd": entry.get("cwd", ""),
                        "version": entry.get("version", ""),
                        "gitBranch": entry.get("gitBranch", ""),
                    })
                continue

            if entry_type == "system":
                content = message.get("content", "") if isinstance(message, dict) else str(message)
                if not content:
                    continue
                messages.append({
                    "userId": source_user_id,
                    "turn_id": f"cc-{str(msg_uuid)[:8]}",
                    "role": "system",
                    "content": content,
                    "source": DEFAULT_SOURCE,
                    "session_id": session_id,
                    "created_at": timestamp,
                })

    return messages


def send_to_service_bus(
    messages: List[dict],
    connection_string: str,
    queue_name: str = DEFAULT_QUEUE_NAME,
) -> int:
    """Send messages to Azure Service Bus and return the sent count."""
    if not connection_string:
        return 0

    from azure.servicebus import ServiceBusClient, ServiceBusMessage

    sent = 0
    client = ServiceBusClient.from_connection_string(connection_string)
    try:
        sender = client.get_queue_sender(queue_name=queue_name)
        batch_size = 100
        for index in range(0, len(messages), batch_size):
            chunk = messages[index : index + batch_size]
            sb_messages = [
                ServiceBusMessage(json.dumps(message, ensure_ascii=False, default=str))
                for message in chunk
            ]
            sender.send_messages(sb_messages)
            sent += len(chunk)
        return sent
    finally:
        client.close()


def push_unpublished_sessions(
    project_dir: Optional[Path] = None,
    connection_string: Optional[str] = None,
    queue_name: Optional[str] = None,
    user_id: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Push unpublished Claude sessions from the local Claude project dir."""
    project_dir = project_dir or get_project_dir()
    connection_string = connection_string or os.getenv("SERVICE_BUS_CONNECTION_STRING", "")
    queue_name = queue_name or os.getenv("SERVICE_BUS_QUEUE_NAME", DEFAULT_QUEUE_NAME)
    user_id = user_id or os.getenv("CLAUDE_DEV_USER_ID", DEFAULT_USER_ID)

    if not project_dir.exists():
        return {"status": "missing_project_dir", "project_dir": str(project_dir)}

    track_file = project_dir / ".pushed_sessions"
    pushed = read_pushed_sessions(track_file)

    jsonl_files = sorted(project_dir.glob("*.jsonl"))
    new_files = [path for path in jsonl_files if path.stem not in pushed]

    now = time.time()
    new_files = [path for path in new_files if (now - path.stat().st_mtime) > 60]
    if not new_files:
        return {"status": "nothing_to_push", "project_dir": str(project_dir), "sent": 0}

    all_messages: List[dict] = []
    session_counts: dict[str, int] = {}
    for jsonl_path in new_files:
        messages = build_messages_from_jsonl(jsonl_path, user_id=user_id)
        session_counts[jsonl_path.stem] = len(messages)
        all_messages.extend(messages)

    if dry_run:
        return {
            "status": "dry_run",
            "project_dir": str(project_dir),
            "sessions": list(session_counts.keys()),
            "messages": len(all_messages),
            "session_counts": session_counts,
        }

    sent = send_to_service_bus(all_messages, connection_string, queue_name=queue_name)
    if sent > 0:
        for jsonl_path in new_files:
            pushed.add(jsonl_path.stem)
        write_pushed_sessions(track_file, pushed)

    return {
        "status": "sent" if sent > 0 else "not_sent",
        "project_dir": str(project_dir),
        "sessions": list(session_counts.keys()),
        "messages": len(all_messages),
        "sent": sent,
        "session_counts": session_counts,
    }


def main() -> None:
    """CLI entry point for pushing Claude sessions."""
    parser = argparse.ArgumentParser(description="Push Claude Code sessions to Service Bus")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()

    result = push_unpublished_sessions(dry_run=args.dry_run)
    status = result.get("status")
    if status == "missing_project_dir":
        print(f"[push_claude] No Claude Code sessions directory: {result['project_dir']}")
        return
    if status == "nothing_to_push":
        print("[push_claude] No new sessions to push.")
        return
    if status == "dry_run":
        print(f"[push_claude] DRY RUN — {result['messages']} messages not sent.")
        return
    if result.get("sent", 0) > 0:
        print(
            f"[push_claude] Done: {result['sent']}/{result['messages']} messages "
            f"from {len(result['sessions'])} sessions."
        )
        return
    print("[push_claude] Nothing sent. Check connection or dry-run first.")


if __name__ == "__main__":
    main()
