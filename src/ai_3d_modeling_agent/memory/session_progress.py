"""Session progress persistence for MVP runs."""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.memory.session_paths import ensure_session_runtime_dir, session_progress_path
from ai_3d_modeling_agent.schemas.session_progress import MultiStageProgressSnapshot
from ai_3d_modeling_agent.schemas.task_objects import TaskObjectSpec


class SessionProgressStore:
    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root

    def progress_path(self, session_id: str) -> Path:
        ensure_session_runtime_dir(self.runtime_root, session_id)
        return session_progress_path(self.runtime_root, session_id)

    def write(self, session_id: str, payload: Dict[str, Any]) -> Path:
        path = self.progress_path(session_id)
        enriched_payload = dict(payload)
        enriched_payload["session_id"] = session_id
        enriched_payload["updated_at"] = int(time.time())
        with path.open("w", encoding="utf-8") as file:
            json.dump(enriched_payload, file, ensure_ascii=False, indent=2)
        return path

    def write_multi_stage_snapshot(
        self,
        session_id: str,
        snapshot: MultiStageProgressSnapshot,
    ) -> Path:
        return self.write(session_id, snapshot.to_dict())

    def mark_started(
        self,
        session_id: str,
        task: str,
        max_iterations: int,
        required_objects: Optional[List[TaskObjectSpec]] = None,
    ) -> Path:
        return self.write(
            session_id,
            {
                "status": "running",
                "task": task,
                "current_iteration": 0,
                "max_iterations": max_iterations,
                "required_objects": [item.to_dict() for item in (required_objects or [])],
                "actions": [],
                "final_gap_report_path": "",
                "final_object_scale": [],
                "reconnect_todo": {
                    "task_resume": True,
                    "model_unload_coordination": True,
                    "inflight_request_recovery": True,
                },
                "mcp_todo": {
                    "integration_planned": True,
                    "session_mapping": True,
                    "tool_boundary_decision": True,
                },
            },
        )

    def mark_iteration(
        self,
        session_id: str,
        task: str,
        current_iteration: int,
        max_iterations: int,
        required_objects: List[TaskObjectSpec],
        actions: List[str],
        gap_report_path: str,
        removed_object_names: Optional[List[str]] = None,
    ) -> Path:
        return self.write(
            session_id,
            {
                "status": "running",
                "task": task,
                "current_iteration": current_iteration,
                "max_iterations": max_iterations,
                "required_objects": [item.to_dict() for item in required_objects],
                "actions": list(actions),
                "removed_object_names": list(removed_object_names or []),
                "final_gap_report_path": gap_report_path,
                "final_object_scale": [],
                "reconnect_todo": {
                    "task_resume": True,
                    "model_unload_coordination": True,
                    "inflight_request_recovery": True,
                },
                "mcp_todo": {
                    "integration_planned": True,
                    "session_mapping": True,
                    "tool_boundary_decision": True,
                },
            },
        )

    def mark_finished(
        self,
        session_id: str,
        task: str,
        current_iteration: int,
        max_iterations: int,
        required_objects: List[TaskObjectSpec],
        actions: List[str],
        gap_report_path: str,
        final_object_scale: List[float],
        stop_reason: str,
        success: bool,
        removed_object_names: Optional[List[str]] = None,
    ) -> Path:
        return self.write(
            session_id,
            {
                "status": "completed" if success else "failed",
                "task": task,
                "current_iteration": current_iteration,
                "max_iterations": max_iterations,
                "required_objects": [item.to_dict() for item in required_objects],
                "actions": list(actions),
                "removed_object_names": list(removed_object_names or []),
                "final_gap_report_path": gap_report_path,
                "final_object_scale": list(final_object_scale),
                "stop_reason": stop_reason,
                "reconnect_todo": {
                    "task_resume": True,
                    "model_unload_coordination": True,
                    "inflight_request_recovery": True,
                },
                "mcp_todo": {
                    "integration_planned": True,
                    "session_mapping": True,
                    "tool_boundary_decision": True,
                },
            },
        )
