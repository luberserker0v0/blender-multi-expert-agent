"""Session-scoped tool call logging helpers for execution phases."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ai_3d_modeling_agent.memory.session_paths import ensure_session_runtime_dir, session_mcp_log_path


def append_session_tool_call(
    context: Any,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any] | None = None,
    is_error: bool = False,
) -> dict[str, Any]:
    """Append a tool-call style record to the session MCP log if context is available."""

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": "",
        "tool_name": str(tool_name),
        "arguments": dict(arguments),
        "is_error": bool(is_error),
        "result": dict(result or {}),
    }

    state = context if isinstance(context, dict) else {}
    runtime_root_value = state.get("runtime_root")
    session_id = str(state.get("session_id", "")).strip()
    if not runtime_root_value or not session_id:
        return record

    runtime_root = Path(str(runtime_root_value))
    ensure_session_runtime_dir(runtime_root, session_id)
    path = session_mcp_log_path(runtime_root, session_id)
    record["session_id"] = session_id
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def format_tool_calls_markdown(tool_calls: list[dict[str, Any]]) -> str:
    """Render a compact markdown summary for Activity bubble expansion."""

    lines: list[str] = []
    for call in tool_calls:
        tool_name = str(call.get("tool_name", "")).strip() or "tool"
        arguments = call.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        formatted_args = ", ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in arguments.items())
        if formatted_args:
            lines.append(f"- `{tool_name}({formatted_args})`")
        else:
            lines.append(f"- `{tool_name}()`")
    return "\n".join(lines)
