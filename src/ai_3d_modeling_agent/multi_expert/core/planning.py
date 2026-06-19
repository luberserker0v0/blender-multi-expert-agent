"""Normalize PlanArtifact into build/assembly execution views."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from ai_3d_modeling_agent.multi_expert.artifacts import PlanArtifact, SpecArtifact


@dataclass
class PlanningDiagnostic:
    """A deterministic planning warning or violation."""

    code: str
    summary: str
    severity: str = "warning"
    family: str = ""
    responsibility_ref: str = ""
    constraint_ref: str = ""
    used_step_fallback: bool = False


@dataclass
class BuildExecutionItem:
    """Normalized build work derived from planning truth."""

    family: str
    step_index: int
    instance_count: int
    primitive_type: str
    scale: list[float]
    responsibility_refs: list[str] = field(default_factory=list)
    planning_warnings: list[str] = field(default_factory=list)
    deferred_placement: list[str] = field(default_factory=list)
    used_step_fallback: bool = False


@dataclass
class BuildExecutionPlan:
    """Execution-ready build plan."""

    items: list[BuildExecutionItem] = field(default_factory=list)
    diagnostics: list[PlanningDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [asdict(item) for item in self.items],
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


@dataclass
class AssemblyExecutionItem:
    """Normalized assembly work derived from planning truth."""

    family: str
    step_index: int
    parent_name: str | None
    world_position: list[float]
    world_rotation: list[float]
    instance_world_positions: list[list[float]] = field(default_factory=list)
    placement_rule: str | None = None
    target_parent_family: str | None = None
    attachment_target_family: str | None = None
    attachment_target_point_id: str | None = None
    local_anchor_point_id: str | None = None
    required_parenting: bool = False
    resolved_attachment_target_point: list[float] | None = None
    resolved_local_anchor_point: list[float] | None = None
    resolved_world_position: list[float] | None = None
    resolved_parent: str | None = None
    missing_contract_fields: list[str] = field(default_factory=list)
    resolved_from_clarification: bool = False
    unresolved_planning_gap: bool = False
    skipped: bool = False
    responsibility_refs: list[str] = field(default_factory=list)
    constraint_refs: list[str] = field(default_factory=list)
    planning_warnings: list[str] = field(default_factory=list)
    placement_relations: list[str] = field(default_factory=list)
    hierarchy_notes: list[str] = field(default_factory=list)
    used_step_fallback: bool = False


@dataclass
class AssemblyExecutionPlan:
    """Execution-ready assembly plan."""

    items: list[AssemblyExecutionItem] = field(default_factory=list)
    diagnostics: list[PlanningDiagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [asdict(item) for item in self.items],
            "diagnostics": [asdict(item) for item in self.diagnostics],
        }


def validate_plan_structure(
    plan_artifact: PlanArtifact,
    spec_artifact: SpecArtifact | None = None,
) -> list[dict[str, Any]]:
    allowed_families = _allowed_families(spec_artifact)
    step_families = [str(step.get("family", "")).strip() for step in plan_artifact.steps if str(step.get("family", "")).strip()]
    build_families = [str(item.get("family", "")).strip() for item in plan_artifact.build_responsibilities if isinstance(item, dict) and str(item.get("family", "")).strip()]
    assembly_families = [str(item.get("family", "")).strip() for item in plan_artifact.assembly_responsibilities if isinstance(item, dict) and str(item.get("family", "")).strip()]
    issues: list[dict[str, Any]] = []

    for family in [*step_families, *build_families, *assembly_families]:
        if _is_helper_family_name(family):
            issues.append(
                {
                    "code": "helper_family_forbidden",
                    "family": family,
                    "blocking": True,
                    "summary": f"Family '{family}' looks like an internal attachment/helper family and cannot appear as a deliverable geometric family.",
                }
            )
        if allowed_families and family not in allowed_families:
            issues.append(
                {
                    "code": "invalid_family_reference",
                    "family": family,
                    "blocking": True,
                    "summary": f"Family '{family}' is not part of the validated design/spec family set.",
                }
            )

    mixed_identity = _mixed_family_identity(step_families + build_families + assembly_families)
    for base_name, variants in mixed_identity.items():
        issues.append(
            {
                "code": "mixed_family_identity",
                "family": base_name,
                "blocking": True,
                "summary": f"Plan mixes generic family '{base_name}' with instance-style variants {sorted(variants)}.",
            }
        )

    for responsibility in plan_artifact.assembly_responsibilities:
        if not isinstance(responsibility, dict):
            continue
        family = str(responsibility.get("family", "")).strip()
        attachment_target_family = _optional_str(responsibility.get("attachment_target_family"))
        target_parent_family = _optional_str(responsibility.get("target_parent_family"))
        placement_rule = _optional_str(responsibility.get("placement_rule"))
        if attachment_target_family and allowed_families and attachment_target_family not in allowed_families:
            issues.append(
                {
                    "code": "invalid_family_reference",
                    "family": family or attachment_target_family,
                    "blocking": True,
                    "summary": f"Assembly contract for '{family}' references invalid attachment target family '{attachment_target_family}'.",
                }
            )
        if target_parent_family and allowed_families and target_parent_family not in allowed_families:
            issues.append(
                {
                    "code": "invalid_family_reference",
                    "family": family or target_parent_family,
                    "blocking": True,
                    "summary": f"Assembly contract for '{family}' references invalid parent family '{target_parent_family}'.",
                }
            )
        if placement_rule == "align_local_anchor_to_target_point" and attachment_target_family and family and attachment_target_family == family:
            issues.append(
                {
                    "code": "invalid_self_alignment_contract",
                    "family": family,
                    "blocking": True,
                    "summary": f"Assembly contract for '{family}' aligns the family to its own attachment target, which is treated as invalid in the generic pipeline.",
                }
            )

    return _dedupe_issue_dicts(issues)


def normalize_build_execution_plan(
    plan_artifact: PlanArtifact,
    spec_artifact: SpecArtifact,
) -> BuildExecutionPlan:
    structural_issues = validate_plan_structure(plan_artifact, spec_artifact)
    blocking_by_family = _blocking_issues_by_family(structural_issues)
    if blocking_by_family:
        diagnostics = [
            PlanningDiagnostic(
                code=str(issue.get("code", "planning_violation")),
                summary=str(issue.get("summary", "Planning violation.")),
                severity="error",
                family=str(issue.get("family", "")).strip(),
            )
            for issue in structural_issues
        ]
        return BuildExecutionPlan(items=[], diagnostics=diagnostics)

    steps_by_family = _steps_by_family(plan_artifact.steps)
    spec_parts = spec_artifact.parts if isinstance(spec_artifact.parts, dict) else {}
    items: list[BuildExecutionItem] = []
    diagnostics: list[PlanningDiagnostic] = []
    covered_families: set[str] = set()

    for index, responsibility in enumerate(plan_artifact.build_responsibilities):
        family = str(responsibility.get("family", "")).strip()
        if not family:
            continue
        covered_families.add(family)
        step = steps_by_family.get(family, {})
        spec_entry = spec_parts.get(family, {})
        if not isinstance(spec_entry, dict):
            spec_entry = {}
        bbox = spec_entry.get("target_bbox", {}) or {}
        primitive_type = str(spec_entry.get("primitive", "cube"))
        item_warnings: list[str] = []
        item_diagnostics = _build_capability_diagnostics(family, responsibility)
        diagnostics.extend(item_diagnostics)
        item_warnings.extend(item.summary for item in item_diagnostics)
        used_step_fallback = bool(step)
        items.append(
            BuildExecutionItem(
                family=family,
                step_index=int(step.get("step_index", index)),
                instance_count=int(step.get("instance_count", 1)),
                primitive_type=primitive_type,
                scale=[
                    float(bbox.get("width", 1.0)),
                    float(bbox.get("depth", 1.0)),
                    float(bbox.get("height", 1.0)),
                ],
                responsibility_refs=[str(ref) for ref in responsibility.get("decision_refs", [])],
                planning_warnings=item_warnings,
                deferred_placement=[str(item) for item in responsibility.get("deferred_placement", [])],
                used_step_fallback=used_step_fallback,
            )
        )

    for family, step in steps_by_family.items():
        if family in covered_families:
            continue
        spec_entry = spec_parts.get(family, {})
        if not isinstance(spec_entry, dict):
            spec_entry = {}
        bbox = spec_entry.get("target_bbox", {}) or {}
        diagnostics.append(
            PlanningDiagnostic(
                code="build-step-fallback",
                summary=f"Build for {family} fell back to legacy plan steps because no build responsibility was provided.",
                family=family,
                used_step_fallback=True,
            )
        )
        items.append(
            BuildExecutionItem(
                family=family,
                step_index=int(step.get("step_index", len(items))),
                instance_count=int(step.get("instance_count", 1)),
                primitive_type=str(spec_entry.get("primitive", "cube")),
                scale=[
                    float(bbox.get("width", 1.0)),
                    float(bbox.get("depth", 1.0)),
                    float(bbox.get("height", 1.0)),
                ],
                planning_warnings=[diagnostics[-1].summary],
                used_step_fallback=True,
            )
        )

    items.sort(key=lambda item: item.step_index)
    return BuildExecutionPlan(items=items, diagnostics=diagnostics)


def normalize_assembly_execution_plan(plan_artifact: PlanArtifact, spec_artifact: SpecArtifact | None = None) -> AssemblyExecutionPlan:
    structural_issues = validate_plan_structure(plan_artifact, spec_artifact)
    blocking_by_family = _blocking_issues_by_family(structural_issues)
    if blocking_by_family:
        diagnostics = [
            PlanningDiagnostic(
                code=str(issue.get("code", "planning_violation")),
                summary=str(issue.get("summary", "Planning violation.")),
                severity="error",
                family=str(issue.get("family", "")).strip(),
            )
            for issue in structural_issues
        ]
        return AssemblyExecutionPlan(items=[], diagnostics=diagnostics)

    steps_by_family = _steps_by_family(plan_artifact.steps)
    spec_parts = spec_artifact.parts if isinstance(spec_artifact, SpecArtifact) and isinstance(spec_artifact.parts, dict) else {}
    point_registry = _spec_point_registry(spec_artifact)
    items: list[AssemblyExecutionItem] = []
    diagnostics: list[PlanningDiagnostic] = []
    covered_families: set[str] = set()

    for index, responsibility in enumerate(plan_artifact.assembly_responsibilities):
        family = str(responsibility.get("family", "")).strip()
        if not family:
            continue
        covered_families.add(family)
        step = steps_by_family.get(family, {})
        item_diagnostics = _assembly_capability_diagnostics(family, responsibility)
        contract = _extract_assembly_contract(family, responsibility, spec_parts, point_registry, plan_artifact)
        item_diagnostics.extend(_assembly_contract_diagnostics(family, responsibility, contract))
        diagnostics.extend(item_diagnostics)
        planning_warnings = [item.summary for item in item_diagnostics]
        items.append(
            AssemblyExecutionItem(
                family=family,
                step_index=int(step.get("step_index", index)),
                parent_name=contract["resolved_parent"] or _optional_str(step.get("parent")),
                world_position=contract["resolved_world_position"] or _float_vector(step.get("world_position", [0.0, 0.0, 0.0])),
                world_rotation=_float_vector(step.get("world_rotation", [0.0, 0.0, 0.0])),
                placement_rule=contract["placement_rule"],
                target_parent_family=contract["target_parent_family"],
                attachment_target_family=contract["attachment_target_family"],
                attachment_target_point_id=contract["attachment_target_point_id"],
                local_anchor_point_id=contract["local_anchor_point_id"],
                required_parenting=contract["required_parenting"],
                resolved_attachment_target_point=contract["resolved_attachment_target_point"],
                resolved_local_anchor_point=contract["resolved_local_anchor_point"],
                resolved_world_position=contract["resolved_world_position"],
                resolved_parent=contract["resolved_parent"],
                missing_contract_fields=contract["missing_contract_fields"],
                resolved_from_clarification=contract["resolved_from_clarification"],
                unresolved_planning_gap=contract["unresolved_planning_gap"],
                skipped=contract["unresolved_planning_gap"],
                responsibility_refs=[str(ref) for ref in responsibility.get("decision_refs", [])],
                constraint_refs=_constraint_refs_for_step(plan_artifact.ordering_constraints, step),
                planning_warnings=planning_warnings,
                placement_relations=[str(item) for item in responsibility.get("placement_relations", [])],
                hierarchy_notes=[str(item) for item in responsibility.get("hierarchy_notes", [])],
                used_step_fallback=bool(step) and not contract["resolved_world_position"],
            )
        )

    for family, step in steps_by_family.items():
        if family in covered_families:
            continue
        diagnostics.append(
            PlanningDiagnostic(
                code="assembly-step-fallback",
                summary=f"Assembly for {family} fell back to legacy plan steps because no assembly responsibility was provided.",
                family=family,
                used_step_fallback=True,
            )
        )
        items.append(
            AssemblyExecutionItem(
                family=family,
                step_index=int(step.get("step_index", len(items))),
                parent_name=_optional_str(step.get("parent")),
                world_position=_float_vector(step.get("world_position", [0.0, 0.0, 0.0])),
                world_rotation=_float_vector(step.get("world_rotation", [0.0, 0.0, 0.0])),
                placement_rule="place_at_world_position",
                resolved_world_position=_float_vector(step.get("world_position", [0.0, 0.0, 0.0])),
                resolved_parent=_optional_str(step.get("parent")),
                constraint_refs=_constraint_refs_for_step(plan_artifact.ordering_constraints, step),
                planning_warnings=[diagnostics[-1].summary],
                used_step_fallback=True,
            )
        )

    _apply_common_instance_layouts(items, spec_parts)
    items.sort(key=lambda item: item.step_index)
    return AssemblyExecutionPlan(items=items, diagnostics=diagnostics)


def _steps_by_family(steps: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for step in steps:
        family = str(step.get("family", "")).strip()
        if family and family not in result:
            result[family] = step
    return result


def _constraint_refs_for_step(ordering_constraints: list[dict[str, Any]], step: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    family = str(step.get("family", "")).strip()
    parent_name = str(step.get("parent", "")).strip()
    for constraint in ordering_constraints:
        depends_on = [str(item) for item in constraint.get("depends_on", [])]
        dependency_families = {
            token.split(":", 1)[1].strip()
            for token in depends_on
            if ":" in token
        }
        if family in dependency_families or (parent_name and parent_name in dependency_families):
            refs.extend(str(ref) for ref in constraint.get("decision_refs", []))
    return refs


def _build_capability_diagnostics(family: str, responsibility: dict[str, Any]) -> list[PlanningDiagnostic]:
    diagnostics: list[PlanningDiagnostic] = []
    if responsibility.get("placement_relations") or responsibility.get("hierarchy_notes"):
        diagnostics.append(
            PlanningDiagnostic(
                code="builder-placement-violation",
                summary=f"Build responsibility for {family} includes final placement or hierarchy work that belongs to the Assembler.",
                family=family,
                responsibility_ref=_first_ref(responsibility),
                severity="warning",
            )
        )
    return diagnostics


def _assembly_capability_diagnostics(family: str, responsibility: dict[str, Any]) -> list[PlanningDiagnostic]:
    diagnostics: list[PlanningDiagnostic] = []
    if responsibility.get("geometry_assumptions") or responsibility.get("deferred_placement"):
        diagnostics.append(
            PlanningDiagnostic(
                code="assembler-geometry-violation",
                summary=f"Assembly responsibility for {family} includes geometry-definition work that belongs to the Builder or Spec phase.",
                family=family,
                responsibility_ref=_first_ref(responsibility),
                severity="warning",
            )
        )
    return diagnostics


def validate_assembly_contract(
    plan_artifact: PlanArtifact,
    spec_artifact: SpecArtifact | None = None,
) -> list[dict[str, Any]]:
    spec_parts = spec_artifact.parts if isinstance(spec_artifact, SpecArtifact) and isinstance(spec_artifact.parts, dict) else {}
    point_registry = _spec_point_registry(spec_artifact)
    issues: list[dict[str, Any]] = []
    for responsibility in plan_artifact.assembly_responsibilities:
        if not isinstance(responsibility, dict):
            continue
        family = str(responsibility.get("family", "")).strip()
        if not family:
            continue
        contract = _extract_assembly_contract(family, responsibility, spec_parts, point_registry, plan_artifact)
        if not contract["missing_contract_fields"]:
            continue
        issues.append(
            {
                "code": "assembly-contract-gap",
                "family": family,
                "missing_contract_fields": list(contract["missing_contract_fields"]),
                "blocking": True,
                "placement_rule": contract["placement_rule"],
                "summary": f"Assembly contract for {family} is missing blocking fields: {', '.join(contract['missing_contract_fields'])}.",
            }
        )
    return issues


def _extract_assembly_contract(
    family: str,
    responsibility: dict[str, Any],
    spec_parts: dict[str, Any],
    point_registry: dict[str, list[dict[str, Any]]],
    plan_artifact: PlanArtifact,
) -> dict[str, Any]:
    step = _steps_by_family(plan_artifact.steps).get(family, {})
    step_parent = _optional_str(step.get("parent"))
    placement_rule = _optional_str(responsibility.get("placement_rule"))
    target_parent_family = _optional_str(responsibility.get("target_parent_family"))
    attachment_target_family = _optional_str(responsibility.get("attachment_target_family"))
    attachment_target_point_id = _optional_str(responsibility.get("attachment_target_point_id"))
    local_anchor_point_id = _optional_str(responsibility.get("local_anchor_point_id"))
    required_parenting = bool(responsibility.get("required_parenting", False))
    clarification_source = bool(
        responsibility.get("clarification_scope")
        or responsibility.get("resolved_from_clarification")
        or responsibility.get("clarified", False)
    )

    if not placement_rule:
        placement_rule = (
            "align_local_anchor_to_target_point"
            if attachment_target_family or target_parent_family or step_parent or responsibility.get("placement_relations") or responsibility.get("hierarchy_notes")
            else "place_at_world_position"
        )
    if not target_parent_family and step_parent:
        target_parent_family = step_parent
    if not attachment_target_family and step_parent:
        attachment_target_family = step_parent
    if not responsibility.get("required_parenting", None) and step_parent:
        required_parenting = True
    if required_parenting and not target_parent_family and attachment_target_family:
        target_parent_family = attachment_target_family

    missing_contract_fields: list[str] = []
    if placement_rule == "align_local_anchor_to_target_point":
        if not attachment_target_family:
            missing_contract_fields.append("attachment_target_family")
        if not attachment_target_point_id:
            missing_contract_fields.append("attachment_target_point_id")
        if not local_anchor_point_id:
            missing_contract_fields.append("local_anchor_point_id")
    if "required_parenting" not in responsibility and placement_rule == "align_local_anchor_to_target_point":
        missing_contract_fields.append("required_parenting")
    if required_parenting and not target_parent_family:
        missing_contract_fields.append("target_parent_family")

    resolved_attachment_target_point = _resolve_attachment_point(point_registry, spec_parts, attachment_target_family, attachment_target_point_id)
    resolved_local_anchor_point = _resolve_attachment_point(point_registry, spec_parts, family, local_anchor_point_id)
    if placement_rule == "align_local_anchor_to_target_point":
        if resolved_attachment_target_point is None:
            missing_contract_fields.append("resolved_attachment_target_point")
        if resolved_local_anchor_point is None:
            missing_contract_fields.append("resolved_local_anchor_point")

    parent_family = attachment_target_family or target_parent_family or ""
    parent_step = _steps_by_family(plan_artifact.steps).get(parent_family, {})
    parent_world_position = _float_vector(
        plan_artifact.world_positions.get(
            parent_family,
            parent_step.get("world_position", [0.0, 0.0, 0.0]),
        )
    )
    resolved_world_position: list[float] | None = None
    if placement_rule == "align_local_anchor_to_target_point" and resolved_attachment_target_point is not None and resolved_local_anchor_point is not None:
        target_world = [parent_world_position[i] + resolved_attachment_target_point[i] for i in range(3)]
        resolved_world_position = [round(target_world[i] - resolved_local_anchor_point[i], 4) for i in range(3)]
    elif placement_rule == "place_at_world_position":
        resolved_world_position = _float_vector(step.get("world_position", plan_artifact.world_positions.get(family, [0.0, 0.0, 0.0])))

    return {
        "placement_rule": placement_rule,
        "target_parent_family": target_parent_family,
        "attachment_target_family": attachment_target_family,
        "attachment_target_point_id": attachment_target_point_id,
        "local_anchor_point_id": local_anchor_point_id,
        "required_parenting": required_parenting,
        "resolved_attachment_target_point": resolved_attachment_target_point,
        "resolved_local_anchor_point": resolved_local_anchor_point,
        "resolved_world_position": resolved_world_position,
        "resolved_parent": target_parent_family if required_parenting else None,
        "missing_contract_fields": _dedupe_strings(missing_contract_fields),
        "resolved_from_clarification": clarification_source,
        "unresolved_planning_gap": bool(missing_contract_fields),
    }


def _resolve_attachment_point(
    point_registry: dict[str, list[dict[str, Any]]],
    spec_parts: dict[str, Any],
    family: str | None,
    point_id: str | None,
) -> list[float] | None:
    if not family or not point_id:
        return None
    normalized_id = _normalize_point_token(point_id)
    for item in point_registry.get(family, []):
        if not isinstance(item, dict):
            continue
        candidate_ids = {
            _normalize_point_token(item.get("id")),
            _normalize_point_token(item.get("name")),
        }
        aliases = item.get("aliases", [])
        if isinstance(aliases, list):
            candidate_ids.update(_normalize_point_token(alias) for alias in aliases)
        if normalized_id not in candidate_ids:
            continue
        return _float_vector(item.get("local_position", [0.0, 0.0, 0.0]))
    entry = spec_parts.get(family, {})
    if isinstance(entry, dict):
        for item in entry.get("attachment_points", []) if isinstance(entry.get("attachment_points", []), list) else []:
            if not isinstance(item, dict):
                continue
            candidate_ids = {
                _normalize_point_token(item.get("id")),
                _normalize_point_token(item.get("name")),
            }
            if normalized_id in candidate_ids:
                return _float_vector(item.get("local_offset", [0.0, 0.0, 0.0]))
    return None


def _apply_common_instance_layouts(items: list[AssemblyExecutionItem], spec_parts: dict[str, Any]) -> None:
    """Fill deterministic per-instance placements for common object layouts.

    The meeting can describe a chair naturally while Python owns the executable
    placement contract. This prevents a whole family with multiple instances
    from silently sharing a single world position.
    """
    by_family = {item.family.lower(): item for item in items}
    if {"seat", "leg", "backrest"} <= set(by_family):
        _apply_simple_chair_layout(by_family, spec_parts)


def _apply_simple_chair_layout(by_family: dict[str, AssemblyExecutionItem], spec_parts: dict[str, Any]) -> None:
    seat_dims = _bbox_dimensions(spec_parts, "seat", [0.45, 0.45, 0.08])
    leg_dims = _bbox_dimensions(spec_parts, "leg", [0.05, 0.05, 0.75])
    backrest_dims = _bbox_dimensions(spec_parts, "backrest", [0.45, 0.08, 0.55])

    seat = by_family["seat"]
    seat.world_position = [0.0, 0.0, 0.0]
    seat.resolved_world_position = [0.0, 0.0, 0.0]
    seat.instance_world_positions = [[0.0, 0.0, 0.0]]

    leg_x = round((seat_dims[0] / 2.0) - (leg_dims[0] / 2.0), 4)
    leg_y = round((seat_dims[1] / 2.0) - (leg_dims[1] / 2.0), 4)
    leg_z = round(-((seat_dims[2] / 2.0) + (leg_dims[2] / 2.0)), 4)
    leg_positions = [
        [leg_x, leg_y, leg_z],
        [-leg_x, leg_y, leg_z],
        [-leg_x, -leg_y, leg_z],
        [leg_x, -leg_y, leg_z],
    ]
    leg = by_family["leg"]
    leg.world_position = list(leg_positions[0])
    leg.resolved_world_position = list(leg_positions[0])
    leg.instance_world_positions = leg_positions

    backrest_y = round((seat_dims[1] / 2.0) + (backrest_dims[1] / 2.0), 4)
    backrest_z = round((seat_dims[2] / 2.0) + (backrest_dims[2] / 2.0), 4)
    backrest_pos = [0.0, backrest_y, backrest_z]
    backrest = by_family["backrest"]
    backrest.world_position = list(backrest_pos)
    backrest.resolved_world_position = list(backrest_pos)
    backrest.instance_world_positions = [backrest_pos]


def _bbox_dimensions(spec_parts: dict[str, Any], family: str, default: list[float]) -> list[float]:
    entry = spec_parts.get(family, {})
    bbox = entry.get("target_bbox", {}) if isinstance(entry, dict) else {}
    if not isinstance(bbox, dict):
        return list(default)
    return [
        float(bbox.get("width", default[0])),
        float(bbox.get("depth", default[1])),
        float(bbox.get("height", default[2])),
    ]


def _spec_point_registry(spec_artifact: SpecArtifact | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(spec_artifact, SpecArtifact):
        return {}
    if isinstance(spec_artifact.point_registry, dict) and spec_artifact.point_registry:
        return spec_artifact.point_registry
    registry: dict[str, list[dict[str, Any]]] = {}
    spec_parts = spec_artifact.parts if isinstance(spec_artifact.parts, dict) else {}
    for family, entry in spec_parts.items():
        if not isinstance(entry, dict):
            continue
        points: list[dict[str, Any]] = []
        raw_points = entry.get("attachment_points", [])
        if not isinstance(raw_points, list):
            raw_points = []
        for item in raw_points:
            if not isinstance(item, dict):
                continue
            point_name = str(item.get("name") or item.get("id") or "").strip()
            point_id = str(item.get("id") or point_name).strip()
            if not point_id:
                continue
            points.append(
                {
                    "id": point_id,
                    "name": point_name,
                    "local_position": list(item.get("local_offset", [0.0, 0.0, 0.0])),
                    "description": str(item.get("description", "")),
                    "aliases": [point_name] if point_name and point_name != point_id else [],
                }
            )
        registry[str(family)] = points
    return registry


def _allowed_families(spec_artifact: SpecArtifact | None) -> set[str]:
    if not isinstance(spec_artifact, SpecArtifact):
        return set()
    return {str(name).strip() for name in spec_artifact.parts.keys() if str(name).strip()} if isinstance(spec_artifact.parts, dict) else set()


def _is_helper_family_name(family: str) -> bool:
    token = _normalize_point_token(family)
    if not token:
        return False
    helper_markers = ("attachment", "anchor", "locator", "helper", "socket", "pivot", "marker", "point")
    return any(marker in token for marker in helper_markers)


def _base_family_name(family: str) -> str:
    family = family.strip()
    match = re.match(r"^(.*?)(?:[_-]?(\d+))$", family)
    if not match:
        return family
    base_name = str(match.group(1) or "").strip("_- ")
    return base_name or family


def _mixed_family_identity(families: list[str]) -> dict[str, set[str]]:
    variants_by_base: dict[str, set[str]] = {}
    raw_families = {family.strip() for family in families if family.strip()}
    for family in raw_families:
        base_name = _base_family_name(family)
        if not base_name:
            continue
        variants_by_base.setdefault(base_name, set()).add(family)
    mixed: dict[str, set[str]] = {}
    for base_name, variants in variants_by_base.items():
        numbered_variants = {variant for variant in variants if variant != base_name}
        if base_name in variants and numbered_variants:
            mixed[base_name] = variants
    return mixed


def _dedupe_issue_dicts(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for issue in issues:
        code = str(issue.get("code", "")).strip()
        family = str(issue.get("family", "")).strip()
        summary = str(issue.get("summary", "")).strip()
        key = (code, family, summary)
        if not code or not summary or key in seen:
            continue
        seen.add(key)
        result.append(issue)
    return result


def _blocking_issues_by_family(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        if not bool(issue.get("blocking", False)):
            continue
        family = str(issue.get("family", "")).strip()
        grouped.setdefault(family, []).append(issue)
    return grouped


def _normalize_point_token(value: Any) -> str:
    text = str(value).strip().lower() if value is not None else ""
    return re.sub(r"[^a-z0-9]+", "", text)


def _assembly_contract_diagnostics(
    family: str,
    responsibility: dict[str, Any],
    contract: dict[str, Any],
) -> list[PlanningDiagnostic]:
    diagnostics: list[PlanningDiagnostic] = []
    for field_name in contract["missing_contract_fields"]:
        diagnostics.append(
            PlanningDiagnostic(
                code="assembly-contract-gap",
                summary=f"Assembly contract for {family} is missing blocking field '{field_name}'.",
                family=family,
                responsibility_ref=_first_ref(responsibility),
                severity="error",
            )
        )
    return diagnostics


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _first_ref(payload: dict[str, Any]) -> str:
    refs = payload.get("decision_refs", [])
    if isinstance(refs, list) and refs:
        return str(refs[0])
    return ""


def _float_vector(value: Any) -> list[float]:
    if not isinstance(value, list):
        return [0.0, 0.0, 0.0]
    return [float(item) for item in value[:3]] + [0.0] * max(0, 3 - len(value))


def _optional_str(value: Any) -> str | None:
    raw = str(value).strip() if value is not None else ""
    return raw or None
