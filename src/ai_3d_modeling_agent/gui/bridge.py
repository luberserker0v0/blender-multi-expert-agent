"""Local API bridge for the React UI."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from copy import deepcopy
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ai_3d_modeling_agent.gui.prototype import (
    GuiLaunchConfig,
    GuiSavedSettings,
    build_multi_stage_command,
    generate_session_id,
    load_gui_settings,
    save_gui_settings,
    session_progress_path,
)
from ai_3d_modeling_agent.io.settings_loader import load_settings as load_pipeline_settings
from ai_3d_modeling_agent.memory.session_paths import (
    delete_session_runtime_dir,
    ensure_session_runtime_dir,
    list_session_meeting_state_paths,
    sanitize_session_id,
    session_assembly_execution_plan_path,
    session_build_execution_plan_path,
    session_console_log_path,
    session_meeting_state_path,
    session_meetings_log_path,
    session_mcp_log_path,
    session_pending_interaction_path,
    session_plan_artifact_path,
)
from ai_3d_modeling_agent.multi_expert.core.meeting import (
    MEETING_SCHEMA_VERSION,
    load_all_phase_meeting_states,
    load_phase_meeting_state,
    select_latest_meeting_state,
)
from ai_3d_modeling_agent.services.agent_orchestrator import (
    AgentOrchestratorClient,
    AgentOrchestratorConfig,
)
from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient


class GuiBridgeService:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.runtime_root = self.repo_root / "data" / "runtime"
        self.backend_settings_path = self.repo_root / "settings.json"
        self.live_bridge_smoke_mode = os.environ.get("AI3D_E2E_LIVE_BRIDGE_SMOKE", "").strip() == "1"
        self.ui_state_lock = threading.RLock()
        self.process_lock = threading.RLock()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.process_log_handles: Dict[str, Any] = {}
        self.run_statuses: Dict[str, Dict[str, Any]] = {}
        self.last_run_payloads: Dict[str, Dict[str, Any]] = {}
        self.retry_plans: Dict[str, Dict[str, Any]] = {}
        self.stream_lock = threading.RLock()
        self.mcp_status: Dict[str, Any] = {
            "enabled": True,
            "state": "idle",
            "message": "Blender MCP has not been initialized yet.",
            "tools": [],
            "server_name": "",
        }
        # In-process pipeline support
        self._activity_subscribers: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._run_threads: Dict[str, threading.Thread] = {}
        self._flush_managers: Dict[str, Any] = {}
        self._stream_sequences: Dict[str, int] = {}
        self._activity_event_traces: Dict[str, List[Dict[str, Any]]] = {}

    def create_session(self) -> Dict[str, str]:
        session_id = generate_session_id("gui")
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            now = self._timestamp_now()
            sessions = self._normalize_session_index(state.get("sessions"))
            sessions[session_id] = {
                "id": session_id,
                "title": "New modeling session",
                "updatedAt": now,
            }
            state["sessions"] = list(sessions.values())
            state["current_session_id"] = session_id
            workspaces = self._normalize_workspace_index(state.get("workspaces"))
            workspaces[session_id] = self._default_workspace_payload()
            state["workspaces"] = workspaces
            self._write_ui_state_unlocked(state)
        return {"session_id": session_id}

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        stop_result = self.stop_run(session_id)
        path = session_progress_path(self.runtime_root, session_id)
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            sessions = self._normalize_session_index(state.get("sessions"))
            sessions.pop(session_id, None)
            workspaces = self._normalize_workspace_index(state.get("workspaces"))
            workspaces.pop(session_id, None)
            if str(state.get("current_session_id", "")) == session_id:
                ordered_remaining = sorted(
                    sessions.values(),
                    key=lambda item: int(item.get("updatedAt", 0)),
                    reverse=True,
                )
                state["current_session_id"] = ordered_remaining[0]["id"] if ordered_remaining else ""
            state["sessions"] = list(sessions.values())
            state["workspaces"] = workspaces
            self._write_ui_state_unlocked(state)
        existed = path.exists()
        deleted_runtime_dir = delete_session_runtime_dir(self.runtime_root, session_id)
        self._activity_event_traces.pop(session_id, None)
        self.clear_activity_subscribers(session_id)
        return {
            "deleted": bool(existed or deleted_runtime_dir),
            "session_id": session_id,
            "stopped": bool(stop_result.get("stopped", False)),
            "reason": "" if (existed or deleted_runtime_dir) else "Session file not found.",
        }

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions_root = self.runtime_root / "session_data"
        sessions_root.mkdir(parents=True, exist_ok=True)
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            indexed = self._normalize_session_index(state.get("sessions"))
            workspaces = self._normalize_workspace_index(state.get("workspaces"))
        for path in sorted(sessions_root.glob("*/progress.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            data = self._read_json(path)
            session_id = str(data.get("session_id", path.parent.name))
            updated_at = int(path.stat().st_mtime)
            existing = indexed.get(session_id, {})
            workspace = workspaces.get(session_id, {})
            workspace_task = str(workspace.get("taskInput", "")).strip()
            existing_title = str(existing.get("title", "")).strip()
            progress_task = str(data.get("task", "")).strip()
            indexed[session_id] = {
                "id": session_id,
                "title": (
                    existing_title
                    if existing_title and existing_title != "Untitled session"
                    else workspace_task
                    or progress_task
                    or existing_title
                    or "Untitled session"
                ),
                "updatedAt": max(updated_at, int(existing.get("updatedAt", 0))),
            }
        return sorted(indexed.values(), key=lambda item: int(item.get("updatedAt", 0)), reverse=True)

    def get_session_workspace(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return {"exists": False, "workspace": self._default_workspace_payload()}
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            workspaces = self._normalize_workspace_index(state.get("workspaces"))
            workspace = workspaces.get(session_id)
        return {
            "exists": workspace is not None,
            "workspace": workspace or self._default_workspace_payload(),
        }

    def save_session_workspace(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not session_id:
            return {"saved": False, "reason": "session_id is required."}
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            workspaces = self._normalize_workspace_index(state.get("workspaces"))
            sessions = self._normalize_session_index(state.get("sessions"))
            existing = workspaces.get(session_id, self._default_workspace_payload())
            workspace = {
                "taskInput": str(payload.get("task_input", existing.get("taskInput", ""))),
                "referenceText": str(payload.get("reference_text", existing.get("referenceText", ""))),
                "referenceImages": [str(item) for item in payload.get("reference_images", existing.get("referenceImages", []))],
            }
            requested_title = str(payload.get("title", "")).strip()
            existing_title = str(sessions.get(session_id, {}).get("title", "Untitled session")).strip()
            title = requested_title or existing_title
            if title in {"", "Untitled session", "New modeling session"} and workspace["taskInput"].strip():
                title = workspace["taskInput"].strip()
            now = self._timestamp_now()
            workspaces[session_id] = workspace
            sessions[session_id] = {
                "id": session_id,
                "title": title,
                "updatedAt": now,
            }
            state["workspaces"] = workspaces
            state["sessions"] = list(sessions.values())
            state["current_session_id"] = session_id
            self._write_ui_state_unlocked(state)
        return {"saved": True, "session_id": session_id, "workspace": workspace}

    def append_activity(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not session_id:
            return {"saved": False, "reason": "session_id is required.", "activity": []}
        items = self._normalize_activity_items(payload.get("activity", []))
        if not items:
            return {"saved": True, "session_id": session_id, "activity": []}
        self._append_activity_history(session_id, items)
        return {"saved": True, "session_id": session_id, "activity": items, "server_cursor": self._compute_server_cursor(session_id)}

    def set_current_session(self, session_id: str) -> Dict[str, Any]:
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
            state["current_session_id"] = session_id
            self._write_ui_state_unlocked(state)
        return {"saved": True, "current_session_id": session_id}

    def load_settings(self) -> Dict[str, Any]:
        return load_gui_settings(self.runtime_root).to_dict()

    def save_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = GuiSavedSettings.from_dict(payload)
        path = save_gui_settings(self.runtime_root, settings)
        return {"saved": True, "path": str(path), "settings": settings.to_dict()}

    def _smoke_mcp_status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "state": "connected",
            "message": "Connected to Blender MCP (live bridge smoke mode).",
            "tools": [{"name": "get_objects_summary"}],
            "server_name": "blender",
            "initialize_result": {"ok": True, "mode": "live-bridge-smoke"},
        }

    def _smoke_agent_orchestrator_result(self, base_url: str) -> Dict[str, Any]:
        return {
            "name": "agent_orchestrator_health",
            "ok": True,
            "message": f"Agent Orchestrator is reachable at {base_url or 'http://127.0.0.1:4111'} (live bridge smoke mode).",
        }

    def _smoke_agent_orchestrator_ready_result(self, model: str) -> Dict[str, Any]:
        return {
            "ok": True,
            "checks": [
                {
                    "name": "agent_orchestrator_health",
                    "ok": True,
                    "message": "Agent Orchestrator health check passed (live bridge smoke mode).",
                },
                {
                    "name": "agent_orchestrator_conversation_ready",
                    "ok": True,
                    "message": f"Agent Orchestrator conversation can be prepared with model '{model or 'default'}' (live bridge smoke mode).",
                },
            ],
        }

    def connect_blender_mcp(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        _ = payload
        if self.live_bridge_smoke_mode:
            self.mcp_status = self._smoke_mcp_status()
            return dict(self.mcp_status)
        try:
            resolved = self._resolve_blender_mcp_client_config()
            client = SdkMCPClient(resolved["config"])
            initialize_result = client.initialize()
            tools = client.list_tools()
            self.mcp_status = {
                "enabled": True,
                "state": "connected",
                "message": "Connected to Blender MCP.",
                "tools": tools,
                "server_name": resolved["server_name"],
                "initialize_result": initialize_result,
            }
        except Exception as exc:
            self.mcp_status = {
                "enabled": True,
                "state": "failed",
                "message": str(exc),
                "tools": [],
                "server_name": "",
            }
        return dict(self.mcp_status)

    def disconnect_blender_mcp(self) -> Dict[str, Any]:
        self.mcp_status = {
            "enabled": True,
            "state": "idle",
            "message": "Blender MCP has not been initialized yet.",
            "tools": [],
            "server_name": "",
        }
        return dict(self.mcp_status)

    def get_blender_mcp_status(self) -> Dict[str, Any]:
        return dict(self.mcp_status)

    def read_progress(self, session_id: str) -> Dict[str, Any]:
        path = session_progress_path(self.runtime_root, session_id)
        if not path.exists():
            return {"exists": False, "progress": None}
        return {"exists": True, "progress": self._read_json(path)}

    def read_mcp_tool_calls(self, session_id: str, limit: int = 100) -> Dict[str, Any]:
        path = session_mcp_log_path(self.runtime_root, session_id)
        if not path.exists():
            return {"exists": False, "tool_calls": []}
        items: List[Dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return {"exists": True, "tool_calls": items}

    def read_console_log(self, session_id: str, limit_bytes: int = 20000) -> Dict[str, Any]:
        path = self.console_log_path(session_id)
        if not path.exists():
            return {"exists": False, "content": "", "path": str(path)}
        raw = path.read_text(encoding="utf-8", errors="replace")
        if limit_bytes > 0 and len(raw.encode("utf-8", errors="replace")) > limit_bytes:
            trimmed = raw.encode("utf-8", errors="replace")[-limit_bytes:].decode("utf-8", errors="replace")
            content = trimmed
        else:
            content = raw
        return {"exists": True, "content": content, "path": str(path)}

    def get_run_status(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return self._default_run_status("")
        return self._refresh_run_status(session_id)

    def run_live_diagnostics(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(payload.get("session_id", ""))
        effective_payload = self._merge_runtime_defaults(payload)

        if self.live_bridge_smoke_mode:
            ao_model = str(effective_payload.get("agent_orchestrator_model", "")).strip()
            ao_url = str(effective_payload.get("agent_orchestrator_base_url", "")).strip()
            self.mcp_status = self._smoke_mcp_status()
            return {
                "ok": True,
                "checks": [
                    self._smoke_agent_orchestrator_result(ao_url),
                    {
                        "name": "agent_orchestrator_conversation_ready",
                        "ok": True,
                        "message": f"Agent Orchestrator conversation can be prepared with model '{ao_model or 'default'}' (live bridge smoke mode).",
                    },
                    {
                        "name": "blender_mcp_connect",
                        "ok": True,
                        "message": "Connected to Blender MCP server 'blender' (live bridge smoke mode).",
                        "detail": {"tool_count": 1},
                    },
                    {
                        "name": "blender_mcp_tool_call",
                        "ok": True,
                        "message": "Executed get_objects_summary through Blender MCP (live bridge smoke mode).",
                    },
                ],
            }

        checks: List[Dict[str, Any]] = []

        checks = self.verifyAgentOrchestratorLive(effective_payload)["checks"]

        try:
            resolved = self._resolve_blender_mcp_client_config(session_id)
            client = SdkMCPClient(resolved["config"])
            initialize_result = client.initialize()
            tools = client.list_tools()
            context_result = client.call_tool("get_objects_summary", {})
            checks.append(
                {
                    "name": "blender_mcp_connect",
                    "ok": True,
                    "message": f"Connected to Blender MCP server '{resolved['server_name']}'.",
                    "detail": {
                        "initialize_result": initialize_result,
                        "tool_count": len(tools),
                    },
                }
            )
            checks.append(
                {
                    "name": "blender_mcp_tool_call",
                    "ok": not bool(context_result.get("isError", False)),
                    "message": "Executed get_objects_summary through Blender MCP.",
                }
            )
            self.mcp_status = {
                "enabled": True,
                "state": "connected",
                "message": "Connected to Blender MCP.",
                "tools": tools,
                "server_name": resolved["server_name"],
                "initialize_result": initialize_result,
            }
        except Exception as exc:
            checks.append(
                {
                    "name": "blender_mcp_connect",
                    "ok": False,
                    "message": str(exc),
                }
            )
            self.mcp_status = {
                "enabled": True,
                "state": "failed",
                "message": str(exc),
                "tools": [],
                "server_name": "",
            }

        return {
            "ok": all(bool(item.get("ok", False)) for item in checks),
            "checks": checks,
        }

    def verifyAgentOrchestratorLive(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        effective_payload = self._merge_runtime_defaults(payload)
        base_url = str(effective_payload.get("agent_orchestrator_base_url", "")).strip()
        model = str(effective_payload.get("agent_orchestrator_model", "")).strip()

        if self.live_bridge_smoke_mode:
            return self._smoke_agent_orchestrator_ready_result(model)

        checks: List[Dict[str, Any]] = []
        if base_url:
            try:
                client = AgentOrchestratorClient(
                    AgentOrchestratorConfig(
                        base_url=base_url,
                        model=model,
                        conversation_id=str(effective_payload.get("agent_orchestrator_conversation_id", "")),
                        destroy_on_finish=bool(effective_payload.get("agent_orchestrator_destroy_on_finish", True)),
                        timeout_seconds=int(effective_payload.get("agent_orchestrator_timeout_seconds", 120)),
                    ),
                )
                client.health()
                checks.append(
                    {
                        "name": "agent_orchestrator_health",
                        "ok": True,
                        "message": f"Agent Orchestrator is reachable at {base_url}.",
                    }
                )
                checks.append(
                    {
                        "name": "agent_orchestrator_conversation_ready",
                        "ok": True,
                        "message": f"Agent Orchestrator model '{model or 'default'}' is configured.",
                    }
                )
            except Exception as exc:
                checks.append(
                    {
                        "name": "agent_orchestrator_health",
                        "ok": False,
                        "message": str(exc),
                    }
                )
        else:
            checks.append(
                {
                    "name": "agent_orchestrator_health",
                    "ok": False,
                    "message": "Agent Orchestrator URL is empty.",
                }
            )

        return {
            "ok": all(bool(item.get("ok", False)) for item in checks),
            "checks": checks,
        }

    def verifyAgentOrchestratorEndpoint(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = self.verifyAgentOrchestratorLive(payload)
        first = result["checks"][0] if result.get("checks") else {}
        return {
            "name": str(first.get("name", "agent_orchestrator_health")),
            "ok": bool(first.get("ok", False)),
            "message": str(first.get("message", "")),
            "detail": first.get("detail", {}),
        }

    def listAgentOrchestratorModels(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        effective_payload = self._merge_runtime_defaults(payload)
        base_url = str(effective_payload.get("agent_orchestrator_base_url", "")).strip()
        project_models = self._project_agent_orchestrator_models()
        if self.live_bridge_smoke_mode:
            return {
                "ok": True,
                "models": self._merge_agent_orchestrator_models(
                    [
                        {"id": "openai/gpt-5", "provider": "openai", "model": "gpt-5"},
                        {"id": "anthropic/claude-3-5-sonnet", "provider": "anthropic", "model": "claude-3-5-sonnet"},
                    ],
                    project_models,
                ),
                "message": "Agent Orchestrator model list loaded (live bridge smoke mode).",
            }
        if not base_url:
            return {
                "ok": False,
                "models": project_models,
                "message": "Agent Orchestrator URL is empty.",
            }
        try:
            client = AgentOrchestratorClient(
                AgentOrchestratorConfig(
                    base_url=base_url,
                    model="",
                    conversation_id="",
                    destroy_on_finish=True,
                    timeout_seconds=int(effective_payload.get("agent_orchestrator_timeout_seconds", 120)),
                ),
            )
            models = self._merge_agent_orchestrator_models(client.list_models(), project_models)
            return {
                "ok": True,
                "models": models,
                "message": f"Loaded {len(models)} Agent Orchestrator models.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "models": project_models,
                "message": str(exc),
            }

    def _project_agent_orchestrator_models(self) -> List[Dict[str, str]]:
        config_path = self.repo_root / ".opencode" / "opencode.json"
        if not config_path.exists():
            return []
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        provider_config = config.get("provider") if isinstance(config, dict) else None
        if not isinstance(provider_config, dict):
            return []
        models: List[Dict[str, str]] = []
        for provider_id, provider in provider_config.items():
            if not isinstance(provider_id, str) or not isinstance(provider, dict):
                continue
            provider_models = provider.get("models")
            if not isinstance(provider_models, dict):
                continue
            for model_id, model_info in provider_models.items():
                if not isinstance(model_id, str):
                    continue
                model_name = model_id
                if isinstance(model_info, dict):
                    model_name = str(model_info.get("name") or model_id)
                models.append(
                    {
                        "id": f"{provider_id}/{model_id}",
                        "provider": provider_id,
                        "model": model_id,
                        "name": model_name,
                    }
                )
        return models

    def _merge_agent_orchestrator_models(
        self,
        primary: List[Dict[str, Any]],
        project_models: List[Dict[str, str]],
    ) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for model in [*primary, *project_models]:
            model_id = str(model.get("id", "")).strip()
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            merged.append(dict(model))
        return merged

    def bootstrap(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        self._refresh_mcp_status_best_effort()
        with self.ui_state_lock:
            state = self._read_ui_state_unlocked()
        sessions = self.list_sessions()
        saved_current_session_id = str(state.get("current_session_id", ""))
        resolved_session_id = (
            session_id
            or saved_current_session_id
            or (sessions[0]["id"] if sessions else "")
        )
        return {
            "sessions": sessions,
            "current_session_id": resolved_session_id,
            "settings": self.load_settings(),
            "mcp_status": self.get_blender_mcp_status(),
        }

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        resolved_status = self.get_run_status(session_id)
        workspace = self.get_session_workspace(session_id)
        progress_payload = self.read_progress(session_id).get("progress") or self._default_progress_payload()
        latest_meeting_state = self.select_latest_meeting_state(session_id)
        meeting_states = self.load_all_phase_meeting_states(session_id)
        plan_artifact = self.load_plan_artifact(session_id)
        build_execution_plan = self.load_build_execution_plan(session_id)
        assembly_execution_plan = self.load_assembly_execution_plan(session_id)
        failure_triage = self._build_failure_triage(
            session_id,
            run_status=resolved_status,
            plan_artifact=plan_artifact,
            build_execution_plan=build_execution_plan,
            assembly_execution_plan=assembly_execution_plan,
        )
        return {
            "session_id": session_id,
            "workspace": workspace.get("workspace", self._default_workspace_payload()),
            "activity": self._read_activity_history(session_id),
            "progress": progress_payload,
            "run_status": resolved_status,
            "console_log": self.read_console_log(session_id).get("content", ""),
            "mcp_tool_calls": self.read_mcp_tool_calls(session_id).get("tool_calls", []),
            "mcp_status": self.get_blender_mcp_status(),
            "retry_prompt": self._build_retry_prompt(session_id, resolved_status),
            "meeting_state": latest_meeting_state,
            "meeting_states": meeting_states,
            "plan_artifact": plan_artifact,
            "build_execution_plan": build_execution_plan,
            "assembly_execution_plan": assembly_execution_plan,
            "failure_triage": failure_triage,
            "server_cursor": self._compute_server_cursor(session_id, resolved_status),
            "snapshot_generated_at": int(time.time()),
        }

    def get_activity_snapshot(self, session_id: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        _ = cursor
        return self.get_session_state(session_id)

    def get_activity_truth_timeline(self, session_id: str) -> Dict[str, Any]:
        snapshot = self.get_session_state(session_id)
        return {
            "session_id": session_id,
            "snapshot": snapshot,
            "activity": snapshot.get("activity", []),
            "meeting_state": snapshot.get("meeting_state"),
            "meeting_states": snapshot.get("meeting_states", []),
            "plan_artifact": snapshot.get("plan_artifact"),
            "build_execution_plan": snapshot.get("build_execution_plan"),
            "assembly_execution_plan": snapshot.get("assembly_execution_plan"),
            "server_cursor": snapshot.get("server_cursor", ""),
            "snapshot_generated_at": snapshot.get("snapshot_generated_at", int(time.time())),
        }

    def get_meeting_state_truth(self, session_id: str) -> Dict[str, Any]:
        latest_state = self.select_latest_meeting_state(session_id)
        all_states = self.load_all_phase_meeting_states(session_id)
        return {
            "session_id": session_id,
            "meeting_state": latest_state,
            "meeting_states": all_states,
            "latest_phase_name": str((latest_state or {}).get("phase_name", "")),
            "latest_phase_status": str((latest_state or {}).get("phase_status", "")),
            "latest_resolution_summary": str((latest_state or {}).get("last_resolution_summary", "")),
            "snapshot_generated_at": int(time.time()),
        }

    def get_planning_truth(self, session_id: str) -> Dict[str, Any]:
        latest_state = self.select_latest_meeting_state(session_id)
        plan_state = self.load_phase_meeting_state(session_id, "plan")
        plan_artifact = self.load_plan_artifact(session_id)
        build_execution_plan = self.load_build_execution_plan(session_id)
        assembly_execution_plan = self.load_assembly_execution_plan(session_id)
        effective_state = plan_state or latest_state
        failure_triage = self._build_failure_triage(
            session_id,
            plan_artifact=plan_artifact,
            build_execution_plan=build_execution_plan,
            assembly_execution_plan=assembly_execution_plan,
        )
        return {
            "session_id": session_id,
            "plan_meeting_state": plan_state,
            "meeting_state": effective_state,
            "plan_artifact": plan_artifact,
            "build_execution_plan": build_execution_plan,
            "assembly_execution_plan": assembly_execution_plan,
            "latest_phase_name": str((effective_state or {}).get("phase_name", "")),
            "latest_phase_status": str((effective_state or {}).get("phase_status", "")),
            "latest_resolution_summary": str((effective_state or {}).get("last_resolution_summary", "")),
            "accepted_decisions": list((effective_state or {}).get("accepted_decisions", []) or []),
            "open_issues": list((effective_state or {}).get("open_issues", []) or []),
            "failure_triage": failure_triage,
            "latest_planning_warnings": list(failure_triage.get("planning_warnings", []) or []),
            "latest_planning_failures": list(failure_triage.get("planning_failures", []) or []),
            "latest_failure_category": str(failure_triage.get("failure_category", "")),
            "build_fallback_usage": bool(failure_triage.get("build_used_fallback", False)),
            "assembly_fallback_usage": bool(failure_triage.get("assembly_used_fallback", False)),
            "snapshot_generated_at": int(time.time()),
        }

    def get_activity_event_trace(self, session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "events": deepcopy(self._activity_event_traces.get(session_id, [])),
            "server_cursor": self._compute_server_cursor(session_id),
            "snapshot_generated_at": int(time.time()),
        }

    def get_runtime_truth(self, session_id: str) -> Dict[str, Any]:
        resolved_status = self.get_run_status(session_id)
        return {
            "session_id": session_id,
            "run_status": resolved_status,
            "console_log": self.read_console_log(session_id).get("content", ""),
            "mcp_tool_calls": self.read_mcp_tool_calls(session_id).get("tool_calls", []),
            "mcp_status": self.get_blender_mcp_status(),
            "snapshot_generated_at": int(time.time()),
        }

    def get_inspector_truth(self, session_id: str) -> Dict[str, Any]:
        snapshot = self.get_session_state(session_id)
        progress = snapshot.get("progress") or {}
        selection = self._default_inspector_selection(progress)
        return {
            "session_id": session_id,
            "progress": progress,
            "summary": self._build_inspector_summary(progress),
            "selection_kind": str(selection.get("kind", "none")),
            "latest_capture": self._latest_capture_path(selection),
            "final_validation_capture": self._final_validation_capture_path(progress),
            "selected_task_title": self._selected_task_title(selection),
            "inspector_blocks": self._build_inspector_blocks(selection),
            "snapshot_generated_at": snapshot.get("snapshot_generated_at", int(time.time())),
        }

    def get_retry_truth(self, session_id: str) -> Dict[str, Any]:
        snapshot = self.get_session_state(session_id)
        pending_interaction = self._read_pending_interaction(session_id)
        return {
            "session_id": session_id,
            "run_status": snapshot.get("run_status", self._default_run_status(session_id)),
            "retry_prompt": snapshot.get("retry_prompt", self._build_retry_prompt(session_id, snapshot.get("run_status", {}))),
            "pending_interaction": pending_interaction,
            "progress": snapshot.get("progress"),
            "activity": snapshot.get("activity", []),
            "failure_triage": snapshot.get("failure_triage", {}),
            "failure_category": str((snapshot.get("failure_triage") or {}).get("failure_category", "")),
            "planning_summary": str((pending_interaction or {}).get("planning_summary", "")),
            "blocking_constraint_refs": list((pending_interaction or {}).get("blocking_constraint_refs", []) or []),
            "server_cursor": snapshot.get("server_cursor", self._compute_server_cursor(session_id)),
            "snapshot_generated_at": snapshot.get("snapshot_generated_at", int(time.time())),
        }

    def build_activity_stream_payload(self, session_id: str) -> Dict[str, Any]:
        return self.get_activity_snapshot(session_id)

    def start_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(payload.get("session_id", ""))
        self.last_run_payloads[session_id] = deepcopy(payload)
        self._activity_event_traces[session_id] = []
        return self.start_inprocess_run(payload)

    def retry_run(self, session_id: str, retry_count: int) -> Dict[str, Any]:
        payload = deepcopy(self.last_run_payloads.get(session_id, {}))
        if not payload:
            return {
                "started": False,
                "session_id": session_id,
                "error_message": "No previous run configuration found for this session.",
                "run_status": self.get_run_status(session_id),
            }
        retry_total = max(1, int(retry_count))
        with self.process_lock:
            self.retry_plans[session_id] = {
                "remaining_retries": max(0, retry_total - 1),
                "requested_retries": retry_total,
                "decision_state": "retrying",
                "last_failure_reason": "",
            }
        pending = self._read_pending_interaction(session_id)
        if pending:
            pending["status"] = "resolved"
            pending["resolved_action"] = f"retry_{retry_total}"
            pending["resolved_at"] = int(time.time())
            self._write_pending_interaction(session_id, pending)
        return self.start_inprocess_run(payload)

    def clear_retry_prompt(self, session_id: str) -> Dict[str, Any]:
        with self.process_lock:
            plan = dict(self.retry_plans.get(session_id, {}))
            plan["remaining_retries"] = 0
            plan["decision_state"] = "stopped"
            self.retry_plans[session_id] = plan
        pending = self._read_pending_interaction(session_id)
        if pending:
            pending["status"] = "resolved"
            pending["resolved_action"] = "stop"
            pending["resolved_at"] = int(time.time())
            self._write_pending_interaction(session_id, pending)
        return {"saved": True, "session_id": session_id}

    def _start_run_from_payload(self, payload: Dict[str, Any], is_retry: bool = False) -> Dict[str, Any]:
        command: List[str] = []
        effective_payload = self._merge_runtime_defaults(payload)
        config = GuiLaunchConfig(
            task=str(effective_payload["task"]),
            session_id=str(effective_payload["session_id"]),
            agent_orchestrator_base_url=str(effective_payload["agent_orchestrator_base_url"]),
            agent_orchestrator_model=str(effective_payload.get("agent_orchestrator_model", "")),
            agent_orchestrator_conversation_id=str(effective_payload.get("agent_orchestrator_conversation_id", "")),
            agent_orchestrator_destroy_on_finish=bool(effective_payload.get("agent_orchestrator_destroy_on_finish", True)),
            agent_orchestrator_timeout_seconds=int(effective_payload.get("agent_orchestrator_timeout_seconds", 120)),
            reference_texts=[str(item) for item in effective_payload.get("reference_texts", [])],
            reference_images=[str(item) for item in effective_payload.get("reference_images", [])],
            max_part_refinement_rounds=int(effective_payload.get("max_part_refinement_rounds", 3)),
            max_assembly_rounds=int(effective_payload.get("max_assembly_rounds", 3)),
            use_blender_mcp=True,
            use_yolo_perception=bool(effective_payload.get("use_yolo_perception", False)),
            yolo_model_path=str(effective_payload.get("yolo_model_path", "")),
            yolo_viewpoints=[str(item) for item in effective_payload.get("yolo_viewpoints", [])],
        )
        try:
            resolved = self._resolve_blender_mcp_client_config(config.session_id)
            config.blender_mcp_command = resolved["config"].command
            config.blender_mcp_cwd = resolved["config"].cwd or ""
            config.blender_mcp_args = list(resolved["config"].args)
            config.blender_mcp_env = dict(resolved["config"].env)
            if self.connect_blender_mcp({}).get("state") != "connected":
                raise RuntimeError(self.mcp_status.get("message", "Blender MCP must be connected before starting."))

            self.save_session_workspace(
                config.session_id,
                {
                    "task_input": config.task,
                    "reference_text": "\n".join(config.reference_texts),
                    "reference_images": config.reference_images,
                    "title": config.task or "Untitled session",
                },
            )
            ensure_session_runtime_dir(self.runtime_root, config.session_id)
            command = build_multi_stage_command(self.repo_root, config)
            with self.process_lock:
                self.run_statuses[config.session_id] = {
                    "session_id": config.session_id,
                    "workflow_status": "starting",
                    "process_status": "launching",
                    "error_message": "",
                    "last_command": command,
                    "pid": None,
                    "exit_code": None,
                    "attempt_index": self._next_attempt_index(config.session_id),
                }
            self._clear_pending_interaction(config.session_id)
            console_log_path = self.console_log_path(config.session_id)
            console_log_path.parent.mkdir(parents=True, exist_ok=True)
            if not is_retry:
                console_log_path.write_text("", encoding="utf-8")
            console_log_handle = console_log_path.open("a", encoding="utf-8")
            if is_retry:
                console_log_handle.write("\n=== RETRY ATTEMPT START ===\n")
                console_log_handle.flush()
            process = subprocess.Popen(
                command,
                cwd=str(self.repo_root),
                stdout=console_log_handle,
                stderr=subprocess.STDOUT,
            )
            with self.process_lock:
                self.processes[config.session_id] = process
                self.process_log_handles[config.session_id] = console_log_handle
                attempt_index = int(self.run_statuses[config.session_id].get("attempt_index", 1))
                self.run_statuses[config.session_id] = {
                    "session_id": config.session_id,
                    "workflow_status": "running",
                    "process_status": "running",
                    "error_message": "",
                    "last_command": command,
                    "pid": process.pid,
                    "exit_code": None,
                    "attempt_index": attempt_index,
                }
            return {
                "started": True,
                "session_id": config.session_id,
                "pid": process.pid,
                "command": command,
                "run_status": self._refresh_run_status(config.session_id),
            }
        except Exception as exc:
            with self.process_lock:
                self.run_statuses[config.session_id] = {
                    "session_id": config.session_id,
                    "workflow_status": "failed",
                    "process_status": "error",
                    "error_message": str(exc),
                    "last_command": command,
                    "pid": None,
                    "exit_code": None,
                    "attempt_index": self._next_attempt_index(config.session_id),
                }
            return {
                "started": False,
                "session_id": config.session_id,
                "pid": None,
                "command": command,
                "error_message": str(exc),
                "run_status": self._refresh_run_status(config.session_id),
            }

    # ── In-process pipeline support ─────────────────────────────────

    def start_inprocess_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Start a pipeline run in-process (threaded, not subprocess)."""
        session_id = str(payload.get("session_id", ""))
        task = str(payload.get("task", ""))

        if not session_id or not task:
            return {"started": False, "error_message": "Missing session_id or task"}
        if self.live_bridge_smoke_mode:
            return self._start_live_bridge_smoke_run(payload)
        try:
            self._resolve_blender_mcp_client_config(session_id)
            if self.connect_blender_mcp({}).get("state") != "connected":
                raise RuntimeError(self.mcp_status.get("message", "Blender MCP must be connected before starting."))
        except Exception as exc:
            status = {
                "session_id": session_id,
                "workflow_status": "failed",
                "process_status": "error",
                "error_message": str(exc),
                "last_command": [f"inprocess:{task[:50]}"],
                "pid": None,
                "exit_code": None,
                "attempt_index": self._next_attempt_index(session_id),
            }
            with self.process_lock:
                self.run_statuses[session_id] = status
            return {
                "started": False,
                "session_id": session_id,
                "error_message": str(exc),
                "run_status": status,
            }

        # Setup
        ensure_session_runtime_dir(self.runtime_root, session_id)
        self._clear_pending_interaction(session_id)

        with self.process_lock:
            self.run_statuses[session_id] = {
                "session_id": session_id,
                "workflow_status": "starting",
                "process_status": "launching",
                "error_message": "",
                "last_command": f"inprocess:{task[:50]}",
                "pid": None,
                "exit_code": None,
                "attempt_index": self._next_attempt_index(session_id),
            }

        # Create buffers
        session_dir = self.runtime_root / "session_data" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        from ai_3d_modeling_agent.io.buffered_writer import BufferedWriter
        from ai_3d_modeling_agent.io.flush_manager import FlushManager

        meetings_buffer = BufferedWriter(session_dir / "meetings.jsonl")

        # Create console log file for in-process runs
        console_log_path = self.console_log_path(session_id)
        console_log_path.parent.mkdir(parents=True, exist_ok=True)
        console_log_path.write_text("", encoding="utf-8")

        flush_mgr = FlushManager(interval=5.0)
        flush_mgr.register(meetings_buffer)
        self._flush_managers[session_id] = flush_mgr

        # Event callback → WebSocket queue
        def on_event(event: Dict[str, Any]) -> None:
            print(f"[BRIDGE] Event emitted: {event.get('kind', 'unknown')} → queue", flush=True)
            if not event.get("event_id"):
                event["event_id"] = f"meeting-{session_id}-{self._next_stream_sequence(session_id)}"
            activity_items = self._activity_items_from_meeting_event(event)
            if activity_items:
                self._append_activity_history(session_id, activity_items)
            self.publish_activity_stream_event(
                session_id,
                self._make_stream_event(session_id, "meeting_event", event),
            )

        # Start thread
        thread = threading.Thread(
            target=self._run_inprocess_thread,
            args=(session_id, payload, on_event, meetings_buffer, flush_mgr),
            daemon=True,
        )
        thread.start()
        self._run_threads[session_id] = thread

        return {
            "started": True,
            "session_id": session_id,
            "pid": None,
            "command": f"inprocess:{task[:50]}",
            "run_status": self._refresh_run_status(session_id),
        }

    def _start_live_bridge_smoke_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        session_id = str(payload.get("session_id", ""))
        task = str(payload.get("task", ""))
        ensure_session_runtime_dir(self.runtime_root, session_id)
        self.connect_blender_mcp({})
        self.save_session_workspace(
            session_id,
            {
                "task_input": task,
                "reference_text": "\n".join(str(item) for item in payload.get("reference_texts", [])),
                "reference_images": [str(item) for item in payload.get("reference_images", [])],
                "title": task or "Untitled session",
            },
        )
        attempt_index = self._next_attempt_index(session_id)
        with self.process_lock:
            self.run_statuses[session_id] = {
                "session_id": session_id,
                "workflow_status": "running",
                "process_status": "running",
                "error_message": "",
                "last_command": f"smoke-inprocess:{task[:50]}",
                "pid": None,
                "exit_code": None,
                "attempt_index": attempt_index,
            }
        self._clear_pending_interaction(session_id)
        console_log_path = self.console_log_path(session_id)
        console_log_path.parent.mkdir(parents=True, exist_ok=True)
        if attempt_index <= 1:
            console_log_path.write_text("", encoding="utf-8")
        else:
            self._append_console_marker(session_id, "\n=== RETRY ATTEMPT START ===\n")
        thread = threading.Thread(
            target=self._run_live_bridge_smoke_thread,
            args=(session_id, task, attempt_index),
            daemon=True,
        )
        thread.start()
        self._run_threads[session_id] = thread
        return {
            "started": True,
            "session_id": session_id,
            "pid": None,
            "command": f"smoke-inprocess:{task[:50]}",
            "run_status": self._refresh_run_status(session_id),
        }

    def _run_live_bridge_smoke_thread(self, session_id: str, task: str, attempt_index: int) -> None:
        try:
            self._append_console_marker(
                session_id,
                f"Mock multi-expert run started\nTask: {task}\nAO readiness: smoke-ready\n",
            )
            self._write_smoke_progress(session_id, task, status="running", stage="design", stage_status="running")
            self._emit_smoke_meeting_event(
                session_id,
                {
                    "event_id": f"{session_id}:design:phase_start:{attempt_index}",
                    "phase": "design",
                    "kind": "phase_start",
                    "message": "Design meeting started",
                    "summary": "Design meeting started",
                    "timestamp": time.strftime("%H:%M"),
                },
            )
            self._emit_smoke_meeting_event(
                session_id,
                {
                    "event_id": f"{session_id}:design:proposal:{attempt_index}",
                    "phase": "design",
                    "kind": "proposal",
                    "speaker": "moderator",
                    "summary": "AO moderator accepted a simple chair design with Seat and Legs.",
                    "full_content": "AO moderator accepted a simple chair design with Seat and Legs.",
                    "message": "AO moderator accepted a simple chair design with Seat and Legs.",
                    "timestamp": time.strftime("%H:%M"),
                },
            )
            time.sleep(0.8)
            is_retry_failure_seed = "[retry-smoke]" in task and attempt_index <= 1
            if is_retry_failure_seed:
                failure_reason = "Validation failed for seat; waiting for retry decision"
                self._write_smoke_progress(
                    session_id,
                    task,
                    status="failed",
                    stage="build",
                    stage_status="failed",
                    stop_reason=failure_reason,
                )
                self._append_console_marker(
                    session_id,
                    f"Mock retry smoke failure triggered\n{failure_reason}\n",
                )
                with self.process_lock:
                    self.run_statuses[session_id] = {
                        **self.run_statuses.get(session_id, self._default_run_status(session_id)),
                        "workflow_status": "failed",
                        "process_status": "failed",
                        "error_message": failure_reason,
                        "exit_code": 1,
                    }
                self._write_pending_interaction(
                    session_id,
                    {
                        "interaction_id": f"retry-{sanitize_session_id(session_id)}-{int(time.time())}",
                        "session_id": session_id,
                        "kind": "retry_decision",
                        "status": "pending",
                        "prompt": "This run failed. Choose whether to retry.",
                        "failure_reason": failure_reason,
                        "failure_category": "validation",
                        "planning_summary": "Smoke retry seed intentionally failed the first attempt.",
                        "blocking_constraint_refs": [],
                        "attempt_index": attempt_index,
                        "next_attempt_index": attempt_index + 1,
                        "remaining_retries": 0,
                        "suggested_options": [1, 3, 0],
                        "created_at": int(time.time()),
                        "resolved_at": None,
                    },
                )
                return

            self._write_smoke_progress(session_id, task, status="running", stage="build", stage_status="running")
            self._emit_smoke_meeting_event(
                session_id,
                {
                    "event_id": f"{session_id}:build:step:{attempt_index}",
                    "phase": "build",
                    "kind": "build_step",
                    "message": "Builder produced Markdown intents and Python executed the Blender MCP todos.",
                    "summary": "Builder produced Markdown intents and Python executed the Blender MCP todos.",
                    "timestamp": time.strftime("%H:%M"),
                },
            )
            time.sleep(4.0)
            self._write_smoke_progress(
                session_id,
                task,
                status="completed",
                stage="completed",
                stage_status="completed",
            )
            self._append_console_marker(session_id, "Mock multi-expert run completed\n")
            with self.process_lock:
                plan = dict(self.retry_plans.get(session_id, {}))
                if plan:
                    plan["decision_state"] = "completed"
                    plan["remaining_retries"] = 0
                    self.retry_plans[session_id] = plan
                self.run_statuses[session_id] = {
                    **self.run_statuses.get(session_id, self._default_run_status(session_id)),
                    "workflow_status": "completed",
                    "process_status": "completed",
                    "error_message": "",
                    "exit_code": 0,
                }
            self._clear_pending_interaction(session_id)
        except Exception as exc:
            with self.process_lock:
                self.run_statuses[session_id] = {
                    **self.run_statuses.get(session_id, self._default_run_status(session_id)),
                    "workflow_status": "failed",
                    "process_status": "error",
                    "error_message": str(exc),
                    "exit_code": 1,
                }

    def _write_smoke_progress(
        self,
        session_id: str,
        task: str,
        *,
        status: str,
        stage: str,
        stage_status: str,
        stop_reason: str = "",
    ) -> None:
        progress = self._default_progress_payload()
        progress.update(
            {
                "session_id": session_id,
                "status": status,
                "task": task,
                "stage": stage,
                "stage_status": stage_status,
                "multi_expert_mode": True,
                "completed_task_ids": ["seat", "legs"] if status == "completed" else [],
                "stop_reason": stop_reason,
            }
        )
        if status == "completed":
            progress["part_tasks"] = [
                {
                    "task_id": "seat",
                    "title": "Seat",
                    "object_name": "seat",
                    "status": "approved",
                    "current_round": 1,
                    "approved": True,
                    "hidden_after_approval": False,
                    "rounds": [],
                },
                {
                    "task_id": "legs",
                    "title": "Legs",
                    "object_name": "legs",
                    "status": "approved",
                    "current_round": 1,
                    "approved": True,
                    "hidden_after_approval": False,
                    "rounds": [],
                },
            ]
            progress["assembly"] = {
                "status": "completed",
                "current_round": 1,
                "approved": True,
                "all_parts_visible": True,
                "initial_placement_applied": True,
                "rounds": [],
            }
            progress["final_validation"] = {
                "status": "completed",
                "capture_path": "",
                "viewpoint": "front",
                "detected_parts": ["Seat", "Legs"],
                "missing_critical_parts": [],
                "quantitative_metrics": [],
            }
        path = session_progress_path(self.runtime_root, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(progress, ensure_ascii=False, indent=2)
        for attempt in range(10):
            try:
                path.write_text(serialized, encoding="utf-8")
                return
            except OSError:
                if attempt == 9:
                    raise
                time.sleep(0.05)

    def _emit_smoke_meeting_event(self, session_id: str, event: Dict[str, Any]) -> None:
        path = session_meetings_log_path(self.runtime_root, session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False))
            file.write("\n")
        activity_items = self._activity_items_from_meeting_event(event)
        if activity_items:
            self._append_activity_history(session_id, activity_items)
        self.publish_activity_stream_event(session_id, self._make_stream_event(session_id, "meeting_event", event))

    def _run_inprocess_thread(
        self,
        session_id: str,
        payload: Dict[str, Any],
        on_event: Callable,
        meetings_buffer: Any,
        flush_mgr: Any,
    ) -> None:
        """Run the pipeline in a background thread."""
        import sys

        flush_mgr.start()

        # Create a Tee writer that writes to both original stdout and the console log file
        console_log_path = self.console_log_path(session_id)
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        class TeeWriter:
            def __init__(self, file_path, original_stream):
                self.file_path = file_path
                self.original = original_stream

            def write(self, text):
                try:
                    with open(self.file_path, "a", encoding="utf-8", errors="replace") as f:
                        f.write(text)
                        f.flush()
                except Exception:
                    pass
                self.original.write(text)
                self.original.flush()

            def flush(self):
                self.original.flush()

            def fileno(self):
                return self.original.fileno()

        try:
            tee = TeeWriter(console_log_path, original_stdout)
            sys.stdout = tee
            sys.stderr = tee
            effective_payload = self._merge_runtime_defaults(payload)

            from ai_3d_modeling_agent.pipelines.runners import run_pipeline

            with self.process_lock:
                current = self.run_statuses.get(session_id, {})
                self.run_statuses[session_id] = {
                    **current,
                    "workflow_status": "running",
                    "process_status": "running",
                }

            resolved_mcp = self._resolve_blender_mcp_client_config(session_id)
            result = run_pipeline(
                task=str(effective_payload.get("task", "")),
                session_id=session_id,
                use_blender_mcp=True,
                blender_mcp_command=resolved_mcp["config"].command,
                blender_mcp_cwd=resolved_mcp["config"].cwd or "",
                blender_mcp_args=list(resolved_mcp["config"].args),
                blender_mcp_env=dict(resolved_mcp["config"].env),
                agent_orchestrator_base_url=str(effective_payload.get("agent_orchestrator_base_url", "")),
                agent_orchestrator_model=str(effective_payload.get("agent_orchestrator_model", "")),
                agent_orchestrator_conversation_id=str(effective_payload.get("agent_orchestrator_conversation_id", "")),
                agent_orchestrator_destroy_on_finish=bool(effective_payload.get("agent_orchestrator_destroy_on_finish", True)),
                agent_orchestrator_timeout_seconds=int(effective_payload.get("agent_orchestrator_timeout_seconds", 120)),
                event_callback=on_event,
                event_buffer=meetings_buffer,
            )

            with self.process_lock:
                self.run_statuses[session_id] = {
                    **self.run_statuses.get(session_id, {}),
                    "workflow_status": "completed",
                    "process_status": "completed",
                    "exit_code": 0,
                }
        except Exception as exc:
            with self.process_lock:
                self.run_statuses[session_id] = {
                    **self.run_statuses.get(session_id, {}),
                    "workflow_status": "failed",
                    "process_status": "error",
                    "error_message": str(exc),
                    "exit_code": 1,
                }
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            flush_mgr.stop()

    def register_activity_subscriber(self, session_id: str, connection_id: str) -> queue.Queue:
        subscriber_queue: queue.Queue = queue.Queue()
        with self.stream_lock:
            subscribers = self._activity_subscribers.setdefault(session_id, {})
            subscribers[connection_id] = {
                "queue": subscriber_queue,
                "created_at": time.time(),
                "closed": False,
            }
        return subscriber_queue

    def unregister_activity_subscriber(self, session_id: str, connection_id: str) -> None:
        with self.stream_lock:
            subscribers = self._activity_subscribers.get(session_id)
            if not subscribers:
                return
            subscriber = subscribers.pop(connection_id, None)
            if isinstance(subscriber, dict):
                subscriber["closed"] = True
            if not subscribers:
                self._activity_subscribers.pop(session_id, None)

    def clear_activity_subscribers(self, session_id: str) -> None:
        with self.stream_lock:
            subscribers = self._activity_subscribers.pop(session_id, {})
            for subscriber in subscribers.values():
                if isinstance(subscriber, dict):
                    subscriber["closed"] = True

    def publish_activity_stream_event(self, session_id: str, event: Dict[str, Any]) -> int:
        if not session_id:
            return 0
        self.record_activity_stream_event(session_id, event)
        delivered = 0
        with self.stream_lock:
            subscribers = dict(self._activity_subscribers.get(session_id, {}))
        for subscriber in subscribers.values():
            subscriber_queue = subscriber.get("queue") if isinstance(subscriber, dict) else None
            if not isinstance(subscriber_queue, queue.Queue):
                continue
            subscriber_queue.put(deepcopy(event))
            delivered += 1
        return delivered

    def get_activity_subscriber_count(self, session_id: str) -> int:
        with self.stream_lock:
            return len(self._activity_subscribers.get(session_id, {}))

    def record_activity_stream_event(self, session_id: str, event: Dict[str, Any], limit: int = 200) -> None:
        if not session_id:
            return
        with self.stream_lock:
            trace = self._activity_event_traces.setdefault(session_id, [])
            trace.append(deepcopy(event))
            if len(trace) > limit:
                del trace[:-limit]

    def stop_run(self, session_id: str) -> Dict[str, Any]:
        with self.process_lock:
            process = self.processes.get(session_id)
        if process is None:
            status = self._refresh_run_status(session_id)
            return {"stopped": False, "reason": "No active process for session.", "run_status": status}
        if process.poll() is not None:
            self._close_process_log_handle(session_id)
            with self.process_lock:
                self.processes.pop(session_id, None)
            status = self._refresh_run_status(session_id)
            return {"stopped": False, "reason": "Process already finished.", "run_status": status}
        with self.process_lock:
            current = self.run_statuses.get(session_id, self._default_run_status(session_id))
            self.run_statuses[session_id] = {
                **current,
                "workflow_status": "stopping",
                "process_status": "terminating",
                "error_message": "",
            }
            plan = dict(self.retry_plans.get(session_id, {}))
            plan["remaining_retries"] = 0
            plan["decision_state"] = "stopped"
            self.retry_plans[session_id] = plan
        pending = self._read_pending_interaction(session_id)
        if pending:
            pending["status"] = "resolved"
            pending["resolved_action"] = "stop_run"
            pending["resolved_at"] = int(time.time())
            self._write_pending_interaction(session_id, pending)
        stop_requested_marker = f"\n=== STOP REQUESTED {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        self._append_console_marker(session_id, stop_requested_marker)
        console_log_handle = self.process_log_handles.get(session_id)
        if console_log_handle is not None:
            console_log_handle.flush()
        stopped_cleanly = False
        try:
            process.terminate()
            process.wait(timeout=5.0)
            stopped_cleanly = True
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                try:
                    process.wait(timeout=5.0)
                    stopped_cleanly = True
                except subprocess.TimeoutExpired:
                    stopped_cleanly = False
            else:
                process.kill()
                try:
                    process.wait(timeout=5.0)
                    stopped_cleanly = True
                except subprocess.TimeoutExpired:
                    stopped_cleanly = False
        finally:
            self._append_console_marker(
                session_id,
                f"=== STOP {'CONFIRMED' if stopped_cleanly else 'UNCONFIRMED'} ===\n",
            )
            if console_log_handle is not None:
                console_log_handle.flush()
            self._close_process_log_handle(session_id)
        with self.process_lock:
            self.processes.pop(session_id, None)
        terminated_status = {
            **self.run_statuses[session_id],
            "workflow_status": "idle",
            "process_status": "terminated" if stopped_cleanly else "termination_unconfirmed",
        }
        self.run_statuses[session_id] = terminated_status
        return {
            "stopped": stopped_cleanly,
            "session_id": session_id,
            "reason": "" if stopped_cleanly else "Stop was requested, but the process tree could not be fully confirmed as terminated.",
            "run_status": dict(terminated_status),
        }

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        last_error: OSError | json.JSONDecodeError | None = None
        for attempt in range(5):
            try:
                with path.open("r", encoding="utf-8") as file:
                    data = json.load(file)
                return data if isinstance(data, dict) else {}
            except (OSError, json.JSONDecodeError) as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
        if isinstance(last_error, OSError):
            raise last_error
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
            if raw:
                recovered, _ = json.JSONDecoder().raw_decode(raw)
                return recovered if isinstance(recovered, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            last_error: PermissionError | None = None
            for attempt in range(5):
                try:
                    os.replace(temp_path, path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    def pending_interaction_path(self, session_id: str) -> Path:
        return session_pending_interaction_path(self.runtime_root, session_id)

    def _read_pending_interaction(self, session_id: str) -> Dict[str, Any]:
        if not session_id:
            return {}
        path = self.pending_interaction_path(session_id)
        if not path.exists():
            return {}
        try:
            return self._read_json(path)
        except json.JSONDecodeError:
            return {}

    def _write_pending_interaction(self, session_id: str, payload: Dict[str, Any]) -> None:
        if not session_id:
            return
        self._write_json(self.pending_interaction_path(session_id), payload)

    def _clear_pending_interaction(self, session_id: str) -> None:
        if not session_id:
            return
        path = self.pending_interaction_path(session_id)
        if path.exists():
            path.unlink()

    def _append_console_marker(self, session_id: str, message: str) -> None:
        if not session_id:
            return
        path = self.console_log_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(message)
            if not message.endswith("\n"):
                file.write("\n")

    def _read_ui_state(self) -> Dict[str, Any]:
        with self.ui_state_lock:
            return self._read_ui_state_unlocked()

    def _read_ui_state_unlocked(self) -> Dict[str, Any]:
        path = self.runtime_root / "gui" / "ui_state.json"
        if not path.exists():
            return {
                "current_session_id": "",
                "sessions": [],
                "workspaces": {},
            }
        try:
            state = self._read_json(path)
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._write_ui_state_unlocked(state)
            return state
        except json.JSONDecodeError:
            recovered = self._recover_ui_state(path)
            self._write_ui_state_unlocked(recovered)
            return recovered

    def _write_ui_state(self, payload: Dict[str, Any]) -> None:
        with self.ui_state_lock:
            self._write_ui_state_unlocked(payload)

    def _write_ui_state_unlocked(self, payload: Dict[str, Any]) -> None:
        path = self.runtime_root / "gui" / "ui_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            last_error: Optional[PermissionError] = None
            for attempt in range(5):
                try:
                    os.replace(temp_path, path)
                    return
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

    def _recover_ui_state(self, path: Path) -> Dict[str, Any]:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
        except OSError:
            return {
                "current_session_id": "",
                "sessions": [],
                "workspaces": {},
            }
        if not raw:
            return {
                "current_session_id": "",
                "sessions": [],
                "workspaces": {},
            }
        decoder = json.JSONDecoder()
        try:
            recovered, _ = decoder.raw_decode(raw)
        except json.JSONDecodeError:
            return {
                "current_session_id": "",
                "sessions": [],
                "workspaces": {},
            }
        return recovered if isinstance(recovered, dict) else {
            "current_session_id": "",
            "sessions": [],
            "workspaces": {},
        }

    @staticmethod
    def _normalize_session_index(raw: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw, list):
            return {}
        items: Dict[str, Dict[str, Any]] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            session_id = str(item.get("id", "")).strip()
            if not session_id:
                continue
            items[session_id] = {
                "id": session_id,
                "title": str(item.get("title", "Untitled session")),
                "updatedAt": int(item.get("updatedAt", 0) or 0),
            }
        return items

    @staticmethod
    def _normalize_workspace_index(raw: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        items: Dict[str, Dict[str, Any]] = {}
        for session_id, item in raw.items():
            if not isinstance(item, dict):
                continue
            items[str(session_id)] = {
                "taskInput": str(item.get("taskInput", "")),
                "referenceText": str(item.get("referenceText", "")),
                "referenceImages": [str(value) for value in item.get("referenceImages", []) or []],
            }
        return items

    @staticmethod
    def _normalize_activity_items(raw: Any) -> List[Dict[str, str]]:
        if not isinstance(raw, list):
            return []
        items: List[Dict[str, str]] = []
        seen_ids: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            normalized_item = {
                "id": str(item.get("id", "")),
                "kind": str(item.get("kind", "system")),
                "title": str(item.get("title", "System")),
                "body": str(item.get("body", "")),
                "timestamp": str(item.get("timestamp", "")),
                "collapsible": bool(item.get("collapsible", False)),
                "responseBody": str(item.get("responseBody", "")),
                "validationError": str(item.get("validationError", "")),
                "pairKey": str(item.get("pairKey", "")),
                "pairLabel": str(item.get("pairLabel", "")),
                "llmDirection": str(item.get("llmDirection", "")),
            }
            if not normalized_item["id"]:
                normalized_item["id"] = GuiBridgeService._make_activity_fallback_id(normalized_item)
            if normalized_item["id"] in seen_ids:
                continue
            seen_ids.add(normalized_item["id"])
            items.append(
                normalized_item
            )
        return items

    @staticmethod
    def _default_workspace_payload() -> Dict[str, Any]:
        return {
            "taskInput": "",
            "referenceText": "",
            "referenceImages": [],
        }

    @staticmethod
    def _timestamp_now() -> int:
        return int(__import__("time").time())

    def activity_history_path(self, session_id: str) -> Path:
        return self.runtime_root / "session_data" / session_id / "activity.jsonl"

    def _read_activity_history(self, session_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        path = self.activity_history_path(session_id)
        if not path.exists():
            return []
        items: List[Dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                items.append(payload)
        return self._normalize_activity_items(items)

    def _append_activity_history(self, session_id: str, items: List[Dict[str, Any]]) -> None:
        if not session_id or not items:
            return
        path = self.activity_history_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            for item in items:
                file.write(json.dumps(item, ensure_ascii=False))
                file.write("\n")

    def _next_stream_sequence(self, session_id: str) -> int:
        sequence = int(self._stream_sequences.get(session_id, 0)) + 1
        self._stream_sequences[session_id] = sequence
        return sequence

    def _compute_server_cursor(self, session_id: str, run_status: Optional[Dict[str, Any]] = None) -> str:
        status = run_status or self.run_statuses.get(session_id) or self._default_run_status(session_id)
        progress_path = session_progress_path(self.runtime_root, session_id)
        activity_path = self.activity_history_path(session_id)
        console_path = self.console_log_path(session_id)
        pending_path = self.pending_interaction_path(session_id)
        meetings_path = session_meetings_log_path(self.runtime_root, session_id)
        plan_artifact_path = session_plan_artifact_path(self.runtime_root, session_id)
        build_execution_plan_path = session_build_execution_plan_path(self.runtime_root, session_id)
        assembly_execution_plan_path = session_assembly_execution_plan_path(self.runtime_root, session_id)
        path_stamps = [
            self._path_version_stamp(path)
            for path in (
                progress_path,
                activity_path,
                console_path,
                pending_path,
                meetings_path,
                plan_artifact_path,
                build_execution_plan_path,
                assembly_execution_plan_path,
            )
        ]
        meeting_state_stamps = [
            self._path_version_stamp(path)
            for path in list_session_meeting_state_paths(self.runtime_root, session_id)
        ]
        return "|".join(
            [
                f"workflow:{status.get('workflow_status', '')}",
                f"process:{status.get('process_status', '')}",
                f"attempt:{status.get('attempt_index', 0)}",
                *path_stamps,
                *meeting_state_stamps,
            ]
        )

    def load_phase_meeting_state(self, session_id: str, phase_name: str) -> Optional[Dict[str, Any]]:
        return load_phase_meeting_state(self.runtime_root, session_id, phase_name)

    def load_all_phase_meeting_states(self, session_id: str) -> List[Dict[str, Any]]:
        return load_all_phase_meeting_states(self.runtime_root, session_id)

    def select_latest_meeting_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        return select_latest_meeting_state(self.runtime_root, session_id)

    def load_plan_artifact(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = session_plan_artifact_path(self.runtime_root, session_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def load_build_execution_plan(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = session_build_execution_plan_path(self.runtime_root, session_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def load_assembly_execution_plan(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = session_assembly_execution_plan_path(self.runtime_root, session_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _build_failure_triage(
        self,
        session_id: str,
        *,
        run_status: Optional[Dict[str, Any]] = None,
        plan_artifact: Optional[Dict[str, Any]] = None,
        build_execution_plan: Optional[Dict[str, Any]] = None,
        assembly_execution_plan: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        resolved_status = run_status or self.run_statuses.get(session_id) or self._default_run_status(session_id)
        effective_plan = plan_artifact if plan_artifact is not None else self.load_plan_artifact(session_id)
        effective_build = build_execution_plan if build_execution_plan is not None else self.load_build_execution_plan(session_id)
        effective_assembly = assembly_execution_plan if assembly_execution_plan is not None else self.load_assembly_execution_plan(session_id)

        planning_warnings: list[str] = []
        planning_failures: list[str] = []
        responsibility_refs: list[str] = []
        constraint_refs: list[str] = []
        categories: set[str] = set()

        for diagnostic in list((effective_build or {}).get("diagnostics", []) or []):
            if not isinstance(diagnostic, dict):
                continue
            summary = str(diagnostic.get("summary", "")).strip()
            if summary and summary not in planning_warnings:
                planning_warnings.append(summary)
            ref = str(diagnostic.get("responsibility_ref", "")).strip()
            if ref and ref not in responsibility_refs:
                responsibility_refs.append(ref)
            code = str(diagnostic.get("code", "")).strip()
            if code == "builder-placement-violation":
                categories.add("planning_violation")

        assembly_items = list((effective_assembly or {}).get("items", []) or [])
        for diagnostic in list((effective_assembly or {}).get("diagnostics", []) or []):
            if not isinstance(diagnostic, dict):
                continue
            summary = str(diagnostic.get("summary", "")).strip()
            if summary and summary not in planning_warnings:
                planning_warnings.append(summary)
            ref = str(diagnostic.get("responsibility_ref", "")).strip()
            if ref and ref not in responsibility_refs:
                responsibility_refs.append(ref)
            constraint_ref = str(diagnostic.get("constraint_ref", "")).strip()
            if constraint_ref and constraint_ref not in constraint_refs:
                constraint_refs.append(constraint_ref)
            code = str(diagnostic.get("code", "")).strip()
            if code in {"builder-placement-violation", "assembler-geometry-violation"}:
                categories.add("planning_violation")

        if isinstance(effective_plan, dict):
            for item in list(effective_plan.get("risk_hotspots", []) or []):
                text = str(item).strip()
                if text and f"Planning risk hotspot remains active: {text}" not in planning_warnings:
                    planning_warnings.append(f"Planning risk hotspot remains active: {text}")
            for item in list(effective_plan.get("open_issues", []) or []):
                text = str(item).strip()
                if text and f"Unresolved planning issue remains: {text}" not in planning_warnings:
                    planning_warnings.append(f"Unresolved planning issue remains: {text}")

        error_message = str(resolved_status.get("error_message", "")).strip()
        lowered_error = error_message.lower()
        if "ordering constraint" in lowered_error or "parent" in lowered_error:
            categories.add("planning_violation")
            if error_message and error_message not in planning_failures:
                planning_failures.append(error_message)
            for item in assembly_items:
                if not isinstance(item, dict):
                    continue
                for ref in list(item.get("constraint_refs", []) or []):
                    text = str(ref).strip()
                    if text and text not in constraint_refs:
                        constraint_refs.append(text)
        elif any(token in lowered_error for token in ("blender", "executor", "object", "primitive", "action")):
            categories.add("execution_failure")
        elif "validation failed" in lowered_error or "mismatch" in lowered_error:
            categories.add("validation_failure")
        elif error_message and str(resolved_status.get("workflow_status", "")) == "failed":
            categories.add("execution_failure")

        if categories == {"planning_violation", "execution_failure"} or len(categories) > 1:
            failure_category = "mixed"
        elif categories:
            failure_category = next(iter(categories))
        else:
            failure_category = ""

        planning_summary_parts: list[str] = []
        if planning_failures:
            planning_summary_parts.append(planning_failures[0])
        elif planning_warnings:
            planning_summary_parts.append(planning_warnings[0])
        if constraint_refs:
            planning_summary_parts.append(f"Blocking constraints: {', '.join(constraint_refs[:3])}")
        planning_summary = " ".join(part for part in planning_summary_parts if part).strip()

        build_used_fallback = any(bool(item.get("used_step_fallback", False)) for item in list((effective_build or {}).get("items", []) or []) if isinstance(item, dict))
        assembly_used_fallback = any(bool(item.get("used_step_fallback", False)) for item in assembly_items if isinstance(item, dict))

        return {
            "failure_category": failure_category,
            "planning_summary": planning_summary,
            "planning_warnings": planning_warnings,
            "planning_failures": planning_failures,
            "blocking_constraint_refs": constraint_refs,
            "planning_responsibility_refs": responsibility_refs,
            "build_used_fallback": build_used_fallback,
            "assembly_used_fallback": assembly_used_fallback,
        }

    @staticmethod
    def _select_inspector_task(progress: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(progress, dict):
            return None
        part_tasks = progress.get("part_tasks")
        if not isinstance(part_tasks, list) or not part_tasks:
            return None
        active_task_id = str(progress.get("active_task_id", "")).strip()
        if active_task_id:
            for task in part_tasks:
                if isinstance(task, dict) and str(task.get("task_id", "")).strip() == active_task_id:
                    return task
        return None

    @classmethod
    def _default_inspector_selection(cls, progress: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(progress, dict):
            return {"kind": "none"}
        assembly = progress.get("assembly")
        assembly_rounds = assembly.get("rounds") if isinstance(assembly, dict) else []
        stage = str(progress.get("stage", "")).strip()
        status = str(progress.get("status", "")).strip()
        if isinstance(assembly_rounds, list) and assembly_rounds and (
            stage == "assembly" or stage == "completed" or status == "completed"
        ):
            round_data = assembly_rounds[-1]
            if isinstance(round_data, dict):
                return {"kind": "assembly-round", "round": round_data}
        selected_task = cls._select_inspector_task(progress)
        if isinstance(selected_task, dict):
            return {"kind": "task", "task": selected_task}
        return {"kind": "none"}

    @staticmethod
    def _build_inspector_summary(progress: Dict[str, Any]) -> Dict[str, str]:
        final_validation = progress.get("final_validation") if isinstance(progress, dict) else {}
        detected_parts = final_validation.get("detected_parts") if isinstance(final_validation, dict) else []
        completed_task_ids = progress.get("completed_task_ids") if isinstance(progress, dict) else []
        active_task_id = str(progress.get("active_task_id", "")).strip() if isinstance(progress, dict) else ""
        stop_reason = str(progress.get("stop_reason", "")).strip() if isinstance(progress, dict) else ""
        stage = str(progress.get("stage", "")).strip() if isinstance(progress, dict) else ""
        stage_status = str(progress.get("stage_status", "")).strip() if isinstance(progress, dict) else ""
        stage_value = f"{stage} / {stage_status}".strip(" /") if stage or stage_status else "Unknown"
        return {
            "status": str(progress.get("status", "unknown")).strip() if isinstance(progress, dict) else "unknown",
            "stage": stage_value,
            "active_task": active_task_id or "None",
            "detected_parts": ", ".join(str(item) for item in detected_parts) if isinstance(detected_parts, list) and detected_parts else "Pending",
            "completed_tasks": ", ".join(str(item) for item in completed_task_ids) if isinstance(completed_task_ids, list) and completed_task_ids else "None",
            "stop_reason": stop_reason or "Run is still active.",
        }

    @staticmethod
    def _latest_capture_path(selection: Dict[str, Any]) -> str:
        if not isinstance(selection, dict):
            return "No capture selected"
        kind = str(selection.get("kind", "none"))
        if kind == "assembly-round":
            round_data = selection.get("round")
            if isinstance(round_data, dict):
                return str(round_data.get("capture_path", "")).strip() or "No capture selected"
            return "No capture selected"
        if kind == "task":
            selected_task = selection.get("task")
            if not isinstance(selected_task, dict):
                return "No capture selected"
            rounds = selected_task.get("rounds")
            if not isinstance(rounds, list) or not rounds:
                return "No capture selected"
            latest_round = rounds[-1]
            if not isinstance(latest_round, dict):
                return "No capture selected"
            return str(latest_round.get("capture_path", "")).strip() or "No capture selected"
        return "No capture selected"

    @staticmethod
    def _final_validation_capture_path(progress: Dict[str, Any]) -> str:
        if not isinstance(progress, dict):
            return "Pending final validation"
        final_validation = progress.get("final_validation")
        if not isinstance(final_validation, dict):
            return "Pending final validation"
        return str(final_validation.get("capture_path", "")).strip() or "Pending final validation"

    @staticmethod
    def _selected_task_title(selection: Dict[str, Any]) -> str:
        if not isinstance(selection, dict):
            return "No active task selected"
        kind = str(selection.get("kind", "none"))
        if kind == "task":
            selected_task = selection.get("task")
            if isinstance(selected_task, dict):
                return str(selected_task.get("title", "")).strip() or "No active task selected"
        if kind == "assembly-round":
            round_data = selection.get("round")
            if isinstance(round_data, dict):
                round_index = round_data.get("round_index", "")
                return f"Assembly Round {round_index}".strip()
        return "No active task selected"

    @staticmethod
    def _build_inspector_blocks(selection: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(selection, dict):
            return []
        kind = str(selection.get("kind", "none"))
        if kind == "task":
            selected_task = selection.get("task")
            if not isinstance(selected_task, dict):
                return []
            return [
                {
                    "title": "Task Summary",
                    "items": [
                        {"label": "task_id", "value": str(selected_task.get("task_id", ""))},
                        {"label": "object_name", "value": str(selected_task.get("object_name", ""))},
                        {"label": "status", "value": str(selected_task.get("status", ""))},
                        {"label": "current_round", "value": str(selected_task.get("current_round", ""))},
                        {"label": "approved", "value": GuiBridgeService._stringify_inspector_value(selected_task.get("approved", ""))},
                    ],
                }
            ]
        if kind == "assembly-round":
            round_data = selection.get("round")
            if not isinstance(round_data, dict):
                return []
            requested_actions = round_data.get("requested_actions")
            if not isinstance(requested_actions, list):
                requested_actions = []
            blocks: List[Dict[str, Any]] = [
                {
                    "title": "Assembly Round",
                    "items": [
                        {"label": "round_index", "value": str(round_data.get("round_index", ""))},
                        {"label": "task_title", "value": str(round_data.get("task_title", "")).strip() or "Unknown"},
                        {"label": "assembly_step_index", "value": str(round_data.get("assembly_step_index", "")).strip() or "Unknown"},
                        {"label": "approved", "value": GuiBridgeService._stringify_inspector_value(round_data.get("approved", ""))},
                        {"label": "feedback_summary", "value": str(round_data.get("feedback_summary", ""))},
                    ],
                }
            ]
            context = round_data.get("context")
            if isinstance(context, dict):
                blocks.append(
                    {
                        "title": "Context",
                        "items": [{"label": str(label), "value": str(value)} for label, value in context.items()],
                    }
                )
            for index, action in enumerate(requested_actions):
                if not isinstance(action, dict):
                    continue
                parameters = action.get("parameters")
                if not isinstance(parameters, dict):
                    parameters = {}
                blocks.append(
                    {
                        "title": f"Requested Action {index + 1}",
                        "items": [
                            {"label": "action_type", "value": str(action.get("action_type", ""))},
                            {"label": "execution_status", "value": str(action.get("execution_status", ""))},
                            {"label": "reason", "value": str(action.get("reason", ""))},
                            *[
                                {"label": f"param.{label}", "value": str(value)}
                                for label, value in parameters.items()
                            ],
                        ],
                    }
                )
            return blocks
        return []

    @staticmethod
    def _stringify_inspector_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def _make_stream_event(
        self,
        session_id: str,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sequence = self._next_stream_sequence(session_id)
        event_id = str((data or {}).get("event_id", f"{event_type}-{sequence}"))
        return {
            "type": event_type,
            "session_id": session_id,
            "event_id": event_id,
            "sequence": sequence,
            "server_cursor": self._compute_server_cursor(session_id),
            "data": data or {},
        }

    def _activity_items_from_meeting_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        kind = str(event.get("kind", ""))
        phase = str(event.get("phase", ""))
        message = str(event.get("message", "")).strip()
        summary = str(event.get("summary", "")).strip() or str(event.get("content_preview", "")).strip() or message
        full_content = str(event.get("full_content", "")).strip() or message
        speaker = str(event.get("speaker", "")).strip() or ("Moderator" if kind == "resolution" else "Agent")
        title = phase.title() if phase else "System"
        timestamp = time.strftime("%H:%M")
        event_id = str(event.get("event_id", ""))
        raw_tool_calls = event.get("tool_calls", [])
        tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) else []

        def tool_call_markdown() -> str:
            lines: List[str] = []
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                tool_name = str(tool_call.get("tool_name", "")).strip() or "tool"
                arguments = tool_call.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}
                formatted_args = ", ".join(
                    f"{key}={json.dumps(value, ensure_ascii=False)}"
                    for key, value in arguments.items()
                )
                lines.append(
                    f"- `{tool_name}({formatted_args})`" if formatted_args else f"- `{tool_name}()`"
                )
            return "\n".join(lines)

        def missing_contract_markdown() -> str:
            raw_missing = event.get("missing_contract_fields", [])
            missing_fields = raw_missing if isinstance(raw_missing, list) else []
            values = [str(item).strip() for item in missing_fields if str(item).strip()]
            if not values:
                return ""
            return "Missing contract fields:\n" + "\n".join(f"- `{item}`" for item in values)

        def phase_body(default_value: str) -> str:
            return summary or default_value

        if kind in {"phase_start", "phase_open"}:
            return [{"id": event_id, "kind": "meeting_phase", "title": title, "body": phase_body("Meeting opened"), "timestamp": timestamp}]
        if kind in {"expert_spoke", "proposal", "challenge", "response", "resolution"}:
            substep = str(event.get("substep", "")).strip().lower()
            final = bool(event.get("final", True))
            if kind == "proposal":
                bubble_title = f"{speaker} - Proposal"
            elif kind == "challenge":
                bubble_title = f"{speaker} - Challenge"
            elif kind == "response":
                bubble_title = f"{speaker} - Response"
            elif kind == "resolution":
                bubble_title = f"{speaker} - Resolution"
            else:
                bubble_title = speaker
            if not final and substep:
                bubble_title = f"{speaker} - {substep.title()}"
            return [{
                "id": event_id,
                "kind": "llm",
                "title": bubble_title,
                "body": summary,
                "timestamp": timestamp,
                "collapsible": bool(full_content),
                "responseBody": full_content,
                "meetingSubstep": substep or None,
                "meetingFinal": final,
                "deliberationGroupId": event.get("deliberation_group_id"),
                "guardrailFlags": list(event.get("guardrail_flags", []) or []),
            }]
        if kind in {"extraction_done", "validation_result"}:
            return [{
                "id": event_id,
                "kind": "system",
                "title": "System",
                "body": summary or full_content or "Validation update",
                "timestamp": timestamp,
                "collapsible": bool(full_content and full_content != summary),
                "responseBody": full_content if full_content and full_content != summary else "",
            }]
        if kind in {"phase_end", "phase_close"}:
            return [{"id": event_id, "kind": "meeting_phase", "title": title, "body": phase_body("Meeting closed"), "timestamp": timestamp}]
        if kind in {"build_step", "assemble_step"}:
            tool_body = tool_call_markdown()
            missing_body = missing_contract_markdown()
            return [{
                "id": event_id,
                "kind": "meeting_step",
                "title": "Step",
                "body": summary or full_content or "Execution step",
                "timestamp": timestamp,
                "collapsible": bool(tool_body or missing_body or full_content),
                "responseBody": tool_body or missing_body or full_content,
            }]
        return []

    def console_log_path(self, session_id: str) -> Path:
        return session_console_log_path(self.runtime_root, session_id)

    def _refresh_run_status(self, session_id: str) -> Dict[str, Any]:
        with self.process_lock:
            status = dict(self.run_statuses.get(session_id, self._default_run_status(session_id)))
            process = self.processes.get(session_id)
        if process is None:
            return status
        exit_code = process.poll()
        if exit_code is None:
            status["workflow_status"] = "running"
            status["process_status"] = "running"
            status["pid"] = process.pid
            status["exit_code"] = None
        else:
            status["pid"] = process.pid
            status["exit_code"] = exit_code
            if exit_code == 0:
                status["workflow_status"] = "completed"
                status["process_status"] = "exited"
                status["error_message"] = ""
                self._clear_pending_interaction(session_id)
                with self.process_lock:
                    plan = dict(self.retry_plans.get(session_id, {}))
                    if plan:
                        plan["decision_state"] = "completed"
                        plan["remaining_retries"] = 0
                        self.retry_plans[session_id] = plan
            else:
                status["workflow_status"] = "failed"
                status["process_status"] = "exited"
                status["error_message"] = status.get("error_message") or f"Process exited with code {exit_code}."
                failure_triage = self._build_failure_triage(session_id, run_status=status)
                with self.process_lock:
                    plan = dict(self.retry_plans.get(session_id, {}))
                    if plan:
                        plan["last_failure_reason"] = status["error_message"]
                        remaining = int(plan.get("remaining_retries", 0))
                    else:
                        remaining = 0
                self._write_pending_interaction(
                    session_id,
                    {
                        "interaction_id": f"retry-{sanitize_session_id(session_id)}-{int(time.time())}",
                        "session_id": session_id,
                        "kind": "retry_decision",
                        "status": "pending",
                        "prompt": "This run failed. Choose whether to retry.",
                        "failure_reason": status["error_message"],
                        "failure_category": str(failure_triage.get("failure_category", "")),
                        "planning_summary": str(failure_triage.get("planning_summary", "")),
                        "blocking_constraint_refs": list(failure_triage.get("blocking_constraint_refs", []) or []),
                        "attempt_index": int(status.get("attempt_index", 0)),
                        "next_attempt_index": int(status.get("attempt_index", 0)) + 1,
                        "remaining_retries": remaining,
                        "suggested_options": [1, 3, 0],
                        "created_at": int(time.time()),
                        "resolved_at": None,
                    },
                )
            self._close_process_log_handle(session_id)
            with self.process_lock:
                self.processes.pop(session_id, None)
        with self.process_lock:
            self.run_statuses[session_id] = status
        if exit_code not in (None, 0):
            auto_retry = int(self.retry_plans.get(session_id, {}).get("remaining_retries", 0))
            if auto_retry > 0:
                failure_triage = self._build_failure_triage(session_id, run_status=status)
                with self.process_lock:
                    plan = dict(self.retry_plans.get(session_id, {}))
                    plan["remaining_retries"] = max(0, auto_retry - 1)
                    plan["decision_state"] = "retrying"
                    self.retry_plans[session_id] = plan
                self._write_pending_interaction(
                    session_id,
                    {
                        "interaction_id": f"retry-{sanitize_session_id(session_id)}-{int(time.time())}",
                        "session_id": session_id,
                        "kind": "retry_decision",
                        "status": "resolved",
                        "resolved_action": "auto_retry",
                        "failure_reason": status.get("error_message", ""),
                        "failure_category": str(failure_triage.get("failure_category", "")),
                        "planning_summary": str(failure_triage.get("planning_summary", "")),
                        "blocking_constraint_refs": list(failure_triage.get("blocking_constraint_refs", []) or []),
                        "attempt_index": int(status.get("attempt_index", 0)),
                        "next_attempt_index": int(status.get("attempt_index", 0)) + 1,
                        "remaining_retries": max(0, auto_retry - 1),
                        "created_at": int(time.time()),
                        "resolved_at": int(time.time()),
                    },
                )
                retry_payload = deepcopy(self.last_run_payloads.get(session_id, {}))
                if retry_payload:
                    self._start_run_from_payload(retry_payload, is_retry=True)
                    with self.process_lock:
                        return dict(self.run_statuses.get(session_id, status))
        return dict(status)

    def _close_process_log_handle(self, session_id: str) -> None:
        handle = self.process_log_handles.pop(session_id, None)
        if handle is None:
            return
        try:
            handle.close()
        except Exception:
            return

    @staticmethod
    def _default_run_status(session_id: str) -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "workflow_status": "idle",
            "process_status": "not_started",
            "error_message": "",
            "last_command": [],
            "pid": None,
            "exit_code": None,
            "attempt_index": 0,
        }

    @staticmethod
    def _default_progress_payload() -> Dict[str, Any]:
        return {
            "workflow_type": "multi_stage_modeling",
            "status": "idle",
            "task": "",
            "stage": "idle",
            "stage_status": "waiting_for_prompt",
            "multi_expert_mode": True,
            "active_task_id": "",
            "completed_task_ids": [],
            "part_tasks": [],
            "assembly": {
                "status": "pending",
                "current_round": 0,
                "approved": False,
                "all_parts_visible": False,
                "initial_placement_applied": False,
                "rounds": [],
            },
            "final_validation": {
                "status": "pending",
                "capture_path": "",
                "viewpoint": "front",
                "detected_parts": [],
                "missing_critical_parts": [],
                "quantitative_metrics": [],
            },
            "stop_reason": "",
        }

    def _next_attempt_index(self, session_id: str) -> int:
        existing = self.run_statuses.get(session_id, {})
        return int(existing.get("attempt_index", 0)) + 1

    def _build_retry_prompt(self, session_id: str, run_status: Dict[str, Any]) -> Dict[str, Any]:
        with self.process_lock:
            plan = dict(self.retry_plans.get(session_id, {}))
            has_last_payload = session_id in self.last_run_payloads
        pending = self._read_pending_interaction(session_id)
        failure_triage = self._build_failure_triage(session_id, run_status=run_status)
        should_offer = (
            bool(session_id)
            and has_last_payload
            and str(run_status.get("workflow_status", "")) == "failed"
            and str(plan.get("decision_state", "")) != "retrying"
            and str(plan.get("decision_state", "")) != "stopped"
            and str(pending.get("status", "pending")) == "pending"
        )
        attempt_index = int(run_status.get("attempt_index", 0))
        return {
            "show": should_offer,
            "session_id": session_id,
            "remaining_retries": int(plan.get("remaining_retries", 0)),
            "decision_state": str(plan.get("decision_state", "")),
            "failure_reason": str(pending.get("failure_reason", "")) or str(run_status.get("error_message", "")),
            "failure_category": str(pending.get("failure_category", "")) or str(failure_triage.get("failure_category", "")),
            "planning_summary": str(pending.get("planning_summary", "")) or str(failure_triage.get("planning_summary", "")),
            "blocking_constraint_refs": list(pending.get("blocking_constraint_refs", []) or failure_triage.get("blocking_constraint_refs", []) or []),
            "interaction_id": str(pending.get("interaction_id", "")),
            "attempt_index": int(pending.get("attempt_index", attempt_index)),
            "next_attempt_index": int(pending.get("next_attempt_index", attempt_index + 1)),
            "auto_retrying": str(plan.get("decision_state", "")) == "retrying",
        }

    @staticmethod
    def _sanitize_session_id(session_id: str) -> str:
        return sanitize_session_id(session_id)

    def _ensure_mcp_status(self) -> None:
        if str(self.mcp_status.get("state", "")) != "idle":
            return
        self.connect_blender_mcp({})

    def _refresh_mcp_status_best_effort(self) -> None:
        if str(self.mcp_status.get("state", "")) != "idle":
            return
        try:
            self.connect_blender_mcp({})
        except Exception as exc:
            self.mcp_status = {
                "enabled": True,
                "state": "failed",
                "message": str(exc),
                "tools": [],
                "server_name": "",
            }

    def _load_backend_settings(self) -> Dict[str, Any]:
        if not self.backend_settings_path.exists():
            raise FileNotFoundError(
                f"Backend settings file not found: {self.backend_settings_path}"
            )
        return load_pipeline_settings(self.backend_settings_path)

    @staticmethod
    def _make_activity_fallback_id(item: Dict[str, Any]) -> str:
        digest = sha1(
            json.dumps(
                {
                    "kind": item.get("kind", ""),
                    "title": item.get("title", ""),
                    "body": item.get("body", ""),
                    "timestamp": item.get("timestamp", ""),
                    "pairKey": item.get("pairKey", ""),
                    "llmDirection": item.get("llmDirection", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8", errors="replace")
        ).hexdigest()
        return f"activity-{digest[:16]}"

    @staticmethod
    def _path_version_stamp(path: Path) -> str:
        if not path.exists():
            return "0"
        stat = path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"

    def _merge_runtime_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        settings = self._load_backend_settings()
        merged = dict(payload)
        merged["max_part_refinement_rounds"] = int(
            payload.get("max_part_refinement_rounds") or settings.get("max_part_refinement_rounds", 3)
        )
        merged["max_assembly_rounds"] = int(
            payload.get("max_assembly_rounds") or settings.get("max_assembly_rounds", 3)
        )
        merged["use_yolo_perception"] = bool(
            payload.get("use_yolo_perception")
            if "use_yolo_perception" in payload
            else settings.get("use_yolo_perception", False)
        )
        merged["yolo_model_path"] = str(payload.get("yolo_model_path") or settings.get("yolo_model_path", ""))
        merged["yolo_viewpoints"] = [
            str(item)
            for item in (
                payload.get("yolo_viewpoints")
                or settings.get("yolo_viewpoints", [])
            )
        ]
        merged["agent_orchestrator_base_url"] = str(
            payload.get("agent_orchestrator_base_url") or settings.get("agent_orchestrator_base_url", "")
        )
        merged["agent_orchestrator_model"] = str(
            payload.get("agent_orchestrator_model") or settings.get("agent_orchestrator_model", "")
        )
        merged["agent_orchestrator_conversation_id"] = str(
            payload.get("agent_orchestrator_conversation_id") or settings.get("agent_orchestrator_conversation_id", "")
        )
        merged["agent_orchestrator_destroy_on_finish"] = bool(
            payload.get("agent_orchestrator_destroy_on_finish")
            if "agent_orchestrator_destroy_on_finish" in payload
            else settings.get("agent_orchestrator_destroy_on_finish", True)
        )
        merged["agent_orchestrator_timeout_seconds"] = int(
            payload.get("agent_orchestrator_timeout_seconds")
            or settings.get("agent_orchestrator_timeout_seconds", 120)
        )
        return merged

    def _resolve_blender_mcp_client_config(self, session_id: str = "") -> Dict[str, Any]:
        settings = self._load_backend_settings()
        command = str(settings.get("blender_mcp_command", "")).strip()
        cwd = str(settings.get("blender_mcp_cwd", "")).strip()
        raw_args = settings.get("blender_mcp_args", [])
        raw_env = settings.get("blender_mcp_env", {})
        server_name = str(settings.get("blender_mcp_server_name", "blender")).strip() or "blender"
        if not isinstance(raw_args, list):
            raise ValueError("Backend setting 'blender_mcp_args' must be a list.")
        if not isinstance(raw_env, dict):
            raise ValueError("Backend setting 'blender_mcp_env' must be an object.")
        args = [str(item).strip() for item in raw_args if str(item).strip()]
        if not command:
            raise ValueError("Blender MCP is misconfigured in backend settings. Missing command.")
        if not args:
            raise ValueError(
                "Blender MCP is misconfigured in backend settings. "
                "Expected a non-empty Blender MCP args list."
            )
        return {
            "server_name": server_name,
            "config": McpClientConfig(
                command=command,
                args=args,
                cwd=cwd or None,
                env={str(key): str(value) for key, value in raw_env.items()},
                session_id=session_id or None,
            ),
        }

    @staticmethod
    def _parse_mcp_json(raw: str) -> Dict[str, Any]:
        if not raw.strip():
            raise ValueError("Blender MCP JSON is empty.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Blender MCP JSON: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Blender MCP JSON must be an object.")
        servers = payload.get("mcpServers")
        if not isinstance(servers, dict) or not servers:
            raise ValueError("Blender MCP JSON must contain a non-empty 'mcpServers' object.")
        server_name, config_data = next(iter(servers.items()))
        if not isinstance(config_data, dict):
            raise ValueError("Selected MCP server config must be an object.")
        command = str(config_data.get("command", "")).strip()
        if not command:
            raise ValueError("MCP server config requires 'command'.")
        args = config_data.get("args", [])
        if args is None:
            args = []
        if not isinstance(args, list):
            raise ValueError("MCP server config 'args' must be a list.")
        cwd = config_data.get("cwd")
        env = config_data.get("env") or {}
        if not isinstance(env, dict):
            raise ValueError("MCP server config 'env' must be an object when provided.")
        return {
            "server_name": str(server_name),
            "config": McpClientConfig(
                command=command,
                args=[str(item) for item in args],
                cwd=None if cwd is None else str(cwd),
                env={str(key): str(value) for key, value in env.items()},
            ),
        }
