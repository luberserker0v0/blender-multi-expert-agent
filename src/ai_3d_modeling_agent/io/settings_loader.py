"""Read pipeline settings from JSON files, with support for nested backend schema."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_LLM_ENDPOINT_URL: str = "http://127.0.0.1:8080"
DEFAULT_LLM_MODEL: str = "local-model"


DEFAULTS: dict[str, Any] = {
    "llm_endpoint_url": DEFAULT_LLM_ENDPOINT_URL,
    "llm_model": DEFAULT_LLM_MODEL,
    "llm_api_key": "",
    "use_blender_mcp": False,
    "blender_mcp_command": "uv",
    "blender_mcp_args": [],
    "blender_mcp_cwd": "",
    "blender_mcp_env": {},
    "agent_orchestrator_base_url": "",
    "agent_orchestrator_model": "",
    "agent_orchestrator_conversation_id": "",
    "agent_orchestrator_destroy_on_finish": True,
    "agent_orchestrator_timeout_seconds": 120,
    "max_part_refinement_rounds": 3,
    "max_assembly_rounds": 3,
    "use_yolo_perception": False,
    "yolo_model_path": "",
    "yolo_viewpoints": ["front"],
}


def load_settings(
    path: str | Path | None = None,
    *,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load normalized settings from a JSON file, with optional flat overrides."""
    result: dict[str, Any] = dict(DEFAULTS)

    if path is not None:
        file_settings = _read_json(path)
        result.update(_normalize_settings_dict(file_settings))

    if overrides:
        filtered = {k: v for k, v in overrides.items() if v is not None}
        result.update(filtered)

    return result


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Settings file not found: {p}")

    with p.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Settings file must contain a JSON object, got {type(data).__name__}")

    return data


def _normalize_settings_dict(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    _assign_if_present(normalized, "llm_endpoint_url", raw.get("llm_endpoint_url"))
    _assign_if_present(normalized, "llm_model", raw.get("llm_model"))
    _assign_if_present(normalized, "llm_api_key", raw.get("llm_api_key"))
    _assign_if_present(normalized, "agent_orchestrator_base_url", raw.get("agent_orchestrator_base_url"))
    _assign_if_present(normalized, "agent_orchestrator_model", raw.get("agent_orchestrator_model"))
    _assign_if_present(normalized, "agent_orchestrator_conversation_id", raw.get("agent_orchestrator_conversation_id"))
    _assign_if_present(normalized, "agent_orchestrator_destroy_on_finish", raw.get("agent_orchestrator_destroy_on_finish"))
    _assign_if_present(normalized, "agent_orchestrator_timeout_seconds", raw.get("agent_orchestrator_timeout_seconds"))
    _assign_if_present(normalized, "use_blender_mcp", raw.get("use_blender_mcp"))
    _assign_if_present(normalized, "blender_mcp_command", raw.get("blender_mcp_command"))
    if "blender_mcp_args" in raw:
        normalized["blender_mcp_args"] = _ensure_string_list(raw["blender_mcp_args"], "blender_mcp_args")
    _assign_if_present(normalized, "blender_mcp_cwd", raw.get("blender_mcp_cwd"))
    if "blender_mcp_env" in raw:
        normalized["blender_mcp_env"] = _ensure_string_dict(raw["blender_mcp_env"], "blender_mcp_env")
    _assign_if_present(normalized, "max_part_refinement_rounds", raw.get("max_part_refinement_rounds"))
    _assign_if_present(normalized, "max_assembly_rounds", raw.get("max_assembly_rounds"))
    _assign_if_present(normalized, "use_yolo_perception", raw.get("use_yolo_perception"))
    _assign_if_present(normalized, "yolo_model_path", raw.get("yolo_model_path"))
    if "yolo_viewpoints" in raw:
        normalized["yolo_viewpoints"] = _ensure_string_list(raw["yolo_viewpoints"], "yolo_viewpoints")
    llm = raw.get("llm")
    if llm is not None:
        llm_payload = _ensure_object(llm, "llm")
        _assign_if_present(normalized, "llm_endpoint_url", llm_payload.get("endpoint_url"))
        _assign_if_present(normalized, "llm_model", llm_payload.get("model"))
        _assign_if_present(normalized, "llm_api_key", llm_payload.get("api_key"))

    pipeline = raw.get("pipeline")
    if pipeline is not None:
        pipeline_payload = _ensure_object(pipeline, "pipeline")
        _assign_if_present(
            normalized,
            "max_part_refinement_rounds",
            pipeline_payload.get("max_part_refinement_rounds"),
        )
        _assign_if_present(
            normalized,
            "max_assembly_rounds",
            pipeline_payload.get("max_assembly_rounds"),
        )

    ao = raw.get("agent_orchestrator")
    if ao is not None:
        ao_payload = _ensure_object(ao, "agent_orchestrator")
        _assign_if_present(normalized, "agent_orchestrator_base_url", ao_payload.get("base_url"))
        _assign_if_present(normalized, "agent_orchestrator_model", ao_payload.get("model"))
        _assign_if_present(normalized, "agent_orchestrator_conversation_id", ao_payload.get("conversation_id"))
        _assign_if_present(normalized, "agent_orchestrator_destroy_on_finish", ao_payload.get("destroy_on_finish"))
        _assign_if_present(normalized, "agent_orchestrator_timeout_seconds", ao_payload.get("timeout_seconds"))

    yolo = raw.get("yolo")
    if yolo is not None:
        yolo_payload = _ensure_object(yolo, "yolo")
        _assign_if_present(normalized, "use_yolo_perception", yolo_payload.get("enabled"))
        _assign_if_present(normalized, "yolo_model_path", yolo_payload.get("model_path"))
        if "viewpoints" in yolo_payload:
            normalized["yolo_viewpoints"] = _ensure_string_list(yolo_payload["viewpoints"], "yolo.viewpoints")

    if "mcpServers" in raw:
        normalized.update(_normalize_nested_mcp(raw["mcpServers"]))

    return normalized


def _normalize_nested_mcp(raw: Any) -> dict[str, Any]:
    servers = _ensure_object(raw, "mcpServers")
    blender = servers.get("blender")
    if blender is None:
        return {}

    blender_payload = _ensure_object(blender, "mcpServers.blender")
    if "command" not in blender_payload:
        raise ValueError("mcpServers.blender.command is required.")
    command = str(blender_payload.get("command", "")).strip()
    if not command:
        raise ValueError("mcpServers.blender.command must be non-empty.")

    args = blender_payload.get("args", [])
    if args is None:
        args = []
    normalized = {
        "use_blender_mcp": True,
        "blender_mcp_command": command,
        "blender_mcp_args": _ensure_string_list(args, "mcpServers.blender.args"),
        "blender_mcp_server_name": "blender",
    }

    if "cwd" in blender_payload and blender_payload.get("cwd") is not None:
        normalized["blender_mcp_cwd"] = str(blender_payload.get("cwd", "")).strip()
    if "env" in blender_payload:
        normalized["blender_mcp_env"] = _ensure_string_dict(
            blender_payload.get("env") or {},
            "mcpServers.blender.env",
        )

    return normalized


def _assign_if_present(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


def _ensure_object(raw: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be a JSON object.")
    return raw


def _ensure_string_list(raw: Any, field_name: str) -> list[str]:
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list.")
    return [str(item) for item in raw]


def _ensure_string_dict(raw: Any, field_name: str) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be an object.")
    return {str(key): str(value) for key, value in raw.items()}


def _ensure_bool_dict(raw: Any, field_name: str) -> dict[str, bool]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be an object.")
    return {str(key): bool(value) for key, value in raw.items()}


def settings_to_run_pipeline_kwargs(settings: dict[str, Any]) -> dict[str, Any]:
    valid_keys = {
        "task",
        "session_id",
        "use_blender_mcp",
        "blender_mcp_command",
        "blender_mcp_args",
        "blender_mcp_cwd",
        "blender_mcp_env",
        "agent_orchestrator_base_url",
        "agent_orchestrator_model",
        "agent_orchestrator_conversation_id",
        "agent_orchestrator_destroy_on_finish",
        "agent_orchestrator_timeout_seconds",
        "event_callback",
        "event_buffer",
    }
    return {key: value for key, value in settings.items() if key in valid_keys}
