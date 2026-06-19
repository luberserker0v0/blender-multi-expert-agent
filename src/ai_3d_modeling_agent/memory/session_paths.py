"""Per-session runtime path helpers."""

import shutil
from pathlib import Path


def sanitize_session_id(session_id: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in session_id)
    return sanitized or "default-session"


def session_runtime_dir(runtime_root: Path, session_id: str) -> Path:
    return runtime_root / "session_data" / sanitize_session_id(session_id)


def session_progress_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "progress.json"


def session_console_log_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "console.log"


def session_mcp_log_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "mcp_tool_calls.jsonl"


def session_capture_dir(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "captures"


def session_pending_interaction_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "pending_interaction.json"


def session_meetings_log_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "meetings.jsonl"


def session_meeting_state_path(runtime_root: Path, session_id: str, phase_name: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / f"meeting_state_{phase_name}.json"


def session_plan_artifact_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "plan_artifact.json"


def session_build_execution_plan_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "build_execution_plan.json"


def session_assembly_execution_plan_path(runtime_root: Path, session_id: str) -> Path:
    return session_runtime_dir(runtime_root, session_id) / "assembly_execution_plan.json"


def list_session_meeting_state_paths(runtime_root: Path, session_id: str) -> list[Path]:
    return sorted(session_runtime_dir(runtime_root, session_id).glob("meeting_state_*.json"))


def ensure_session_runtime_dir(runtime_root: Path, session_id: str) -> Path:
    path = session_runtime_dir(runtime_root, session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_session_runtime_dir(runtime_root: Path, session_id: str) -> bool:
    path = session_runtime_dir(runtime_root, session_id)
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True
