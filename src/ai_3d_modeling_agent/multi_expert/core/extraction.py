"""LLM-driven artifact extraction from phase conversations.

After a phase's multi-expert conversation terminates, this module makes
one additional Agent Orchestrator call to the moderator with a phase
extraction skill to synthesize the conversation into a structured JSON
artifact.

Uses ``extract_json_from_llm()`` from ``utils/llm_parser.py`` for robust
JSON parsing (handles markdown fences, leading/trailing commentary).
On failure, returns a partial artifact with ``failure_notes`` populated.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation, Message
from ai_3d_modeling_agent.multi_expert.core.expert import SamplingOptions
from ai_3d_modeling_agent.utils.llm_parser import extract_json_from_llm

logger = logging.getLogger(__name__)


_EXTRACTION_SKILLS: dict[str, str] = {
    "design": "extract-design-artifact",
    "spec": "extract-spec-artifact",
    "plan": "extract-plan-artifact",
    "validate": "extract-validation-artifact",
}


_EXTRACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "design": {
        "parts": [
            {
                "name": "main_body",
                "description": "single cube body",
                "instance_count": 1,
                "parent_name": None,
                "symmetry_group": "NONE",
            }
        ],
        "assembly_concept": "root object placed at the origin",
        "unresolved_issues": [],
        "summary": "design summary",
    },
    "spec": {
        "blueprint_id": "spec-001",
        "parts": {
            "main_body": {
                "instance_count": 1,
                "primitive": "cube",
                "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                "refinement_viewpoint": "front",
                "attachment_points": [
                    {
                        "id": "center",
                        "name": "center",
                        "local_offset": [0.0, 0.0, 0.0],
                        "description": "center point",
                    }
                ],
            }
        },
        "validation_notes": [],
        "summary": "spec summary",
    },
    "plan": {
        "summary": "planning summary",
        "execution_rationale": ["build root geometry before placement"],
        "build_responsibilities": [
            {
                "id": "build-main_body",
                "family": "main_body",
                "summary": "Builder creates the cube geometry.",
                "geometry_assumptions": ["Use cube primitive."],
                "deferred_placement": ["Final placement is handled by assembler."],
                "decision_refs": ["plan.build_responsibilities.main_body"],
            }
        ],
        "assembly_responsibilities": [
            {
                "id": "assemble-main_body",
                "family": "main_body",
                "summary": "Assembler places the cube at its world position.",
                "placement_relations": ["Place at world position."],
                "hierarchy_notes": ["Root object has no parent."],
                "target_parent_family": None,
                "attachment_target_family": None,
                "attachment_target_point_id": None,
                "local_anchor_point_id": "center",
                "placement_rule": "place_at_world_position",
                "required_parenting": False,
                "decision_refs": ["plan.assembly_responsibilities.main_body"],
            }
        ],
        "dependency_summary": ["main_body is a root family."],
        "ordering_constraints": [
            {
                "id": "ordering-root-main_body",
                "summary": "Build root family before assembly.",
                "depends_on": [],
                "responsibility": "builder",
                "decision_refs": ["plan.ordering_constraints.root-main_body"],
            }
        ],
        "risk_hotspots": [],
        "open_issues": [],
    },
    "validate": {
        "passed": True,
        "errors": [],
        "warnings": [],
        "comparisons": [],
    },
}


def _format_conversation_for_extraction(
    conversation: Conversation,
    *,
    phase_state: dict[str, Any] | None = None,
    last_resolution_summary: str = "",
    recent_conversation_excerpt: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if phase_state is not None:
        payload = {
            "phase_name": phase_state.get("phase_name", conversation.phase_name),
            "goal": phase_state.get("goal", ""),
            "owner_role": phase_state.get("owner_role", ""),
            "reviewer_role": phase_state.get("reviewer_role", ""),
            "accepted_decisions": _compact_json_items(phase_state.get("accepted_decisions", []), limit=6),
            "rejected_alternatives": _compact_json_items(phase_state.get("rejected_alternatives", []), limit=4),
            "open_issues": _compact_json_items(phase_state.get("open_issues", []), limit=6),
            "resolution_history": _compact_json_items(phase_state.get("resolution_history", []), limit=3),
            "last_resolution_summary": _truncate_text(last_resolution_summary or phase_state.get("last_resolution_summary", ""), 1200),
            "round_change_summary": _truncate_text(phase_state.get("round_change_summary", ""), 700),
            "phase_quality_flags": phase_state.get("phase_quality_flags", []),
            "coverage_todos": _compact_json_items(phase_state.get("coverage_todos", []), limit=12),
            "coverage_summary": phase_state.get("coverage_summary", {}),
            "todo_groups": _compact_json_items(phase_state.get("todo_groups", []), limit=8),
            "missing_contract_fields": _compact_json_items(phase_state.get("missing_contract_fields", []), limit=6),
            "clarification_attempted": bool(phase_state.get("clarification_attempted", False)),
            "clarification_resolved": bool(phase_state.get("clarification_resolved", False)),
            "recent_conversation_excerpt": _compact_json_items(recent_conversation_excerpt or [], limit=3),
        }
        return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}]

    messages: list[dict[str, str]] = []
    for msg in conversation.messages:
        if msg.speaker == "system":
            messages.append({"role": "system", "content": msg.content})
        else:
            messages.append({
                "role": "user",
            "content": f"[{msg.speaker}] {_truncate_text(msg.content, 1000)}",
            })
    return messages


def extract_design_artifact(
    conversation: Conversation,
    llm: Any,
    *,
    phase_state: dict[str, Any] | None = None,
    last_resolution_summary: str = "",
    recent_conversation_excerpt: list[dict[str, str]] | None = None,
    sampling: SamplingOptions | None = None,
) -> Any:
    from ai_3d_modeling_agent.multi_expert.artifacts import DesignArtifact

    return _do_extraction(
        conversation,
        llm,
        "design",
        DesignArtifact,
        phase_state=phase_state,
        last_resolution_summary=last_resolution_summary,
        recent_conversation_excerpt=recent_conversation_excerpt,
        sampling=sampling,
    )


def extract_spec_artifact(
    conversation: Conversation,
    llm: Any,
    *,
    phase_state: dict[str, Any] | None = None,
    last_resolution_summary: str = "",
    recent_conversation_excerpt: list[dict[str, str]] | None = None,
    sampling: SamplingOptions | None = None,
) -> Any:
    from ai_3d_modeling_agent.multi_expert.artifacts import SpecArtifact

    return _do_extraction(
        conversation,
        llm,
        "spec",
        SpecArtifact,
        phase_state=phase_state,
        last_resolution_summary=last_resolution_summary,
        recent_conversation_excerpt=recent_conversation_excerpt,
        sampling=sampling,
    )


def extract_plan_artifact(
    conversation: Conversation,
    llm: Any,
    *,
    phase_state: dict[str, Any] | None = None,
    last_resolution_summary: str = "",
    recent_conversation_excerpt: list[dict[str, str]] | None = None,
    sampling: SamplingOptions | None = None,
) -> Any:
    from ai_3d_modeling_agent.multi_expert.artifacts import PlanArtifact

    return _do_extraction(
        conversation,
        llm,
        "plan",
        PlanArtifact,
        phase_state=phase_state,
        last_resolution_summary=last_resolution_summary,
        recent_conversation_excerpt=recent_conversation_excerpt,
        sampling=sampling,
    )


def extract_validation_artifact(
    conversation: Conversation,
    llm: Any,
    *,
    sampling: SamplingOptions | None = None,
) -> Any:
    from ai_3d_modeling_agent.multi_expert.artifacts import ValidationArtifact

    return _do_extraction(conversation, llm, "validate", ValidationArtifact, sampling=sampling)


def _is_truncated(text: str) -> bool:
    """Detect if LLM response was truncated mid-JSON.

    Checks for unbalanced braces which indicate the JSON was cut off
    before completion.
    """
    text = text.strip()
    if not text:
        return False
    # Strip markdown code fences if present (```json ... ```)
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()
    # Count braces — if more opening than closing, likely truncated
    if text.count("{") > text.count("}"):
        return True
    # Check if response ends mid-value (not a normal JSON ending)
    if text and text[-1] not in ("}", "]", '"', "'", " ", "\n", "\r"):
        return True
    return False


def _add_truncation_hint(messages: list, truncated_response: str) -> list:
    """Add a hint to messages asking LLM to shorten response on retry."""
    messages = list(messages)  # shallow copy
    messages.append({
        "role": "assistant",
        "content": truncated_response,
    })
    messages.append({
        "role": "user",
        "content": (
            "Your previous response was truncated due to length. "
            "Please provide a shorter, more concise JSON response. "
            "Focus on essential fields only. "
            "Use abbreviated field names if needed."
        ),
    })
    return messages


def _prepend_extraction_contract(messages: list[dict[str, str]], phase_name: str, skill_name: str) -> list[dict[str, str]]:
    schema = _EXTRACTION_SCHEMAS.get(phase_name, {})
    contract = {
        "task": f"Extract the {phase_name} artifact from the supplied meeting state and excerpt.",
        "python_selected_structured_output": skill_name,
        "output_rules": [
            "Return exactly one JSON object and nothing else.",
            "Do not write prose before or after the JSON.",
            "Do not return a skill invocation wrapper such as skill_name/input.",
            "Use ASCII object and family names.",
            "Preserve accepted upstream instance_count values when they are present in meeting state.",
            "Do not invent dimensions, materials, attachment points, or concrete geometry that the meeting marked unresolved.",
            "If geometry is unresolved, omit target_bbox or leave it empty and record the gap in validation_notes.",
        ],
        "required_shape_example": schema,
    }
    return [
        {
            "role": "user",
            "content": json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        },
        *messages,
    ]


def _add_format_retry_hint(messages: list[dict[str, str]], phase_name: str, raw_response: str, reason: str) -> list[dict[str, str]]:
    retry = {
        "format_error": reason,
        "previous_response_preview": raw_response[:1200],
        "required_shape_example": _EXTRACTION_SCHEMAS.get(phase_name, {}),
        "output_rules": [
            "Return only the artifact JSON object.",
            "Do not return skill_name/input.",
            "Do not include markdown fences.",
            "Populate required lists/objects when the source contains enough information.",
        ],
    }
    return [
        *messages,
        {"role": "user", "content": json.dumps(retry, ensure_ascii=False, separators=(",", ":"))},
    ]


def _do_extraction(
    conversation: Conversation,
    llm: Any,
    phase_name: str,
    artifact_class: type,
    *,
    phase_state: dict[str, Any] | None = None,
    last_resolution_summary: str = "",
    recent_conversation_excerpt: list[dict[str, str]] | None = None,
    sampling: SamplingOptions | None = None,
) -> Any:
    skill_name = _EXTRACTION_SKILLS.get(phase_name, "")
    if not skill_name:
        return artifact_class(failure_notes=[f"No extraction skill for phase '{phase_name}'"])

    formatted_messages = _prepend_extraction_contract(
        _format_conversation_for_extraction(
            conversation,
            phase_state=phase_state,
            last_resolution_summary=last_resolution_summary,
            recent_conversation_excerpt=recent_conversation_excerpt,
        ),
        phase_name,
        skill_name,
    )
    max_attempts = 3
    require_complete_schema = bool(getattr(llm, "supports_agent_orchestrator", False))

    # Debug: log input size
    input_chars = sum(len(m.get("content", "")) for m in formatted_messages)
    logger.warning(
        "[EXTRACT] phase=%s | input messages=%d, total_chars=%d",
        phase_name, len(formatted_messages), input_chars,
    )

    for attempt in range(max_attempts):
        try:
            try:
                raw = llm.call(
                    system_prompt="",
                    messages=formatted_messages,
                    sampling=sampling,
                    agent="moderator",
                    label=f"{phase_name}.extraction",
                    skill=skill_name,
                    context={
                        "phase_name": phase_name,
                        "agent_role": "moderator",
                        "meeting_turn_kind": "extraction",
                        "extraction_skill": skill_name,
                    },
                )
            except TypeError as exc:
                if "unexpected keyword" not in str(exc):
                    raise
                raw = llm.call(
                    system_prompt="",
                    messages=formatted_messages,
                    sampling=sampling,
                )

            # Debug: log raw response
            logger.warning(
                "[EXTRACT] phase=%s attempt=%d | response chars=%d, "
                "opens=%d closes=%d last_char=%r",
                phase_name, attempt + 1, len(raw),
                raw.count("{"), raw.count("}"),
                raw.strip()[-1] if raw.strip() else "(empty)",
            )

            # 偵測截斷：如果被截斷，重送時加入提示
            if _is_truncated(raw):
                logger.warning(
                    "Extraction response truncated for phase '%s' (attempt %d), retrying...",
                    phase_name, attempt + 1,
                )
                # Debug: print first 500 and last 500 chars of raw response
                logger.warning(
                    "[EXTRACT] phase=%s TRUNCATED raw(first500)=%s",
                    phase_name, raw[:500],
                )
                logger.warning(
                    "[EXTRACT] phase=%s TRUNCATED raw(last500)=%s",
                    phase_name, raw[-500:],
                )
                if attempt < max_attempts - 1:
                    formatted_messages = _add_truncation_hint(formatted_messages, raw)
                    continue
                return artifact_class(
                    failure_notes=[f"Extraction failed: response truncated after {max_attempts} attempts"]
                )

            data = _normalize_extraction_json(
                extract_json_from_llm(raw, context_label=f"Extract-{phase_name}"),
            )
            data_issue = _extraction_data_issue(phase_name, data) if require_complete_schema else ""
            if data_issue:
                logger.warning(
                    "Extraction response for phase '%s' did not satisfy schema: %s",
                    phase_name,
                    data_issue,
                )
                if attempt < max_attempts - 1:
                    formatted_messages = _add_format_retry_hint(formatted_messages, phase_name, raw, data_issue)
                    continue
                return artifact_class(failure_notes=[f"Extraction failed schema validation: {data_issue}"])
            artifact = _build_artifact(phase_name, artifact_class, data)
            conversation.full_summary = getattr(artifact, "summary", "")
            return artifact
        except Exception as exc:
            logger.warning(
                "Extraction attempt %d for phase '%s' failed: %s",
                attempt + 1, phase_name, exc,
            )
            if attempt < max_attempts - 1:
                continue
            return artifact_class(
                failure_notes=[f"Extraction failed after {max_attempts} attempts: {exc}"]
            )

    return artifact_class(failure_notes=["Extraction failed: unreachable"])


def _normalize_extraction_json(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("input"), dict) and "skill_name" in data:
        return dict(data["input"])
    if isinstance(data, dict) and isinstance(data.get("artifact"), dict):
        return dict(data["artifact"])
    if not isinstance(data, dict):
        raise ValueError("Extraction result must be a JSON object")
    return data


def _extraction_data_issue(phase_name: str, data: dict[str, Any]) -> str:
    if "skill_name" in data and "input" in data:
        return "response is a skill invocation wrapper, not an artifact"
    if phase_name == "design":
        parts = data.get("parts")
        if not isinstance(parts, list) or not parts:
            return "design artifact requires a non-empty parts list"
    elif phase_name == "spec":
        parts = data.get("parts")
        if not isinstance(parts, dict) or not parts:
            return "spec artifact requires a non-empty parts object"
    elif phase_name == "plan":
        build = data.get("build_responsibilities")
        assembly = data.get("assembly_responsibilities")
        if not isinstance(build, list) or not build:
            return "plan artifact requires non-empty build_responsibilities"
        if not isinstance(assembly, list) or not assembly:
            return "plan artifact requires non-empty assembly_responsibilities"
    elif phase_name == "validate":
        if "passed" not in data:
            return "validation artifact requires passed"
    return ""


def _build_artifact(phase_name: str, artifact_class: type, data: dict[str, Any]) -> Any:
    if phase_name == "design":
        return _build_design(artifact_class, data)
    if phase_name == "spec":
        return _build_spec(artifact_class, data)
    if phase_name == "plan":
        return _build_plan(artifact_class, data)
    if phase_name == "validate":
        return _build_validation(artifact_class, data)
    return artifact_class()


def _build_design(cls: type, data: dict[str, Any]) -> Any:
    parts = data.get("parts", [])
    if not isinstance(parts, list):
        parts = []
    cleaned_parts: list[dict[str, Any]] = []
    for p in parts:
        if isinstance(p, dict) and "name" in p:
            name = _canonical_part_family_name(str(p["name"]))
            if _is_non_deliverable_family_name(name):
                continue
            instance_count = int(p.get("instance_count", 1))
            cleaned_parts.append({
                "name": name,
                "description": str(p.get("description", "")),
                "instance_count": instance_count,
                "parent_name": _canonical_optional_family_name(p.get("parent_name")),
                "symmetry_group": "NONE" if instance_count <= 1 else _normalize_symmetry_group(p.get("symmetry_group", "NONE")),
            })
    cleaned_parts = _dedupe_named_items(cleaned_parts)
    known_names = {str(part.get("name", "")).strip() for part in cleaned_parts if str(part.get("name", "")).strip()}
    for part in cleaned_parts:
        parent_name = _optional_string(part.get("parent_name"))
        if parent_name and parent_name not in known_names:
            part["parent_name"] = None
    return cls(
        parts=cleaned_parts,
        assembly_concept=str(data.get("assembly_concept", "")),
        unresolved_issues=list(data.get("unresolved_issues", [])),
        summary=str(data.get("summary", "")),
    )


def _build_spec(cls: type, data: dict[str, Any]) -> Any:
    parts = data.get("parts", {})
    if not isinstance(parts, dict):
        parts = {}
    cleaned_parts: dict[str, Any] = {}
    point_registry: dict[str, list[dict[str, Any]]] = {}
    for name, spec in parts.items():
        if isinstance(spec, dict):
            family_name = _canonical_part_family_name(str(name))
            if _is_non_deliverable_family_name(family_name):
                continue
            bbox = spec.get("target_bbox", {})
            if not isinstance(bbox, dict):
                bbox = {}
            aps = spec.get("attachment_points", [])
            if not isinstance(aps, list):
                aps = []
            cleaned_aps: list[dict[str, Any]] = []
            registry_points: list[dict[str, Any]] = []
            for ap in aps:
                if isinstance(ap, dict) and ("name" in ap or "id" in ap):
                    point_name = str(ap.get("name") or ap.get("id") or "").strip()
                    point_id = str(ap.get("id") or point_name).strip()
                    local_offset = list(ap.get("local_offset", [0, 0, 0]))
                    cleaned_aps.append({
                        "id": point_id,
                        "name": point_name,
                        "local_offset": local_offset,
                        "description": str(ap.get("description", "")),
                    })
                    registry_points.append({
                        "id": point_id,
                        "name": point_name,
                        "local_position": local_offset,
                        "description": str(ap.get("description", "")),
                    })
            cleaned_spec: dict[str, Any] = {
                "refinement_viewpoint": str(spec.get("refinement_viewpoint", "front")),
                "attachment_points": cleaned_aps,
            }
            if "instance_count" in spec or "count" in spec or "instances" in spec:
                cleaned_spec["instance_count"] = _coerce_int(
                    spec.get("instance_count", spec.get("count", spec.get("instances", 1))),
                    1,
                )
            if "primitive" in spec:
                cleaned_spec["primitive"] = _normalize_primitive(spec.get("primitive"))
            geometry_source = str(spec.get("geometry_source", "") or spec.get("source", "")).strip()
            if geometry_source:
                cleaned_spec["geometry_source"] = geometry_source
            assumptions = spec.get("assumptions", [])
            if isinstance(assumptions, list):
                cleaned_spec["assumptions"] = [str(item) for item in assumptions if str(item).strip()]
            elif str(assumptions).strip():
                cleaned_spec["assumptions"] = [str(assumptions).strip()]
            cleaned_bbox = _clean_bbox(bbox)
            if cleaned_bbox:
                cleaned_spec["target_bbox"] = cleaned_bbox
            elif "target_bbox" in spec:
                cleaned_spec["target_bbox"] = {}
            cleaned_parts[family_name] = cleaned_spec
            point_registry[family_name] = registry_points
    return cls(
        parts=cleaned_parts,
        point_registry=point_registry,
        validation_notes=[_stringify_note(item) for item in list(data.get("validation_notes", []) or [])],
        summary=str(data.get("summary", "")),
    )


def _build_plan(cls: type, data: dict[str, Any]) -> Any:
    rationale = data.get("execution_rationale", [])
    if not isinstance(rationale, list):
        rationale = []
    build_responsibilities = data.get("build_responsibilities", [])
    if not isinstance(build_responsibilities, list):
        build_responsibilities = []
    assembly_responsibilities = data.get("assembly_responsibilities", [])
    if not isinstance(assembly_responsibilities, list):
        assembly_responsibilities = []
    dependency_summary = data.get("dependency_summary", [])
    if not isinstance(dependency_summary, list):
        dependency_summary = []
    ordering_constraints = data.get("ordering_constraints", [])
    if not isinstance(ordering_constraints, list):
        ordering_constraints = []
    risk_hotspots = data.get("risk_hotspots", [])
    if not isinstance(risk_hotspots, list):
        risk_hotspots = []
    open_issues = data.get("open_issues", [])
    if not isinstance(open_issues, list):
        open_issues = []
    return cls(
        summary=str(data.get("summary", "")),
        execution_rationale=[str(item) for item in rationale],
        build_responsibilities=[
            {
                "id": str(item.get("id", "")),
                "family": str(item.get("family", "")),
                "summary": str(item.get("summary", "")),
                "geometry_assumptions": [str(value) for value in item.get("geometry_assumptions", []) if str(value).strip()],
                "deferred_placement": [str(value) for value in item.get("deferred_placement", []) if str(value).strip()],
                "decision_refs": [str(value) for value in item.get("decision_refs", []) if str(value).strip()],
            }
            for item in build_responsibilities
            if isinstance(item, dict)
        ],
        assembly_responsibilities=[
            {
                "id": str(item.get("id", "")),
                "family": str(item.get("family", "")),
                "summary": str(item.get("summary", "")),
                "placement_relations": [str(value) for value in item.get("placement_relations", []) if str(value).strip()],
                "hierarchy_notes": [str(value) for value in item.get("hierarchy_notes", []) if str(value).strip()],
                "target_parent_family": _optional_string(item.get("target_parent_family")),
                "attachment_target_family": _optional_string(item.get("attachment_target_family")),
                "attachment_target_point_id": _optional_string(item.get("attachment_target_point_id")),
                "local_anchor_point_id": _optional_string(item.get("local_anchor_point_id")),
                "placement_rule": _optional_string(item.get("placement_rule")),
                "required_parenting": bool(item.get("required_parenting", False)),
                "decision_refs": [str(value) for value in item.get("decision_refs", []) if str(value).strip()],
            }
            for item in assembly_responsibilities
            if isinstance(item, dict)
        ],
        dependency_summary=[str(item) for item in dependency_summary if str(item).strip()],
        ordering_constraints=[
            {
                "id": str(item.get("id", "")),
                "summary": str(item.get("summary", "")),
                "depends_on": [str(value) for value in item.get("depends_on", []) if str(value).strip()],
                "responsibility": str(item.get("responsibility", "")),
                "decision_refs": [str(value) for value in item.get("decision_refs", []) if str(value).strip()],
            }
            for item in ordering_constraints
            if isinstance(item, dict)
        ],
        risk_hotspots=[
            {
                "id": str(item.get("id", "")),
                "summary": str(item.get("summary", "")),
                "owner": str(item.get("owner", "")),
                "issue_refs": [str(value) for value in item.get("issue_refs", []) if str(value).strip()],
                "reason": str(item.get("reason", "")),
            }
            for item in risk_hotspots
            if isinstance(item, dict)
        ],
        open_issues=[str(item) for item in open_issues],
    )


def _build_validation(cls: type, data: dict[str, Any]) -> Any:
    return cls(
        passed=bool(data.get("passed", False)),
        errors=list(data.get("errors", [])),
        warnings=list(data.get("warnings", [])),
        comparisons=list(data.get("comparisons", [])),
    )


def _optional_string(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _stringify_note(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("summary") or value.get("message") or value.get("detail") or json.dumps(value, ensure_ascii=False, default=str))
    return str(value)


def _canonical_optional_family_name(value: Any) -> str | None:
    text = _optional_string(value)
    if text is None:
        return None
    canonical = _canonical_part_family_name(text)
    if _is_non_deliverable_family_name(canonical):
        return None
    return canonical


def _canonical_part_family_name(name: str) -> str:
    text = str(name or "").strip()
    for suffix in ("_Body", "_body", " Body", " body"):
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].strip()
    return text


def _family_key(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _is_non_deliverable_family_name(name: str) -> bool:
    key = _family_key(name)
    if not key:
        return True
    if key.endswith(("vertex", "vertices", "edge", "edges", "face", "faces", "corner", "corners", "surface", "surfaces")):
        return True
    return key in {
        "vertex",
        "vertices",
        "edge",
        "edges",
        "face",
        "faces",
        "corner",
        "corners",
        "surface",
        "surfaces",
        "conceptualextension",
        "basicprimitive",
        "cubeprimitive",
    }


def _dedupe_named_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name", "")).strip()
        key = _family_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _compact_json_items(value: Any, *, limit: int) -> Any:
    if isinstance(value, list):
        return [_compact_json_items(item, limit=limit) for item in value[:limit]]
    if isinstance(value, dict):
        return {str(key): _compact_json_items(item, limit=limit) for key, item in value.items()}
    if isinstance(value, str):
        return _truncate_text(value, 700)
    return value


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _try_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_bbox(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    width = _try_float(value.get("width"))
    depth = _try_float(value.get("depth"))
    height = _try_float(value.get("height"))
    if width is None or depth is None or height is None:
        return {}
    return {"width": width, "depth": depth, "height": height}


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_symmetry_group(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"NONE", "LEFT_RIGHT_X", "LEFT_RIGHT_Y", "QUADRANT_Z", "RADIAL_4_Z"}:
        return text
    if "LEFT_RIGHT_X" in text or ("X" in text and ("MIRROR" in text or "LEFT" in text or "RIGHT" in text)):
        return "LEFT_RIGHT_X"
    if "LEFT_RIGHT_Y" in text or ("Y" in text and ("MIRROR" in text or "LEFT" in text or "RIGHT" in text)):
        return "LEFT_RIGHT_Y"
    if "QUADRANT" in text:
        return "QUADRANT_Z"
    if "RADIAL" in text or "ROTATION" in text:
        return "RADIAL_4_Z"
    return "NONE"


def _normalize_primitive(value: Any) -> str:
    text = str(value or "").strip().lower()
    if "sphere" in text:
        return "uv_sphere"
    if "cylinder" in text:
        return "cylinder"
    if "plane" in text:
        return "plane"
    return "cube"
