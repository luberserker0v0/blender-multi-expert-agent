"""Helpers for the local multi-stage workflow GUI prototype."""

import json
import os
import sys
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ai_3d_modeling_agent.memory.session_paths import session_progress_path as runtime_session_progress_path

DEFAULT_AGENT_ORCHESTRATOR_URL = "http://127.0.0.1:4111"


@dataclass
class GuiLaunchConfig:
    task: str
    session_id: str
    agent_orchestrator_base_url: str
    agent_orchestrator_model: str = ""
    agent_orchestrator_conversation_id: str = ""
    agent_orchestrator_destroy_on_finish: bool = True
    agent_orchestrator_timeout_seconds: int = 120
    reference_texts: List[str] = field(default_factory=list)
    reference_images: List[str] = field(default_factory=list)
    max_part_refinement_rounds: int = 3
    max_assembly_rounds: int = 3
    use_blender_mcp: bool = False
    use_yolo_perception: bool = False
    yolo_model_path: str = ""
    yolo_viewpoints: List[str] = field(default_factory=list)
    blender_mcp_command: str = ""
    blender_mcp_cwd: str = ""
    blender_mcp_args: List[str] = field(default_factory=list)
    blender_mcp_env: Dict[str, str] = field(default_factory=dict)


@dataclass
class GuiSavedSettings:
    agent_orchestrator_base_url: str = DEFAULT_AGENT_ORCHESTRATOR_URL
    agent_orchestrator_model: str = ""
    agent_orchestrator_conversation_id: str = ""
    agent_orchestrator_destroy_on_finish: bool = True
    agent_orchestrator_timeout_seconds: int = 120
    max_part_refinement_rounds: int = 3
    max_assembly_rounds: int = 3
    use_yolo_perception: bool = False
    yolo_model_path: str = ""
    yolo_viewpoints: List[str] = field(default_factory=lambda: ["front"])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_orchestrator_base_url": self.agent_orchestrator_base_url,
            "agent_orchestrator_model": self.agent_orchestrator_model,
            "agent_orchestrator_conversation_id": self.agent_orchestrator_conversation_id,
            "agent_orchestrator_destroy_on_finish": self.agent_orchestrator_destroy_on_finish,
            "agent_orchestrator_timeout_seconds": self.agent_orchestrator_timeout_seconds,
            "max_part_refinement_rounds": self.max_part_refinement_rounds,
            "max_assembly_rounds": self.max_assembly_rounds,
            "use_yolo_perception": self.use_yolo_perception,
            "yolo_model_path": self.yolo_model_path,
            "yolo_viewpoints": list(self.yolo_viewpoints),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuiSavedSettings":
        return cls(
            agent_orchestrator_base_url=str(
                data.get("agent_orchestrator_base_url")
                or data.get("agent_orchestrator_url")
                or DEFAULT_AGENT_ORCHESTRATOR_URL
            ),
            agent_orchestrator_model=str(data.get("agent_orchestrator_model", "")),
            agent_orchestrator_conversation_id=str(data.get("agent_orchestrator_conversation_id", "")),
            agent_orchestrator_destroy_on_finish=bool(data.get("agent_orchestrator_destroy_on_finish", True)),
            agent_orchestrator_timeout_seconds=int(data.get("agent_orchestrator_timeout_seconds", 120)),
            max_part_refinement_rounds=int(data.get("max_part_refinement_rounds", 3)),
            max_assembly_rounds=int(data.get("max_assembly_rounds", 3)),
            use_yolo_perception=bool(data.get("use_yolo_perception", False)),
            yolo_model_path=str(data.get("yolo_model_path", "")),
            yolo_viewpoints=[str(item) for item in data.get("yolo_viewpoints", ["front"])],
        )


def generate_session_id(prefix: str = "session") -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:6]
    return f"{prefix}-{timestamp}-{suffix}"


def build_multi_stage_command(repo_root: Path, config: GuiLaunchConfig) -> List[str]:
    python_exe = os.environ.get("PYTHON_EXECUTABLE", sys.executable)
    command = [
        python_exe,
        str(repo_root / "scripts" / "run_pipeline.py"),
        "--task",
        config.task,
        "--session-id",
        config.session_id,
        "--agent-orchestrator-url",
        config.agent_orchestrator_base_url,
        "--max-part-refinement-rounds",
        str(config.max_part_refinement_rounds),
        "--max-assembly-rounds",
        str(config.max_assembly_rounds),
    ]
    if config.agent_orchestrator_model.strip():
        command.extend(["--agent-orchestrator-model", config.agent_orchestrator_model.strip()])
    if config.agent_orchestrator_conversation_id.strip():
        command.extend(["--agent-orchestrator-conversation-id", config.agent_orchestrator_conversation_id.strip()])
    command.extend(["--agent-orchestrator-timeout-seconds", str(config.agent_orchestrator_timeout_seconds)])
    if not config.agent_orchestrator_destroy_on_finish:
        command.append("--keep-agent-orchestrator-conversation")
    if config.use_blender_mcp:
        command.append("--use-blender-mcp")
        if config.blender_mcp_command.strip():
            command.extend(["--blender-mcp-command", config.blender_mcp_command.strip()])
        if config.blender_mcp_cwd.strip():
            command.extend(["--blender-mcp-cwd", config.blender_mcp_cwd.strip()])
        for item in config.blender_mcp_args:
            if item.strip():
                # Use = so values like "--directory" are treated as argument values, not as new CLI flags.
                command.append(f"--blender-mcp-arg={item.strip()}")
        for key, value in config.blender_mcp_env.items():
            command.append(f"--blender-mcp-env={key}={value}")
    if config.use_yolo_perception:
        command.append("--use-yolo-perception")
        if config.yolo_model_path.strip():
            command.extend(["--yolo-model-path", config.yolo_model_path.strip()])
        for item in config.yolo_viewpoints:
            if item.strip():
                command.extend(["--yolo-viewpoint", item.strip()])
    return command


def session_progress_path(runtime_root: Path, session_id: str) -> Path:
    return runtime_session_progress_path(runtime_root, session_id)


def gui_settings_path(runtime_root: Path) -> Path:
    return runtime_root / "gui" / "saved_settings.json"


def save_gui_settings(runtime_root: Path, settings: GuiSavedSettings) -> Path:
    path = gui_settings_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(settings.to_dict(), file, ensure_ascii=False, indent=2)
    return path


def load_gui_settings(runtime_root: Path) -> GuiSavedSettings:
    path = gui_settings_path(runtime_root)
    if not path.exists():
        return GuiSavedSettings()
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        return GuiSavedSettings()
    return GuiSavedSettings.from_dict(data)


def summarize_progress(progress_data: Dict[str, Any]) -> Dict[str, str]:
    active_task_id = str(progress_data.get("active_task_id", ""))
    stage = str(progress_data.get("stage", ""))
    status = str(progress_data.get("status", ""))
    stage_status = str(progress_data.get("stage_status", ""))

    latest_feedback = ""
    latest_capture_path = ""
    for task in progress_data.get("part_tasks", []):
        if not isinstance(task, dict):
            continue
        rounds = task.get("rounds", [])
        if active_task_id and str(task.get("task_id", "")) != active_task_id:
            continue
        if isinstance(rounds, list) and rounds:
            latest_round = rounds[-1]
            latest_feedback = str(latest_round.get("feedback_summary", ""))
            latest_capture_path = str(latest_round.get("capture_path", ""))
            break

    assembly = progress_data.get("assembly", {})
    if stage == "assembly" and isinstance(assembly, dict):
        rounds = assembly.get("rounds", [])
        if isinstance(rounds, list) and rounds:
            latest_round = rounds[-1]
            latest_feedback = str(latest_round.get("feedback_summary", latest_feedback))
            latest_capture_path = str(latest_round.get("capture_path", latest_capture_path))

    final_validation = progress_data.get("final_validation", {})
    final_capture_path = ""
    final_detected_parts = ""
    if isinstance(final_validation, dict):
        final_capture_path = str(final_validation.get("capture_path", ""))
        final_detected_parts = ", ".join(str(item) for item in final_validation.get("detected_parts", []))

    completed_task_ids = ", ".join(str(item) for item in progress_data.get("completed_task_ids", []))

    return {
        "status": status,
        "stage": stage,
        "stage_status": stage_status,
        "active_task_id": active_task_id,
        "completed_task_ids": completed_task_ids,
        "latest_feedback": latest_feedback,
        "latest_capture_path": latest_capture_path,
        "final_capture_path": final_capture_path,
        "final_detected_parts": final_detected_parts,
        "stop_reason": str(progress_data.get("stop_reason", "")),
    }


def extract_part_task_rows(progress_data: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for task in progress_data.get("part_tasks", []):
        if not isinstance(task, dict):
            continue
        rows.append(
            {
                "task_id": str(task.get("task_id", "")),
                "title": str(task.get("title", "")),
                "status": str(task.get("status", "")),
                "current_round": str(task.get("current_round", "")),
                "approved": "yes" if bool(task.get("approved", False)) else "no",
            }
        )
    return rows


def extract_part_round_rows(progress_data: Dict[str, Any], task_id: str) -> List[Dict[str, str]]:
    for task in progress_data.get("part_tasks", []):
        if not isinstance(task, dict) or str(task.get("task_id", "")) != task_id:
            continue
        rows: List[Dict[str, str]] = []
        for round_item in task.get("rounds", []):
            if not isinstance(round_item, dict):
                continue
            action = round_item.get("requested_action") or {}
            rows.append(
                {
                    "round_index": str(round_item.get("round_index", "")),
                    "approved": "yes" if bool(round_item.get("approved", False)) else "no",
                    "viewpoint": str(round_item.get("viewpoint", "")),
                    "action_type": str(action.get("action_type", "")),
                    "capture_path": str(round_item.get("capture_path", "")),
                    "feedback_summary": str(round_item.get("feedback_summary", "")),
                }
            )
        return rows
    return []


def extract_assembly_round_rows(progress_data: Dict[str, Any]) -> List[Dict[str, str]]:
    assembly = progress_data.get("assembly", {})
    if not isinstance(assembly, dict):
        return []
    rows: List[Dict[str, str]] = []
    for round_item in assembly.get("rounds", []):
        if not isinstance(round_item, dict):
            continue
        actions = round_item.get("requested_actions") or []
        first_action_type = ""
        if isinstance(actions, list) and actions:
            first_action = actions[0] if isinstance(actions[0], dict) else {}
            first_action_type = str(first_action.get("action_type", ""))
        rows.append(
            {
                "round_index": str(round_item.get("round_index", "")),
                "approved": "yes" if bool(round_item.get("approved", False)) else "no",
                "action_count": str(len(actions) if isinstance(actions, list) else 0),
                "first_action_type": first_action_type,
                "capture_path": str(round_item.get("capture_path", "")),
                "feedback_summary": str(round_item.get("feedback_summary", "")),
            }
        )
    return rows


def format_history_detail(title: str, row: Dict[str, Any], extra_lines: Optional[List[str]] = None) -> str:
    lines = [title]
    for key, value in row.items():
        lines.append(f"{key}: {value}")
    for line in extra_lines or []:
        lines.append(line)
    return "\n".join(lines)


def find_part_round_detail(progress_data: Dict[str, Any], task_id: str, round_index: str) -> Dict[str, Any]:
    for task in progress_data.get("part_tasks", []):
        if not isinstance(task, dict) or str(task.get("task_id", "")) != str(task_id):
            continue
        for round_item in task.get("rounds", []):
            if not isinstance(round_item, dict):
                continue
            if str(round_item.get("round_index", "")) == str(round_index):
                return round_item
    return {}


def find_assembly_round_detail(progress_data: Dict[str, Any], round_index: str) -> Dict[str, Any]:
    assembly = progress_data.get("assembly", {})
    if not isinstance(assembly, dict):
        return {}
    for round_item in assembly.get("rounds", []):
        if not isinstance(round_item, dict):
            continue
        if str(round_item.get("round_index", "")) == str(round_index):
            return round_item
    return {}


def format_round_detail(title: str, round_detail: Dict[str, Any], multi_action: bool = False) -> str:
    sections = build_round_inspector_sections(title, round_detail, multi_action=multi_action)
    lines: List[str] = []
    for section in sections:
        lines.append(section["title"])
        for item in section["items"]:
            lines.append(f"{item['label']}: {item['value']}")
    return "\n".join(lines)


def build_round_inspector_sections(
    title: str,
    round_detail: Dict[str, Any],
    multi_action: bool = False,
) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []

    summary_items = [
        {"label": "round_index", "value": round_detail.get("round_index", "")},
        {"label": "approved", "value": round_detail.get("approved", False)},
        {"label": "capture_path", "value": round_detail.get("capture_path", "")},
    ]
    if "viewpoint" in round_detail:
        summary_items.append({"label": "viewpoint", "value": round_detail.get("viewpoint", "")})
    summary_items.append({"label": "feedback_summary", "value": round_detail.get("feedback_summary", "")})
    sections.append({"title": title, "items": summary_items})

    context = round_detail.get("context") or {}
    if isinstance(context, dict) and context:
        sections.append(
            {
                "title": "Context",
                "items": [
                    {"label": "current_mode", "value": context.get("current_mode", "")},
                    {"label": "active_object_name", "value": context.get("active_object_name", "")},
                    {"label": "active_element_mode", "value": context.get("active_element_mode", "")},
                ],
            }
        )

    if multi_action:
        actions = round_detail.get("requested_actions") or []
        if isinstance(actions, list):
            for index, action in enumerate(actions, start=1):
                if not isinstance(action, dict):
                    continue
                sections.extend(_build_action_sections(action, f"Requested Action {index}"))
    else:
        action = round_detail.get("requested_action") or {}
        if isinstance(action, dict) and action:
            sections.extend(_build_action_sections(action, "Requested Action"))

    return sections


def _build_action_sections(action: Dict[str, Any], title: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = [
        {
            "title": title,
            "items": [
                {"label": "action_type", "value": action.get("action_type", "")},
                {"label": "execution_status", "value": action.get("execution_status", "")},
                {"label": "reason", "value": action.get("reason", "")},
            ],
        }
    ]
    parameters = action.get("parameters") or {}
    parameter_items: List[Dict[str, Any]] = []
    if isinstance(parameters, dict) and parameters:
        for key, value in parameters.items():
            parameter_items.append({"label": str(key), "value": value})
    else:
        parameter_items.append({"label": "<empty>", "value": ""})
    sections.append({"title": f"{title} Parameters", "items": parameter_items})
    return sections
