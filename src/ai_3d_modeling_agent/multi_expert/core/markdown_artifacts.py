"""Markdown-first runtime artifacts for the multi-expert pipeline."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ai_3d_modeling_agent.memory.session_paths import ensure_session_runtime_dir
from ai_3d_modeling_agent.multi_expert.artifacts import DesignArtifact, PlanArtifact, SpecArtifact


ARTIFACT_SCHEMA_VERSION = 1


def artifact_dir(context: Any) -> Path | None:
    payload = context if isinstance(context, dict) else {}
    runtime_root = payload.get("runtime_root")
    session_id = str(payload.get("session_id", "") or "").strip()
    if not runtime_root or not session_id:
        return None
    root = ensure_session_runtime_dir(Path(str(runtime_root)), session_id)
    path = root / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_design_markdown(context: Any, artifact: DesignArtifact, *, meeting_state: Any = None) -> None:
    _write_artifact(
        context,
        filename="design.md",
        phase="design",
        status=_phase_status(meeting_state),
        summary=artifact.summary,
        depends_on=[],
        next_phase="spec",
        content=_render_design_doc(artifact, meeting_state),
    )


def write_spec_markdown(context: Any, artifact: SpecArtifact, *, design: DesignArtifact, meeting_state: Any = None) -> None:
    _write_artifact(
        context,
        filename="spec.md",
        phase="spec",
        status=_phase_status(meeting_state),
        summary=artifact.summary,
        depends_on=["design.md"],
        next_phase="plan",
        content=_render_spec_doc(artifact, design, meeting_state),
    )


def write_plan_markdown(context: Any, artifact: PlanArtifact, *, meeting_state: Any = None) -> None:
    _write_artifact(
        context,
        filename="build_plan.md",
        phase="plan",
        status=_phase_status(meeting_state),
        summary=artifact.summary,
        depends_on=["design.md", "spec.md"],
        next_phase="build",
        content=_render_plan_doc(artifact, meeting_state),
    )
    write_todo_markdown(context, todos=build_builder_todos_from_plan(artifact), current_todo="")


def write_todo_markdown(context: Any, *, todos: list[dict[str, Any]], current_todo: str = "") -> None:
    lines = ["# Build Todo", ""]
    for todo in todos:
        status = "x" if str(todo.get("status", "")) == "done" else " "
        lines.append(f"- [{status}] {todo.get('id', '')}: {todo.get('task', '')}")
    if not todos:
        lines.append("- [ ] No build todos generated.")
    _write_artifact(
        context,
        filename="todo.md",
        phase="build",
        status="pending",
        summary=f"{len(todos)} builder todos",
        depends_on=["build_plan.md"],
        next_phase="build",
        content="\n".join(lines).rstrip() + "\n",
        current_todo=current_todo,
    )


def append_build_log(context: Any, *, title: str, body: str, validation: dict[str, Any] | None = None) -> None:
    directory = artifact_dir(context)
    if directory is None:
        return
    path = directory / "build_log.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Build Log\n\n"
    validation_text = ""
    if validation:
        validation_text = "\n\n```json\n" + json.dumps(validation, ensure_ascii=False, indent=2) + "\n```"
    path.write_text(existing.rstrip() + f"\n\n## {title}\n\n{body.strip()}{validation_text}\n", encoding="utf-8")
    _update_index(
        directory,
        {
            "phase": "build",
            "artifact_type": "markdown_doc",
            "path": "build_log.md",
            "status": "updated",
            "version": _next_version(directory, "build_log.md"),
            "summary": title,
            "depends_on": ["todo.md", "build_plan.md"],
            "current_todo": "",
            "next_phase": "validate",
        },
    )


def build_design_artifact_from_markdown_state(
    task_prompt: str,
    meeting_state: Any,
    *,
    conversation: Any = None,
) -> DesignArtifact:
    summary = _state_summary(meeting_state) or f"Design accepted for: {task_prompt}"
    extraction_corpus = _design_markdown_corpus(meeting_state, conversation=conversation) or summary
    names = list(dict.fromkeys([*_extract_part_names(extraction_corpus), *_extract_part_names(task_prompt)]))
    names = _filter_instance_variant_part_names(names, extraction_corpus + " " + task_prompt)
    names = _filter_container_helper_part_names(names)
    if _is_simple_cube_task(task_prompt):
        names = ["cube"]
    if not names:
        names = ["main_object"]
    parts = []
    for name in names:
        parts.append(
            {
                "name": name,
                "description": f"{name} part from accepted design discussion",
                "instance_count": _instance_count_for_name(name, extraction_corpus + " " + task_prompt),
                "parent_name": None,
                "symmetry_group": "NONE",
            }
        )
    return DesignArtifact(
        task_prompt=task_prompt,
        parts=parts,
        assembly_concept=summary,
        unresolved_issues=[_issue_summary(issue) for issue in getattr(meeting_state, "open_issues", []) or []],
        summary=summary,
    )


def build_spec_artifact_from_markdown_state(design: DesignArtifact, meeting_state: Any) -> SpecArtifact:
    corpus = _spec_markdown_corpus(meeting_state)
    parts: dict[str, Any] = {}
    for item in list(design.parts or []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        if not name:
            continue
        part_text = _spec_markdown_corpus_for_part(meeting_state, name) or _text_for_part(corpus, name)
        dimensions = _extract_bbox_from_markdown(part_text)
        geometry = _extract_geometry_description(part_text)
        geometry_source = "accepted_markdown" if dimensions else "markdown_spec"
        design_task_text = " ".join(
            str(value or "")
            for value in (
                getattr(design, "task_prompt", ""),
                getattr(design, "summary", ""),
                getattr(design, "assembly_concept", ""),
            )
        )
        if not dimensions and _is_simple_cube_part(name, design_task_text, part_text):
            dimensions = {"width": 1.0, "depth": 1.0, "height": 1.0}
            geometry = geometry or "Unit cube primitive inferred from the explicit simple cube task."
            geometry_source = "accepted_task_primitive"
        if {"width", "height"} <= set(dimensions) and "depth" not in dimensions and _looks_like_flat_plane(part_text):
            dimensions = {**dimensions, "depth": 0.02}
            geometry_source = "accepted_markdown_plane"
        elif dimensions and len(dimensions) == 2 and _looks_like_flat_plane(part_text):
            dimensions = {**dimensions, "height": 0.02}
            geometry_source = "accepted_markdown_plane"
        parts[name] = {
            "instance_count": int(item.get("instance_count", 1) or 1),
            "primitive": _extract_primitive(part_text) or "cube",
            "target_bbox": dimensions if {"width", "depth", "height"} <= set(dimensions) else {},
            "geometry_source": geometry_source,
            "description": geometry or str(item.get("description", "")),
            "attachment_points": [],
        }
        if geometry and {"width", "depth", "height"} <= set(dimensions):
            parts[name]["geometry"] = geometry
    summary = _state_summary(meeting_state) or "Specification captured as Markdown; concrete geometry may require focused builder steps."
    return SpecArtifact(
        blueprint_id="spec-md-001",
        parts=parts,
        validation_notes=[_issue_summary(issue) for issue in getattr(meeting_state, "open_issues", []) or []],
        summary=summary,
    )


def build_builder_todos_from_plan(plan: PlanArtifact) -> list[dict[str, Any]]:
    todos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for responsibility in list(plan.build_responsibilities or []):
        if not isinstance(responsibility, dict):
            continue
        family = str(responsibility.get("family", "") or "").strip()
        if not family or family in seen:
            continue
        seen.add(family)
        todos.append({"id": f"build:{family}", "task": f"Create and validate {family}", "status": "pending"})
    for responsibility in list(plan.assembly_responsibilities or []):
        if not isinstance(responsibility, dict):
            continue
        family = str(responsibility.get("family", "") or "").strip()
        if not family:
            continue
        todos.append({"id": f"place:{family}", "task": f"Place and validate {family}", "status": "pending"})
    return todos


def _write_artifact(
    context: Any,
    *,
    filename: str,
    phase: str,
    status: str,
    summary: str,
    depends_on: list[str],
    next_phase: str,
    content: str,
    current_todo: str = "",
) -> None:
    directory = artifact_dir(context)
    if directory is None:
        return
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    _update_index(
        directory,
        {
            "phase": phase,
            "artifact_type": "markdown_doc",
            "path": filename,
            "status": status,
            "version": _next_version(directory, filename),
            "summary": summary,
            "depends_on": depends_on,
            "current_todo": current_todo,
            "next_phase": next_phase,
        },
    )


def _update_index(directory: Path, entry: dict[str, Any]) -> None:
    path = directory / "artifact_index.json"
    if path.exists():
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            index = {}
    else:
        index = {}
    artifacts = [item for item in index.get("artifacts", []) if isinstance(item, dict)]
    artifacts = [item for item in artifacts if item.get("path") != entry.get("path")]
    artifacts.append(entry)
    index = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifacts": artifacts,
    }
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _next_version(directory: Path, filename: str) -> int:
    path = directory / "artifact_index.json"
    if not path.exists():
        return 1
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 1
    for item in index.get("artifacts", []):
        if isinstance(item, dict) and item.get("path") == filename:
            try:
                return int(item.get("version", 0)) + 1
            except (TypeError, ValueError):
                return 1
    return 1


def _render_design_doc(artifact: DesignArtifact, meeting_state: Any) -> str:
    return "\n".join(
        [
            "# Design",
            "",
            "## User Task",
            artifact.task_prompt or "",
            "",
            "## Accepted Parts",
            *_part_lines(artifact.parts),
            "",
            "## Rejected Ideas",
            *_state_list(meeting_state, "rejected_alternatives"),
            "",
            "## Open Questions",
            *(_list_lines(artifact.unresolved_issues) or ["- None"]),
            "",
            "## Design Summary",
            artifact.summary or artifact.assembly_concept or "",
            "",
        ]
    )


def _render_spec_doc(artifact: SpecArtifact, design: DesignArtifact, meeting_state: Any) -> str:
    lines = ["# Specification", "", "## Source Design", design.summary or "", "", "## Part Specifications"]
    for name, spec in (artifact.parts or {}).items():
        lines.extend(["", f"### {name}", str(spec.get("description", "")) if isinstance(spec, dict) else str(spec)])
        if isinstance(spec, dict):
            lines.append(f"- Primitive: {spec.get('primitive', 'cube')}")
            lines.append(f"- Instance count: {spec.get('instance_count', 1)}")
            lines.append(f"- Geometry source: {spec.get('geometry_source', 'markdown_spec')}")
            bbox = spec.get("target_bbox")
            if isinstance(bbox, dict) and bbox:
                lines.append(
                    "- Target bbox: "
                    f"width={bbox.get('width')}, depth={bbox.get('depth')}, height={bbox.get('height')}"
                )
            geometry = spec.get("geometry")
            if geometry:
                lines.append(f"- Geometry: {geometry}")
    lines.extend(["", "## Assumptions", *(_list_lines(artifact.validation_notes) or ["- None"])])
    lines.extend(["", "## Open Questions", *_state_list(meeting_state, "open_issues")])
    return "\n".join(lines).rstrip() + "\n"


def _render_plan_doc(artifact: PlanArtifact, meeting_state: Any) -> str:
    lines = ["# Build Plan", "", "## Build Strategy", artifact.summary or ""]
    lines.extend(["", "## Ordered Todos"])
    for todo in build_builder_todos_from_plan(artifact):
        lines.append(f"- [ ] {todo['id']}: {todo['task']}")
    lines.extend(["", "## Validation Criteria"])
    lines.append("- Python validates each builder step with scene queries before advancing.")
    lines.extend(["", "## Known Risks", *(_list_lines(artifact.risk_hotspots or artifact.open_issues) or ["- None"])])
    lines.extend(["", "## Meeting Notes", *_state_list(meeting_state, "open_issues")])
    return "\n".join(lines).rstrip() + "\n"


def _part_lines(parts: Any) -> list[str]:
    lines: list[str] = []
    for item in list(parts or []):
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        count = item.get("instance_count", 1)
        description = item.get("description", "")
        lines.append(f"- {name} x{count}: {description}")
    return lines or ["- main_object x1: accepted design object"]


def _state_list(state: Any, attr: str) -> list[str]:
    values = getattr(state, attr, []) or []
    return _list_lines([_issue_summary(item) for item in values])


def _list_lines(values: Any) -> list[str]:
    lines: list[str] = []
    for item in list(values or []):
        if isinstance(item, dict):
            text = str(item.get("summary") or item.get("reason") or item)
        else:
            text = _issue_summary(item)
        if text:
            lines.append(f"- {text}")
    return lines


def _phase_status(state: Any) -> str:
    return str(getattr(state, "phase_status", "") or "accepted")


def _state_summary(state: Any) -> str:
    return str(getattr(state, "last_resolution_summary", "") or getattr(state, "round_change_summary", "") or "").strip()


def _design_markdown_corpus(state: Any, *, conversation: Any = None) -> str:
    chunks: list[str] = []
    for message in list(getattr(conversation, "messages", []) or []):
        value = str(getattr(message, "content", "") or "").strip()
        if value:
            chunks.append(value)
    for attr in ("last_resolution_summary", "round_change_summary"):
        value = str(getattr(state, attr, "") or "").strip()
        if value:
            chunks.append(value)
    for attr in ("accepted_decisions", "resolution_history", "resolved_challenges", "todo_groups"):
        for item in list(getattr(state, attr, []) or []):
            if isinstance(item, dict):
                keys = (
                    "summary",
                    "change_summary",
                    "resolution_note",
                    "accepted_revision",
                    "accepted_summary",
                    "agent_output",
                    "review_output",
                )
                for key in keys:
                    value = str(item.get(key, "") or "").strip()
                    if value:
                        chunks.append(value)
            else:
                for attr_name in ("summary", "rationale", "evidence"):
                    value = str(getattr(item, attr_name, "") or "").strip()
                    if value:
                        chunks.append(value)
    return "\n\n".join(chunks)


def _spec_markdown_corpus(state: Any) -> str:
    chunks: list[str] = []
    for attr in ("last_resolution_summary", "round_change_summary"):
        value = str(getattr(state, attr, "") or "").strip()
        if value:
            chunks.append(value)
    for attr in ("todo_groups", "revision_requests"):
        for item in list(getattr(state, attr, []) or []):
            if not isinstance(item, dict):
                continue
            for key in ("accepted_summary", "agent_output", "review_output", "focused_prompt", "reason"):
                value = str(item.get(key, "") or "").strip()
                if value:
                    chunks.append(value)
    return "\n\n".join(chunks)


def _spec_markdown_corpus_for_part(state: Any, part_name: str) -> str:
    chunks: list[str] = []
    name = str(part_name or "").strip().lower()
    if not name:
        return ""
    for attr in ("todo_groups", "revision_requests"):
        for item in list(getattr(state, attr, []) or []):
            if not isinstance(item, dict):
                continue
            target = str(item.get("target_name", "") or "").strip().lower()
            if target != name:
                continue
            for key in ("accepted_summary", "agent_output", "review_output", "reason", "focused_prompt"):
                value = str(item.get(key, "") or "").strip()
                if value:
                    chunks.append(value)
    if chunks:
        return "\n\n".join(chunks)
    for attr in ("last_resolution_summary", "round_change_summary"):
        value = str(getattr(state, attr, "") or "").strip()
        if value and re.search(rf"\b{re.escape(name)}\b", value, re.IGNORECASE):
            chunks.append(value)
    return "\n\n".join(chunks)


def _text_for_part(corpus: str, part_name: str) -> str:
    if not part_name:
        return corpus
    name_pattern = re.compile(rf"\b{re.escape(part_name)}\b", re.IGNORECASE)
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", corpus or "") if chunk.strip()]
    selected = [chunk for chunk in paragraphs if name_pattern.search(chunk)]
    return "\n\n".join(selected or paragraphs)


def _extract_geometry_description(text: str) -> str:
    lines = [line.strip(" -*\t") for line in (text or "").splitlines() if line.strip()]
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in ("geometry", "rectangle", "plane", "cube", "box", "cylinder", "dimensions")):
            return _strip_markdown(line)
    return ""


def _extract_primitive(text: str) -> str:
    lowered = (text or "").lower()
    if any(token in lowered for token in ("cylinder", "cylindrical", "round rod")):
        return "cylinder"
    if any(token in lowered for token in ("plane", "rectangle", "box", "cube", "flat")):
        return "cube"
    return ""


def _is_simple_cube_part(name: str, task_prompt: str, part_text: str) -> bool:
    normalized_name = re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")
    if normalized_name not in {"cube", "cube_body", "main_cube"}:
        return False
    text = f"{task_prompt} {part_text}".lower()
    if not _is_simple_cube_task(text):
        return False
    return True


def _is_simple_cube_task(text: str) -> bool:
    text = str(text or "").lower()
    if "simple cube" not in text and not re.search(r"\b(?:build|create|make|model)\b.*\bcube\b", text):
        return False
    complex_terms = (
        "chair",
        "table",
        "vehicle",
        "character",
        "room",
        "building",
        "multiple",
        "several",
        "stack",
    )
    return not any(term in text for term in complex_terms)


def _extract_bbox_from_markdown(text: str) -> dict[str, float]:
    labeled = _extract_labeled_dimensions(text)
    if {"width", "depth", "height"} <= set(labeled):
        return {key: labeled[key] for key in ("width", "depth", "height")}
    if {"depth", "height"} <= set(labeled) and "width" not in labeled and "cylind" in (text or "").lower():
        return {"width": labeled["depth"], "depth": labeled["depth"], "height": labeled["height"]}
    if {"diameter", "height"} <= set(labeled):
        return {"width": labeled["diameter"], "depth": labeled["diameter"], "height": labeled["height"]}
    if {"width", "height"} <= set(labeled):
        return {"width": labeled["width"], "height": labeled["height"]}
    sequence = _extract_dimension_sequence(text)
    if len(sequence) >= 3:
        return {"width": sequence[0], "depth": sequence[1], "height": sequence[2]}
    if len(sequence) == 2:
        return {"width": sequence[0], "depth": sequence[1]}
    return labeled if {"width", "depth", "height"} <= set(labeled) else {}


def _extract_labeled_dimensions(text: str) -> dict[str, float]:
    result: dict[str, float] = {}
    source = _normalize_dimension_text(text)
    shorthand = _extract_lwh_dimensions(source)
    if shorthand:
        result.update(shorthand)
    label_map = {
        "width": "width",
        "length": "width",
        "depth": "depth",
        "height": "height",
        "thickness": "height",
        "diameter": "diameter",
        "radius": "radius",
    }
    pattern = re.compile(
        r"\b(width|length|depth|height|thickness|diameter|radius)\b\s*[:=]?\s*"
        r"([-+]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?",
        re.IGNORECASE,
    )
    for label, raw, unit in pattern.findall(source):
        key = label_map.get(label.lower())
        if key and key not in result:
            value = _convert_unit(float(raw), unit)
            result[key] = value * 2 if key == "radius" else value
    suffix_pattern = re.compile(
        r"([-+]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?\s*"
        r"\b(w|width|d|depth|h|height|diameter|radius)\b",
        re.IGNORECASE,
    )
    suffix_map = {
        "w": "width",
        "width": "width",
        "d": "depth",
        "depth": "depth",
        "h": "height",
        "height": "height",
        "diameter": "diameter",
        "radius": "radius",
    }
    for raw, unit, suffix in suffix_pattern.findall(source):
        key = suffix_map.get(suffix.lower())
        if key and key not in result:
            value = _convert_unit(float(raw), unit)
            result[key] = value * 2 if key == "radius" else value
    return result


def _extract_lwh_dimensions(text: str) -> dict[str, float]:
    matches: dict[str, float] = {}
    pattern = re.compile(
        r"\b([LWDH])\b\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*"
        r"(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?",
        re.IGNORECASE,
    )
    for label, raw, unit in pattern.findall(text or ""):
        key = label.upper()
        value = _convert_unit(float(raw), unit)
        if key not in matches:
            matches[key] = value
    result: dict[str, float] = {}
    if "L" in matches:
        result["width"] = matches["L"]
    if "W" in matches:
        result["depth"] = matches["W"] if "L" in matches else matches["W"]
        if "width" not in result:
            result["width"] = matches["W"]
    if "D" in matches:
        result["depth"] = matches["D"]
    if "H" in matches:
        result["height"] = matches["H"]
    return result


def _extract_dimension_sequence(text: str) -> list[float]:
    compact = _normalize_dimension_text(text).replace("\\times", " x ").replace("×", " x ").replace("*", " x ")
    pattern = re.compile(
        r"([-+]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?"
        r"(?:\s*x\s*([-+]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?)"
        r"(?:\s*x\s*([-+]?\d+(?:\.\d+)?)\s*(mm|millimeter|millimeters|cm|centimeter|centimeters|m|meter|meters|in|inch|inches)?)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(compact):
        raw_values = [match.group(1), match.group(3), match.group(5)]
        raw_units = [match.group(2), match.group(4), match.group(6)]
        values = []
        default_unit = next((unit for unit in raw_units if unit), "")
        for raw, unit in zip(raw_values, raw_units):
            if raw is None:
                continue
            values.append(_convert_unit(float(raw), unit or default_unit))
        if len(values) >= 2:
            return values
    return []


def _normalize_dimension_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(r"\\text\s*\{\s*([^}]+?)\s*\}", r"\1", normalized)
    normalized = re.sub(r"\{\s*([A-Za-z]+)\s*\}", r"\1", normalized)
    normalized = re.sub(r"\(\s*([LWDH])\s*\)", r"\1", normalized, flags=re.IGNORECASE)
    normalized = normalized.replace("\\times", " x ").replace("×", " x ")
    normalized = normalized.replace("$", " ")
    return normalized


def _looks_like_flat_plane(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in ("flat plane", "rectangle", "rectangular", "seat"))


def _convert_unit(value: float, unit: str | None) -> float:
    normalized = str(unit or "").strip().lower()
    if normalized in {"mm", "millimeter", "millimeters"}:
        return round(value / 1000.0, 4)
    if normalized in {"cm", "centimeter", "centimeters"}:
        return round(value / 100.0, 4)
    if normalized in {"in", "inch", "inches"}:
        return round(value * 0.0254, 4)
    return round(value, 4)


def _strip_markdown(text: str) -> str:
    cleaned = re.sub(r"`([^`]+)`", r"\1", text or "")
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = cleaned.replace("$", "").replace("\\text", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _issue_summary(issue: Any) -> str:
    if isinstance(issue, str):
        return issue.strip()
    if isinstance(issue, dict):
        return str(issue.get("summary") or issue.get("reason") or "").strip()
    return str(getattr(issue, "summary", "") or issue).strip()


def _extract_part_names(text: str) -> list[str]:
    blocked = {
        "family",
        "body",
        "volume",
        "object",
        "main object",
        "main_object",
        "primary object",
        "primary_object",
        "root object",
        "root_object",
        "face",
        "edge",
        "vertex",
        "chair",
        "root",
        "assembly",
        "container",
        "chair body",
        "main body",
        "wooden chair",
        "assembly container",
        "moderator",
        "designer",
        "reviewer",
        "specifier",
        "planner",
        "builder",
        "inspector",
        "agent",
        "subagent",
    }
    names: list[str] = []
    for match in re.findall(r"`([^`]{1,48})`", text or ""):
        for raw_name in _split_part_name_token(match):
            name = _clean_part_name(raw_name)
            if name and name.lower() not in blocked:
                names.append(name)
    if not names:
        lowered = (text or "").lower()
        if "chair" in lowered:
            names.extend(["seat", "leg", "backrest"])
        if "table" in lowered:
            names.extend(["tabletop", "leg"])
        for candidate in ("seat", "leg", "backrest", "tabletop", "cube", "body", "stem", "leaf"):
            if candidate in lowered and candidate not in blocked:
                names.append(candidate)
    return list(dict.fromkeys(names))


def _split_part_name_token(value: str) -> list[str]:
    token = str(value or "").strip().strip("{}[]()")
    if "," in token:
        return [part.strip() for part in token.split(",") if part.strip()]
    return [token]


def _filter_instance_variant_part_names(names: list[str], text: str) -> list[str]:
    lowered_text = (text or "").lower()
    available = {str(name).lower() for name in names}
    filtered: list[str] = []
    for name in names:
        normalized = str(name or "").strip().lower()
        match = re.match(r"^([a-z][a-z0-9-]*?)_\d+$", normalized)
        if match:
            base = match.group(1)
            if base in available or f"{base}s" in lowered_text or f"{base} family" in lowered_text:
                continue
        filtered.append(name)
    return filtered


def _filter_container_helper_part_names(names: list[str]) -> list[str]:
    normalized_names = {str(name or "").strip().lower() for name in names}
    core_furniture_parts = {"seat", "leg", "backrest"} & normalized_names
    filtered: list[str] = []
    for name in names:
        normalized = str(name or "").strip().lower()
        if normalized in {
            "main_object",
            "main-object",
            "main_object_01",
            "object",
            "root_object",
            "primary_object",
            "chair_assembly",
            "assembly_container",
        }:
            continue
        if core_furniture_parts and (
            "support_frame" in normalized
            or normalized.endswith("_frame")
            or normalized.endswith("_assembly")
            or normalized.endswith("_container")
        ):
            continue
        filtered.append(name)
    return filtered


def _clean_part_name(value: str) -> str:
    cleaned = re.sub(r"\(\s*x?\d+\s*\)$", "", value.strip(), flags=re.IGNORECASE).strip()
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", cleaned).strip("_")
    name = re.sub(r"_x?\d+$", "", name, flags=re.IGNORECASE)
    for suffix in ("_Family", "_Body", "_Volume", "_Face", "_Edge", "_Vertex"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.lower()


def _instance_count_for_name(name: str, text: str) -> int:
    lowered = (text or "").lower()
    if name.lower() in {"leg", "legs"} and ("four" in lowered or "4" in lowered):
        return 4
    return 1


def to_plain_data(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {str(key): to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_data(item) for item in value]
    return value
