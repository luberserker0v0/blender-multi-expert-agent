"""Deterministic todo/coverage tracking for multi-expert phases."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


TODO_STATUSES = {"pending", "covered", "missing", "not_applicable"}


@dataclass
class CoverageTodo:
    id: str
    phase: str
    source: str
    target_name: str
    target_kind: str
    task: str
    status: str = "pending"
    required: bool = True
    evidence: str = ""
    missing_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if payload["status"] not in TODO_STATUSES:
            payload["status"] = "pending"
        return payload


@dataclass
class TodoGroup:
    id: str
    phase: str
    target_name: str
    target_kind: str
    role: str
    review_role: str
    status: str = "pending"
    todos: list[dict[str, Any]] = None  # type: ignore[assignment]
    focused_prompt: str = ""
    agent_output: str = ""
    review_output: str = ""
    accepted_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "phase": self.phase,
            "target_name": self.target_name,
            "target_kind": self.target_kind,
            "role": self.role,
            "review_role": self.review_role,
            "status": self.status,
            "todos": list(self.todos or []),
            "focused_prompt": self.focused_prompt,
            "agent_output": self.agent_output,
            "review_output": self.review_output,
            "accepted_summary": self.accepted_summary,
        }


def build_spec_todos_from_design(design_artifact: Any) -> list[dict[str, Any]]:
    todos: list[CoverageTodo] = []
    for part in _design_parts(design_artifact):
        name = part["name"]
        source = f"design:{name}"
        todos.extend(
            [
                CoverageTodo(
                    id=f"spec:{name}:part_exists",
                    phase="spec",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="spec_part_exists",
                ),
                CoverageTodo(
                    id=f"spec:{name}:geometry_defined",
                    phase="spec",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="spec_geometry_defined",
                ),
                CoverageTodo(
                    id=f"spec:{name}:instance_count_preserved",
                    phase="spec",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="spec_instance_count_preserved",
                ),
            ]
        )
    return [todo.to_dict() for todo in todos]


def build_plan_todos_from_spec(spec_artifact: Any, part_families: list[Any]) -> list[dict[str, Any]]:
    todos: list[CoverageTodo] = []
    for family in _family_records(spec_artifact, part_families):
        name = family["name"]
        source = f"spec:{name}"
        todos.extend(
            [
                CoverageTodo(
                    id=f"plan:{name}:build_responsibility",
                    phase="plan",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="plan_build_responsibility",
                ),
                CoverageTodo(
                    id=f"plan:{name}:assembly_responsibility",
                    phase="plan",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="plan_assembly_responsibility",
                ),
                CoverageTodo(
                    id=f"plan:{name}:instance_count_preserved",
                    phase="plan",
                    source=source,
                    target_name=name,
                    target_kind="part",
                    task="plan_instance_count_preserved",
                ),
            ]
        )
    return [todo.to_dict() for todo in todos]


def build_todo_groups(
    todos: list[dict[str, Any]],
    *,
    phase: str,
    role: str,
    review_role: str = "reviewer",
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    target_kinds: dict[str, str] = {}
    for todo in todos:
        target = str(todo.get("target_name", "")).strip()
        if not target:
            continue
        grouped.setdefault(target, []).append(dict(todo))
        target_kinds.setdefault(target, str(todo.get("target_kind", "part") or "part"))
    result: list[dict[str, Any]] = []
    for target in sorted(grouped):
        group_id = f"{phase}:{target}"
        result.append(
            TodoGroup(
                id=group_id,
                phase=phase,
                target_name=target,
                target_kind=target_kinds.get(target, "part"),
                role=role,
                review_role=review_role,
                todos=grouped[target],
                focused_prompt=build_focused_todo_prompt(
                    {
                        "id": group_id,
                        "phase": phase,
                        "target_name": target,
                        "role": role,
                        "review_role": review_role,
                        "todos": grouped[target],
                    }
                ),
            ).to_dict()
        )
    return result


def next_todo_group(groups: list[dict[str, Any]]) -> dict[str, Any] | None:
    for group in groups:
        if str(group.get("status", "pending")) in {"pending", "needs_revision"}:
            return group
    return None


def mark_todo_group_status(
    groups: list[dict[str, Any]],
    group_id: str,
    status: str,
    *,
    agent_output: str = "",
    review_output: str = "",
    accepted_summary: str = "",
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for group in groups:
        current = dict(group)
        if str(current.get("id", "")) == group_id:
            current["status"] = status
            if agent_output:
                current["agent_output"] = agent_output
            if review_output:
                current["review_output"] = review_output
            if accepted_summary:
                current["accepted_summary"] = accepted_summary
        updated.append(current)
    return updated


def sync_todo_group_status_with_coverage(
    groups: list[dict[str, Any]],
    todos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    missing_by_target: dict[str, bool] = {}
    complete_by_target: dict[str, bool] = {}
    for todo in todos:
        target = str(todo.get("target_name", "")).strip()
        if not target:
            continue
        status = str(todo.get("status", "pending"))
        required = bool(todo.get("required", True))
        if required and status == "missing":
            missing_by_target[target] = True
        complete_by_target[target] = complete_by_target.get(target, True) and status in {"covered", "not_applicable"}
    updated: list[dict[str, Any]] = []
    for group in groups:
        current = dict(group)
        target = str(current.get("target_name", "")).strip()
        if missing_by_target.get(target):
            current["status"] = "needs_revision"
        elif complete_by_target.get(target):
            current["status"] = "accepted"
        updated.append(current)
    return updated


def coverage_revision_requests(
    todos: list[dict[str, Any]],
    groups: list[dict[str, Any]] | None = None,
    *,
    owner: str = "",
    reviewer: str = "reviewer",
) -> list[dict[str, Any]]:
    group_by_target = {str(group.get("target_name", "")).strip(): dict(group) for group in groups or []}
    missing_by_target: dict[str, list[dict[str, Any]]] = {}
    for todo in todos:
        if not bool(todo.get("required", True)) or str(todo.get("status")) != "missing":
            continue
        target = str(todo.get("target_name", "")).strip()
        if not target:
            continue
        missing_by_target.setdefault(target, []).append(dict(todo))
    requests: list[dict[str, Any]] = []
    for target in sorted(missing_by_target):
        group = group_by_target.get(target, {})
        missing = missing_by_target[target]
        phase = str(group.get("phase") or missing[0].get("phase") or "").strip()
        group_id = str(group.get("id") or f"{phase}:{target}").strip(":")
        reasons = [str(todo.get("missing_reason", "") or todo.get("task", "")).strip() for todo in missing]
        requests.append(
            {
                "id": f"revision:{group_id}",
                "phase": phase,
                "group_id": group_id,
                "target_name": target,
                "target_kind": str(group.get("target_kind") or missing[0].get("target_kind") or "part"),
                "owner": str(group.get("role") or owner).strip(),
                "reviewer": str(group.get("review_role") or reviewer).strip(),
                "status": "needs_revision",
                "reason": "; ".join(reason for reason in reasons if reason),
                "missing_todos": missing,
                "focused_prompt": group.get("focused_prompt", ""),
                "agent_output": group.get("agent_output", ""),
                "review_output": group.get("review_output", ""),
                "accepted_summary": group.get("accepted_summary", ""),
            }
        )
    return requests


def coverage_clarification_requests(
    revision_requests: list[dict[str, Any]],
    *,
    audience: str = "user",
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for request in revision_requests:
        missing_todos = [
            dict(todo)
            for todo in list(request.get("missing_todos", []) or [])
            if bool(todo.get("required", True)) and str(todo.get("status", "")) == "missing"
        ]
        if not missing_todos:
            continue
        target = str(request.get("target_name", "")).strip()
        phase = str(request.get("phase", "")).strip()
        if not target or not phase:
            continue
        questions = [_clarification_question(target, todo) for todo in missing_todos]
        requests.append(
            {
                "id": f"clarification:{phase}:{target}",
                "phase": phase,
                "target_name": target,
                "target_kind": str(request.get("target_kind") or "part"),
                "audience": audience,
                "status": "pending",
                "source_revision_request": str(request.get("id", "")),
                "reason": str(request.get("reason", "")).strip(),
                "missing_todos": missing_todos,
                "questions": questions,
                "prompt": _clarification_prompt(target, questions),
            }
        )
    return requests


def build_focused_todo_prompt(group: dict[str, Any]) -> str:
    target = str(group.get("target_name", "")).strip()
    phase = str(group.get("phase", "")).strip()
    tasks = [
        str(todo.get("task", "")).strip()
        for todo in list(group.get("todos", []) or [])
        if str(todo.get("task", "")).strip()
    ]
    task_text = ", ".join(tasks) if tasks else "the listed coverage requirements"
    return (
        f"Focus only on `{target}` for the {phase} phase. "
        f"Address: {task_text}. Do not solve other targets. "
        "Write phase content for this target only. "
        "If required information is missing, report it as unresolved instead of inventing details. "
        "Do not declare todo status as covered, accepted, complete, or resolved; Python updates todo status after artifact validation."
    )


def mark_spec_coverage(todos: list[dict[str, Any]], spec_artifact: Any, design_artifact: Any | None = None) -> list[dict[str, Any]]:
    spec_parts = getattr(spec_artifact, "parts", {}) or {}
    design_counts = {part["name"]: part["instance_count"] for part in _design_parts(design_artifact)}
    marked: list[dict[str, Any]] = []
    for todo in todos:
        current = dict(todo)
        name = str(current.get("target_name", "")).strip()
        spec = spec_parts.get(name) if isinstance(spec_parts, dict) else None
        if current.get("task") == "spec_part_exists":
            _set_status(current, spec is not None, "part exists in SpecArtifact.parts", "missing part spec")
        elif current.get("task") == "spec_geometry_defined":
            _set_status(current, _has_geometry(spec), "primitive or target_bbox is specified", "missing geometry spec")
        elif current.get("task") == "spec_instance_count_preserved":
            expected = int(design_counts.get(name, 1) or 1)
            if expected <= 1:
                _set_status(current, True, "single instance does not require explicit count", "")
            else:
                actual = _instance_count_from_mapping(spec)
                _set_status(
                    current,
                    actual == expected,
                    f"instance_count={actual}",
                    f"expected instance_count={expected}, got {actual if actual is not None else 'missing'}",
                )
        marked.append(current)
    return marked


def mark_plan_coverage(todos: list[dict[str, Any]], plan_artifact: Any, part_families: list[Any] | None = None) -> list[dict[str, Any]]:
    family_counts = {item["name"]: item["instance_count"] for item in _family_records(None, part_families or [])}
    build_families = _families_in_items(getattr(plan_artifact, "build_responsibilities", []) or [])
    assembly_families = _families_in_items(getattr(plan_artifact, "assembly_responsibilities", []) or [])
    step_counts = _step_instance_counts(getattr(plan_artifact, "steps", []) or [])
    marked: list[dict[str, Any]] = []
    for todo in todos:
        current = dict(todo)
        name = str(current.get("target_name", "")).strip()
        if current.get("task") == "plan_build_responsibility":
            _set_status(current, name in build_families, "build responsibility exists", "missing build responsibility")
        elif current.get("task") == "plan_assembly_responsibility":
            _set_status(current, name in assembly_families, "assembly responsibility exists", "missing assembly responsibility")
        elif current.get("task") == "plan_instance_count_preserved":
            expected = int(family_counts.get(name, 1) or 1)
            actual = step_counts.get(name)
            if expected <= 1:
                _set_status(current, True, "single instance does not require explicit count", "")
            else:
                _set_status(
                    current,
                    actual == expected,
                    f"instance_count={actual}",
                    f"expected instance_count={expected}, got {actual if actual is not None else 'missing'}",
                )
        marked.append(current)
    return marked


def coverage_open_issues(todos: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for todo in todos:
        if bool(todo.get("required", True)) and str(todo.get("status")) == "missing":
            target = str(todo.get("target_name", "")).strip()
            task = str(todo.get("task", "")).strip()
            reason = str(todo.get("missing_reason", "")).strip()
            issues.append(f"Coverage gap for {target}: {task} ({reason}).")
    return issues


def coverage_quality_flags(todos: list[dict[str, Any]]) -> list[str]:
    return ["coverage_gap"] if coverage_open_issues(todos) else []


def coverage_summary(todos: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in sorted(TODO_STATUSES)}
    for todo in todos:
        status = str(todo.get("status", "pending"))
        counts[status if status in counts else "pending"] += 1
    required_missing = [
        str(todo.get("id", ""))
        for todo in todos
        if bool(todo.get("required", True)) and str(todo.get("status")) == "missing"
    ]
    return {
        "total": len(todos),
        "counts": counts,
        "required_missing": required_missing,
        "complete": not required_missing and all(str(todo.get("status")) in {"covered", "not_applicable"} for todo in todos),
    }


def compact_coverage_todos(todos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    visible = []
    for todo in todos:
        status = str(todo.get("status", "pending"))
        if status == "covered" and bool(todo.get("required", True)):
            continue
        visible.append(
            {
                "id": todo.get("id", ""),
                "target_name": todo.get("target_name", ""),
                "task": todo.get("task", ""),
                "status": status,
                "required": bool(todo.get("required", True)),
                "missing_reason": todo.get("missing_reason", ""),
            }
        )
    return visible


def coverage_interaction_contract(phase: str = "") -> dict[str, Any]:
    phase_name = str(phase or "").strip()
    return {
        "authority": "python_process",
        "purpose": "Track whether accepted upstream parts are covered by the current phase output.",
        "agent_may": [
            "address pending or missing todos in the current meeting turn",
            "explain why a todo cannot be covered with current information",
            "flag a required missing todo as blocking",
        ],
        "agent_must_not": [
            "create new authoritative todo ids",
            "rename todo target_name values",
            "mark todos covered by assertion alone",
            "declare todo status as covered, accepted, complete, or resolved",
            "remove or downgrade required todos",
        ],
        "python_will": [
            "generate the authoritative todo list before the phase",
            "validate extracted artifacts after the meeting",
            "mark todo status as covered, missing, or not_applicable",
            "persist missing required todos as open issues and coverage_gap flags",
        ],
        "phase": phase_name,
    }


def _clarification_question(target: str, todo: dict[str, Any]) -> str:
    task = str(todo.get("task", "")).strip()
    reason = str(todo.get("missing_reason", "")).strip()
    if task == "spec_geometry_defined":
        return f"What explicit dimensions or accepted geometry constraints should `{target}` use?"
    if task == "spec_part_exists":
        return f"Should `{target}` remain an accepted part in this model?"
    if task == "spec_instance_count_preserved":
        return f"What exact instance count should `{target}` preserve?"
    if task == "plan_build_responsibility":
        return f"Who should build `{target}`, and what build responsibility should be recorded?"
    if task == "plan_assembly_responsibility":
        return f"How should `{target}` be assembled, parented, or attached?"
    if task == "plan_instance_count_preserved":
        return f"What exact planned instance count should `{target}` preserve?"
    return f"What information is required to resolve `{target}` ({reason or task})?"


def _clarification_prompt(target: str, questions: list[str]) -> str:
    if not questions:
        return f"Clarify the missing information for `{target}`."
    bullet_text = " ".join(f"{index}. {question}" for index, question in enumerate(questions, start=1))
    return f"Clarify `{target}` before continuing: {bullet_text}"


def _design_parts(design_artifact: Any) -> list[dict[str, Any]]:
    if design_artifact is None:
        return []
    parts = getattr(design_artifact, "parts", design_artifact if isinstance(design_artifact, (dict, list)) else [])
    if isinstance(parts, dict):
        iterable = [{"name": key, **(value if isinstance(value, dict) else {})} for key, value in parts.items()]
    elif isinstance(parts, list):
        iterable = [item for item in parts if isinstance(item, dict)]
    else:
        iterable = []
    records = []
    for item in iterable:
        name = str(item.get("name") or item.get("family") or item.get("part_name") or "").strip()
        if not name:
            continue
        records.append({"name": name, "instance_count": _coerce_int(item.get("instance_count", item.get("count", 1)), 1)})
    return records


def _family_records(spec_artifact: Any, part_families: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for family in part_families or []:
        if isinstance(family, dict):
            name = str(family.get("name", "")).strip()
            count = _coerce_int(family.get("instance_count", family.get("count", 1)), 1)
        else:
            name = str(getattr(family, "name", "")).strip()
            count = _coerce_int(getattr(family, "instance_count", 1), 1)
        if name:
            records.append({"name": name, "instance_count": count})
    if records or spec_artifact is None:
        return records
    spec_parts = getattr(spec_artifact, "parts", {}) or {}
    if isinstance(spec_parts, dict):
        return [{"name": str(name), "instance_count": _instance_count_from_mapping(value) or 1} for name, value in spec_parts.items() if str(name).strip()]
    return []


def _has_geometry(spec: Any) -> bool:
    if not isinstance(spec, dict):
        return False
    geometry_source = str(spec.get("geometry_source", "") or "").strip().lower()
    if geometry_source in {"assumed", "default", "provisional", "needs_user_input"}:
        return False
    if spec.get("assumptions") and geometry_source != "accepted_assumption":
        return False
    bbox = spec.get("target_bbox")
    if isinstance(bbox, dict) and all(_try_float(bbox.get(key)) is not None for key in ("width", "depth", "height")):
        return True
    geometry = spec.get("geometry")
    if isinstance(geometry, dict):
        return bool(geometry)
    if isinstance(geometry, str):
        return bool(geometry.strip())
    primitive = str(spec.get("primitive", "") or "").strip()
    description = str(spec.get("description", "") or "").strip()
    if geometry_source in {"markdown_spec", "accepted_markdown", "accepted_markdown_plane", "accepted_task_primitive"}:
        return bool(primitive and description)
    return False


def _instance_count_from_mapping(value: Any) -> int | None:
    if not isinstance(value, dict):
        return None
    for key in ("instance_count", "count", "instances"):
        if key in value:
            return _coerce_int(value.get(key), 0)
    return None


def _families_in_items(items: list[Any]) -> set[str]:
    names = set()
    for item in items:
        if isinstance(item, dict):
            name = str(item.get("family") or item.get("part") or item.get("name") or "").strip()
            if name:
                names.add(name)
    return names


def _step_instance_counts(steps: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        if not isinstance(step, dict):
            continue
        name = str(step.get("family") or step.get("part") or "").strip()
        if not name:
            continue
        counts[name] = _coerce_int(step.get("instance_count", step.get("count", 1)), 1)
    return counts


def _set_status(todo: dict[str, Any], covered: bool, evidence: str, missing_reason: str) -> None:
    todo["status"] = "covered" if covered else "missing"
    todo["evidence"] = evidence if covered else ""
    todo["missing_reason"] = "" if covered else missing_reason


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _try_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
