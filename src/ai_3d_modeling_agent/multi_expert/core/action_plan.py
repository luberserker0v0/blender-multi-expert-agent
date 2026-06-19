"""Parse and validate builder/assembler action JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ai_3d_modeling_agent.utils.llm_parser import extract_json_from_llm


BUILD_ACTIONS = {
    "create_primitive",
    "create_uv_sphere",
    "set_object_scale",
    "duplicate_object",
    "delete_object",
    "hide_object",
    "show_object",
    "move_object",
    "rotate_object",
    "mirror_object",
}

ASSEMBLY_ACTIONS = {
    "show_object",
    "hide_object",
    "move_object",
    "rotate_object",
    "set_parent",
    "set_object_scale",
    "create_collection",
    "move_to_collection",
}

OPTIONAL_METADATA_ACTIONS = {
    "apply_material",
    "assign_material",
    "set_material",
    "set_color",
}


@dataclass
class AgentActionPlan:
    status: str = "blocked"
    reason: str = ""
    missing_capability: str = ""
    issue: str = ""
    route_to: str = ""
    requested_clarification: str = ""
    parts: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)


def parse_agent_action_plan(raw: str, *, allowed_actions: set[str], context_label: str) -> AgentActionPlan:
    data = extract_json_from_llm(raw, context_label=context_label)
    if not isinstance(data, dict):
        raise ValueError(f"{context_label} action plan must be a JSON object")
    if isinstance(data.get("input"), dict) and "skill_name" in data:
        data = data["input"]
    elif isinstance(data.get("action_plan"), dict):
        data = data["action_plan"]
    if "build_actions" in data and "parts" not in data:
        data = {
            **data,
            "status": data.get("status", "ready"),
            "parts": _normalize_action_items(data.get("build_actions") or [], item_kind="part"),
        }
    if "assembly_actions" in data and "steps" not in data:
        data = {
            **data,
            "status": data.get("status", "ready"),
            "steps": _normalize_action_items(data.get("assembly_actions") or [], item_kind="step"),
        }
    if "action_sequence" in data and "actions" not in data:
        sequence = data.get("action_sequence")
        if ("task" in data or "command" in data or "operation" in data or "action" in data or "action_type" in data) and "parameters" in data:
            actions = [_normalize_action_aliases(data)]
            if isinstance(sequence, list):
                actions.extend(_normalize_action_aliases(item) for item in sequence if isinstance(item, dict))
            data = {**data, "actions": actions}
        else:
            data = {**data, "actions": sequence}
    if "placement_rule" in data and "actions" not in data and "steps" not in data:
        actions = _actions_from_semantic_placement(data)
        data = {
            **data,
            "status": data.get("status", "ready"),
            "steps": _normalize_action_items([{**data, "actions": actions}], item_kind="step"),
        }
    if "primitive_type" in data and "actions" not in data and "parts" not in data and "steps" not in data:
        actions = _actions_from_semantic_build(data)
        semantic_status = str(data.get("status", "") or "").strip().lower()
        data = {
            **data,
            "status": "ready" if semantic_status in {"", "pending"} and actions else data.get("status", "ready"),
            "parts": _normalize_action_items([{**data, "actions": actions}], item_kind="part"),
        }
    if "action_type" in data and "parameters" in data and "actions" not in data and "parts" not in data and "steps" not in data:
        dependencies = data.get(
            "dependencies",
            data.get(
                "follow_up_actions",
                data.get(
                    "post_actions",
                    data.get("post_operation_actions", data.get("successors", data.get("required_actions", []))),
                ),
            ),
        )
        actions = [_normalize_action_aliases(data)]
        inferred_fields = _fields_from_dependency_items(dependencies)
        if isinstance(dependencies, list):
            for item in dependencies:
                if not isinstance(item, dict):
                    continue
                nested = item.get("actions_to_run")
                if isinstance(nested, list):
                    actions.extend(_normalize_action_aliases(action) for action in nested if isinstance(action, dict))
                else:
                    actions.append(_normalize_action_aliases(item))
        data = {
            **data,
            **inferred_fields,
            "status": data.get("status", "ready") or "ready",
            "actions": actions,
        }
    if ("task" in data or "command" in data or "operation" in data or "action" in data) and "parameters" in data and "actions" not in data:
        action_type = str(data.get("task") or data.get("command") or data.get("operation") or data.get("action") or "").strip()
        dependencies = data.get(
            "dependencies",
            data.get(
                "next_actions",
                data.get(
                    "subsequent_actions",
                    data.get(
                        "follow_up_actions",
                        data.get("post_operation_actions", data.get("successors", data.get("required_actions", []))),
                    ),
                ),
            ),
        )
        actions = [_normalize_action_aliases(data)]
        if isinstance(dependencies, list):
            actions.extend(_normalize_action_aliases(item) for item in dependencies if isinstance(item, dict))
        data = {
            **data,
            "status": data.get("status", "ready"),
            "actions": actions,
        }
    if "actions" in data and "parts" not in data and "steps" not in data:
        if _looks_like_build_context(context_label, allowed_actions):
            data = {
                **data,
                "status": data.get("status", "ready"),
                "parts": _normalize_action_items([data], item_kind="part"),
            }
        else:
            data = {
                **data,
                "status": data.get("status", "ready"),
                "steps": _normalize_action_items([data], item_kind="step"),
            }
    status = str(data.get("status", "")).strip().lower()
    if status in {"completed", "complete", "success", "succeeded", "done"}:
        status = "ready"
    if status not in {"ready", "blocked", "needs_revision"}:
        raise ValueError(f"{context_label} action plan has invalid status: {status!r}")
    plan = AgentActionPlan(
        status=status,
        reason=str(data.get("reason", "")).strip(),
        missing_capability=str(data.get("missing_capability", "")).strip(),
        issue=str(data.get("issue", "")).strip(),
        route_to=str(data.get("route_to", "")).strip(),
        requested_clarification=str(data.get("requested_clarification", "")).strip(),
        parts=_normalize_action_items(data.get("parts", []) or [], item_kind="part"),
        steps=_normalize_action_items(data.get("steps", []) or [], item_kind="step"),
    )
    if status == "ready":
        _drop_optional_metadata_actions(plan.parts, allowed_actions)
        _drop_optional_metadata_actions(plan.steps, allowed_actions)
        _validate_actions(plan.parts, allowed_actions, context_label)
        _validate_actions(plan.steps, allowed_actions, context_label)
    return plan


def fallback_json_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _normalize_action_items(value: Any, *, item_kind: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    if all(isinstance(item, dict) and "action_type" in item and not _looks_like_action_item_container(item) for item in value):
        return [{"actions": value}] if item_kind == "part" else [{"step_index": 0, "actions": value}]

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        current = dict(item)
        if "actions" not in current and isinstance(current.get("steps"), list):
            current["actions"] = current["steps"]
        if isinstance(current.get("actions"), list):
            current["actions"] = [_normalize_action_aliases(action) for action in current["actions"] if isinstance(action, dict)]
        if item_kind == "part":
            current.setdefault("part_name", current.get("family_name") or current.get("family") or current.get("target_family") or current.get("name"))
            current.setdefault("source_object_name", _infer_source_object_name(current))
            if "instance_names" not in current:
                current["instance_names"] = _infer_instance_names(current)
        else:
            current.setdefault("step_index", current.get("index", index))
            if "placements" not in current:
                current["placements"] = _infer_placements(current)
        normalized.append(current)
    return normalized


def _looks_like_action_item_container(item: dict[str, Any]) -> bool:
    return any(key in item for key in ("actions", "parts", "steps", "dependencies", "follow_up_actions", "instance_names", "part_name", "target_family"))


def _infer_source_object_name(item: dict[str, Any]) -> str:
    for action in item.get("actions", []) or []:
        if not isinstance(action, dict):
            continue
        if str(action.get("action_type", "")).strip() == "create_primitive":
            params = action.get("parameters", {})
            if isinstance(params, dict):
                name = str(params.get("name", "")).strip()
                if name:
                    return name
    return ""


def _infer_instance_names(item: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for action in item.get("actions", []) or []:
        if not isinstance(action, dict):
            continue
        params = action.get("parameters", {})
        if not isinstance(params, dict):
            continue
        if str(action.get("action_type", "")).strip() == "duplicate_object":
            name = str(params.get("new_name", "")).strip()
            if name:
                names.append(name)
    return names


def _infer_placements(item: dict[str, Any]) -> list[dict[str, Any]]:
    placements: dict[str, dict[str, Any]] = {}
    for action in item.get("actions", []) or []:
        if not isinstance(action, dict):
            continue
        params = action.get("parameters", {})
        if not isinstance(params, dict):
            continue
        name = str(params.get("name", "")).strip()
        if not name:
            continue
        placement = placements.setdefault(name, {"part": name, "instances": [name]})
        action_type = str(action.get("action_type", "")).strip()
        if action_type == "move_object":
            placement["world_position"] = list(params.get("location", [0.0, 0.0, 0.0]))
        elif action_type == "rotate_object":
            placement["world_rotation"] = list(params.get("rotation", [0.0, 0.0, 0.0]))
    return list(placements.values())


def _normalize_action_aliases(action: dict[str, Any]) -> dict[str, Any]:
    current = dict(action)
    if "action_type" not in current and "command" in current:
        current["action_type"] = current.get("command")
    if "action_type" not in current and "task" in current:
        current["action_type"] = current.get("task")
    if "action_type" not in current and "action" in current:
        current["action_type"] = current.get("action")
    if "action_type" not in current and "operation" in current:
        current["action_type"] = current.get("operation")
    parameters = current.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    else:
        parameters = dict(parameters)
    for key in (
        "name",
        "primitive_type",
        "new_name",
        "scale",
        "location",
        "rotation_degrees",
        "rotation",
        "child_name",
        "parent_name",
    ):
        if key in current and key not in parameters:
            parameters[key] = current.get(key)
    current["parameters"] = parameters
    return current


def _fields_from_dependency_items(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        return {}
    fields: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        for target_key, source_keys in {
            "part_name": ("part_name", "family", "target_family"),
            "target_family": ("target_family", "family", "part_name"),
            "step_index": ("step_index", "index"),
            "instance_names": ("instance_names",),
        }.items():
            if target_key in fields:
                continue
            for source_key in source_keys:
                value_at_key = item.get(source_key)
                if value_at_key not in (None, "", []):
                    fields[target_key] = value_at_key
                    break
    return fields


def _looks_like_build_context(context_label: str, allowed_actions: set[str]) -> bool:
    label = str(context_label or "").lower()
    if "build" in label:
        return True
    if "assembly" in label or "assemble" in label or "placement" in label:
        return False
    return "create_primitive" in allowed_actions and "set_parent" not in allowed_actions


def _actions_from_semantic_placement(data: dict[str, Any]) -> list[dict[str, Any]]:
    instances = _semantic_placement_instances(data)
    per_instance_locations = _semantic_placement_locations(data)
    location = _xyz_from_value(data.get("target_world_position", data.get("location")), [0.0, 0.0, 0.0])
    rotation = _xyz_from_value(data.get("target_rotation", data.get("rotation_degrees")), [0.0, 0.0, 0.0])
    parent = data.get("parent_object_name", data.get("parent_name", data.get("parent")))
    parent_name = str(parent or "").replace("\\_", "_").strip()
    actions: list[dict[str, Any]] = []
    for index, name in enumerate(instances):
        instance_location = per_instance_locations[index] if index < len(per_instance_locations) else location
        actions.append({"action_type": "show_object", "parameters": {"name": name}})
        actions.append({"action_type": "move_object", "parameters": {"name": name, "location": list(instance_location)}})
        if any(float(value or 0.0) != 0.0 for value in rotation):
            actions.append({"action_type": "rotate_object", "parameters": {"name": name, "rotation_degrees": list(rotation)}})
        if parent_name:
            actions.append({"action_type": "set_parent", "parameters": {"child_name": name, "parent_name": parent_name}})
    return actions


def _semantic_placement_instances(data: dict[str, Any]) -> list[str]:
    explicit = data.get("instances_to_place", data.get("instance_names", data.get("instances")))
    if isinstance(explicit, str):
        values = [part.strip() for part in explicit.split(",")]
    elif isinstance(explicit, list):
        values = explicit
    else:
        values = []
    instances = [str(item).replace("\\_", "_").strip() for item in values if str(item).strip()]
    if instances:
        return instances
    family = str(data.get("target_family") or data.get("family") or data.get("part_name") or "").replace("\\_", "_").strip()
    count = _positive_int(data.get("instance_count", data.get("count", 1)), 1)
    if family:
        return [f"{family}_{index:02d}" for index in range(1, count + 1)]
    return []


def _semantic_placement_locations(data: dict[str, Any]) -> list[list[float]]:
    raw = data.get("instance_world_positions", data.get("instance_locations"))
    if not isinstance(raw, list):
        return []
    locations: list[list[float]] = []
    for item in raw:
        locations.append(_xyz_from_value(item, [0.0, 0.0, 0.0]))
    return locations


def _actions_from_semantic_build(data: dict[str, Any]) -> list[dict[str, Any]]:
    primitive_type = str(data.get("primitive_type", "") or "").replace("\\_", "_").strip()
    family = str(data.get("target_family") or data.get("family") or data.get("part_name") or "part").replace("\\_", "_").strip()
    if not primitive_type:
        return []
    source_name = str(data.get("source_object_name") or data.get("source_name") or f"{family}_source").replace("\\_", "_").strip()
    count = _positive_int(data.get("instance_count", data.get("count", 1)), 1)
    actions: list[dict[str, Any]] = [
        {"action_type": "create_primitive", "parameters": {"primitive_type": primitive_type, "name": source_name}}
    ]
    scale = data.get("scale")
    if isinstance(scale, list) and scale:
        actions.append({"action_type": "set_object_scale", "parameters": {"name": source_name, "scale": scale[:3]}})
    for index in range(1, count + 1):
        actions.append(
            {
                "action_type": "duplicate_object",
                "parameters": {"name": source_name, "new_name": f"{family}_{index:02d}"},
            }
        )
    actions.append({"action_type": "delete_object", "parameters": {"name": source_name}})
    return actions


def _xyz_from_value(value: Any, default: list[float]) -> list[float]:
    if isinstance(value, dict):
        return [float(value.get(axis, default[index]) or 0.0) for index, axis in enumerate(("x", "y", "z"))]
    if isinstance(value, list):
        padded = [float(item or 0.0) for item in value[:3]] + list(default)
        return padded[:3]
    return list(default)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _validate_actions(items: list[dict[str, Any]], allowed_actions: set[str], context_label: str) -> None:
    for item in items:
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError(f"{context_label} actions must be a list")
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError(f"{context_label} action must be an object")
            action_type = str(action.get("action_type", "")).strip()
            if action_type not in allowed_actions:
                raise ValueError(f"{context_label} unsupported action type: {action_type}")
            if not isinstance(action.get("parameters", {}), dict):
                raise ValueError(f"{context_label} action parameters must be an object")


def _drop_optional_metadata_actions(items: list[dict[str, Any]], allowed_actions: set[str]) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        actions = item.get("actions", [])
        if not isinstance(actions, list):
            continue
        item["actions"] = [
            action
            for action in actions
            if not (
                isinstance(action, dict)
                and str(action.get("action_type", "")).strip() in OPTIONAL_METADATA_ACTIONS
                and str(action.get("action_type", "")).strip() not in allowed_actions
            )
        ]
