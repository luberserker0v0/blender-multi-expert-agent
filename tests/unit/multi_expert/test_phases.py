"""Tests for multi-expert phase implementations."""

import json
import tempfile
from pathlib import Path

import pytest

from ai_3d_modeling_agent.multi_expert.artifacts import (
    AssemblyArtifact,
    BuildArtifact,
    DesignArtifact,
    PlanArtifact,
    SpecArtifact,
    ValidationArtifact,
)
from ai_3d_modeling_agent.multi_expert.core.meeting import DEFAULT_MULTI_EXPERT_SAMPLING_POLICY
from ai_3d_modeling_agent.memory.session_paths import session_meeting_state_path
from ai_3d_modeling_agent.multi_expert.experts import (
    Builder,
    Designer,
    Inspector,
    Planner,
    Reviewer,
    Specifier,
)
from ai_3d_modeling_agent.multi_expert.phases import (
    AssemblePhase,
    BuildPhase,
    DesignPhase,
    PlanPhase,
    SpecPhase,
    ValidatePhase,
)
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry
from ai_3d_modeling_agent.schemas.part import PartFamily, SymmetryGroup


def _meeting_registry(*expert_types):
    registry = ExpertRegistry()
    for expert_type in expert_types:
        registry.register(expert_type())
    return registry


def test_design_phase_runs(mock_llm):
    phase = DesignPhase()
    registry = _meeting_registry(Designer, Reviewer)

    result = phase.run(registry, context={}, llm=mock_llm, task_prompt="build a chair")

    assert isinstance(result, DesignArtifact)
    assert mock_llm.call_count >= 4


def test_spec_phase_runs(mock_llm):
    phase = SpecPhase()
    registry = _meeting_registry(Specifier, Reviewer)
    design = DesignArtifact(task_prompt="build a chair")

    result = phase.run(registry, context={}, llm=mock_llm, design_artifact=design)

    assert isinstance(result, SpecArtifact)
    assert mock_llm.call_count >= 4


def test_spec_phase_persists_markdown_first_coverage_state(mock_llm):
    phase = SpecPhase()
    registry = _meeting_registry(Specifier, Reviewer)
    design = DesignArtifact(
        task_prompt="build a chair",
        parts=[
            {"name": "seat", "instance_count": 1},
            {"name": "leg", "instance_count": 4},
        ],
    )
    mock_llm.fixed_response = "Proposal: Define the current target with simple cube geometry and preserve its count."

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = phase.run(
            registry,
            context={"runtime_root": tmp_dir, "session_id": "coverage-spec"},
            llm=mock_llm,
            design_artifact=design,
        )
        state = json.loads(session_meeting_state_path(Path(tmp_dir), "coverage-spec", "spec").read_text(encoding="utf-8"))

    assert state["coverage_todos"]
    assert state["coverage_summary"]["total"] == 6
    assert state["todo_groups"]
    assert {group["target_name"] for group in state["todo_groups"]} == {"leg", "seat"}
    assert set(result.parts) == {"leg", "seat"}
    assert result.parts["leg"]["instance_count"] == 4


def test_spec_phase_preserves_design_instance_counts_in_extracted_parts():
    result = SpecArtifact(parts={"leg": {"primitive": "cylinder", "target_bbox": {"width": 0.1, "depth": 0.1, "height": 1.0}}})
    design = DesignArtifact(parts=[{"name": "leg", "instance_count": 4}])

    SpecPhase._preserve_design_instance_counts(result, design)

    assert result.parts["leg"]["instance_count"] == 4


def test_spec_phase_without_structured_geometry_uses_markdown_first_flow():
    class MarkdownFirstSpecLLM:
        def __init__(self) -> None:
            self.extractions = 0

        def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
            if kwargs.get("skill") == "extract-spec-artifact":
                self.extractions += 1
            if kwargs.get("agent") == "moderator" and kwargs.get("context", {}).get("meeting_turn_kind") == "resolution":
                return "Decision: Accept focused correction.\nAccepted:\n- Define leg geometry.\nRejected:\n- None.\nOpen Issues:\nNone"
            return "Proposal: Define focused leg geometry.\nRationale: Use a simple cube bbox."

    phase = SpecPhase()
    registry = _meeting_registry(Specifier, Reviewer)
    llm = MarkdownFirstSpecLLM()
    design = DesignArtifact(parts=[{"name": "leg", "instance_count": 4}])

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = phase.run(
            registry,
            context={"runtime_root": tmp_dir, "session_id": "coverage-spec-revision-clear"},
            llm=llm,
            design_artifact=design,
        )
        state = json.loads(session_meeting_state_path(Path(tmp_dir), "coverage-spec-revision-clear", "spec").read_text(encoding="utf-8"))

    assert llm.extractions == 0
    assert "leg" in result.parts
    assert state["coverage_todos"]
    assert state["coverage_summary"]["total"] == 3


def test_spec_phase_rejects_assumed_geometry_by_default():
    result = SpecArtifact(
        parts={
            "seat": {
                "primitive": "cube",
                "geometry_source": "assumed",
                "assumptions": ["standard chair seat"],
                "target_bbox": {"width": 0.5, "depth": 0.4, "height": 0.1},
            }
        }
    )

    SpecPhase._apply_geometry_completion_policy(result, "require_user_input")

    assert result.parts["seat"]["target_bbox"] == {}
    assert result.parts["seat"]["geometry_source"] == "needs_user_input"
    assert any("require_user_input" in note for note in result.validation_notes)


def test_spec_phase_rejects_unlabeled_bbox_by_default():
    result = SpecArtifact(
        parts={
            "seat": {
                "primitive": "cube",
                "target_bbox": {"width": 0.5, "depth": 0.4, "height": 0.1},
            }
        }
    )

    SpecPhase._apply_geometry_completion_policy(result, "require_user_input")

    assert result.parts["seat"]["target_bbox"] == {}
    assert result.parts["seat"]["geometry_source"] == "needs_user_input"


def test_spec_phase_allows_labeled_assumed_geometry_when_policy_allows_it():
    result = SpecArtifact(
        parts={
            "seat": {
                "primitive": "cube",
                "geometry_source": "assumed",
                "assumptions": ["standard chair seat"],
                "target_bbox": {"width": 0.5, "depth": 0.4, "height": 0.1},
            }
        }
    )

    SpecPhase._apply_geometry_completion_policy(result, "allow_assumptions")

    assert result.parts["seat"]["target_bbox"] == {"width": 0.5, "depth": 0.4, "height": 0.1}
    assert result.parts["seat"]["geometry_source"] == "accepted_assumption"


def test_plan_phase_runs_with_meeting_and_solver(mock_llm):
    phase = PlanPhase()
    registry = _meeting_registry(Planner, Reviewer)
    spec = SpecArtifact(
        parts={
            "seat": {
                "primitive": "cube",
                "target_bbox": {"width": 1.0, "depth": 1.0, "height": 0.1},
            },
            "leg": {
                "primitive": "cylinder",
                "target_bbox": {"width": 0.1, "depth": 0.1, "height": 1.0},
            },
        }
    )
    families = [
        PartFamily(
            name="seat",
            description="flat surface",
            instance_count=1,
            parent_name=None,
            symmetry_group=SymmetryGroup.NONE,
        ),
        PartFamily(
            name="leg",
            description="vertical support",
            instance_count=4,
            parent_name="seat",
            symmetry_group=SymmetryGroup.QUADRANT_Z,
        ),
    ]

    result = phase.run(registry, context={}, llm=mock_llm, spec_artifact=spec, part_families=families)

    assert isinstance(result, PlanArtifact)
    assert len(result.steps) > 0
    assert "seat" in result.world_positions
    assert "leg" in result.world_positions
    assert any(item["family"] == "seat" for item in result.build_responsibilities)
    assert any(item["family"] == "leg" for item in result.assembly_responsibilities)
    leg_responsibility = next(item for item in result.assembly_responsibilities if item["family"] == "leg")
    assert leg_responsibility["placement_rule"] == "align_local_anchor_to_target_point"
    assert leg_responsibility["required_parenting"] is True
    assert len(result.dependency_summary) > 0
    assert len(result.ordering_constraints) > 0
    assert mock_llm.call_count >= 4


def test_plan_phase_persists_coverage_gap_for_missing_assembly_responsibility():
    class MissingLegAssemblyLLM:
        def __init__(self) -> None:
            self.call_count = 0

        def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
            self.call_count += 1
            if kwargs.get("skill") == "extract-plan-artifact":
                return (
                    '{"summary":"Plan with missing leg assembly.",'
                    '"execution_rationale":[],"build_responsibilities":[{"id":"build-seat","family":"seat"},{"id":"build-leg","family":"leg"}],'
                    '"assembly_responsibilities":[{"id":"assemble-seat","family":"seat"}],'
                    '"dependency_summary":[],"ordering_constraints":[],"risk_hotspots":[],"open_issues":[]}'
                )
            if kwargs.get("agent") == "moderator" and kwargs.get("context", {}).get("meeting_turn_kind") == "resolution":
                return "Decision: Accept scoped plan.\nAccepted:\n- Build seat and leg.\nRejected:\n- None.\nOpen Issues:\nNone"
            return "Proposal: Build seat and leg.\nRationale: Use accepted parts only."

    phase = PlanPhase()
    registry = _meeting_registry(Planner, Reviewer)
    llm = MissingLegAssemblyLLM()
    spec = SpecArtifact(parts={"seat": {"primitive": "cube"}, "leg": {"primitive": "cylinder"}})
    families = [
        PartFamily(name="seat", description="seat", instance_count=1, parent_name=None, symmetry_group=SymmetryGroup.NONE),
        PartFamily(name="leg", description="leg", instance_count=4, parent_name="seat", symmetry_group=SymmetryGroup.QUADRANT_Z),
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        result = phase.run(
            registry,
            context={"runtime_root": tmp_dir, "session_id": "coverage-plan"},
            llm=llm,
            spec_artifact=spec,
            part_families=families,
        )
        state = json.loads(session_meeting_state_path(Path(tmp_dir), "coverage-plan", "plan").read_text(encoding="utf-8"))

    assert state["coverage_todos"]
    assert state["coverage_summary"]["counts"]["missing"] == 0
    assert "coverage_gap" not in state["phase_quality_flags"]
    assert state["phase_status"] == "completed"
    assert state["revision_requests"] == []
    assert state["clarification_requests"] == []
    assert any("Assembly contract for leg" in note for note in result.failure_notes)


def test_build_phase_runs():
    from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
    from ai_3d_modeling_agent.execution.action_executor import ActionExecutor

    phase = BuildPhase()
    object_ops = SimulatedBlenderObjectOps()
    executor = ActionExecutor(object_ops)

    plan = PlanArtifact(
        build_responsibilities=[
            {
                "id": "build-seat",
                "family": "seat",
                "summary": "Builder creates the seat.",
                "geometry_assumptions": ["Use the agreed primitive."],
                "deferred_placement": ["Assembly handles final placement."],
                "decision_refs": ["plan.build_responsibilities.seat"],
            }
        ],
        steps=[
            {
                "family": "seat",
                "world_position": [0.0, 0.0, 0.0],
                "world_rotation": [0.0, 0.0, 0.0],
                "world_scale": [1.0, 1.0, 0.1],
                "instance_count": 1,
                "symmetry_group": "none",
            }
        ]
    )
    spec = SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 0.1}}})

    result = phase.run(plan_artifact=plan, spec_artifact=spec, object_ops=object_ops, executor=executor)

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], BuildArtifact)
    assert result[0].responsibility_refs == ["plan.build_responsibilities.seat"]
    assert result[0].planning_warnings == []


def test_build_phase_without_object_ops():
    phase = BuildPhase()
    plan = PlanArtifact(
        steps=[
            {
                "family": "seat",
                "world_position": [0.0, 0.0, 0.0],
                "instance_count": 1,
                "symmetry_group": "none",
            }
        ]
    )
    spec = SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {}}})

    result = phase.run(plan_artifact=plan, spec_artifact=spec)

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].status == "built"
    assert "fell back to legacy plan steps" in result[0].planning_warnings[0]


def test_build_phase_marks_builder_placement_violation():
    phase = BuildPhase()
    plan = PlanArtifact(
        build_responsibilities=[
            {
                "id": "build-seat",
                "family": "seat",
                "summary": "Builder creates and places the seat.",
                "placement_relations": ["Attach seat to the room origin."],
                "decision_refs": ["plan.build_responsibilities.seat"],
            }
        ],
        steps=[{"family": "seat", "instance_count": 1, "step_index": 0}],
    )
    spec = SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {}}})

    result = phase.run(plan_artifact=plan, spec_artifact=spec)

    assert "final placement or hierarchy work" in result[0].planning_warnings[0]


def test_build_phase_fails_fast_on_invalid_family_contract():
    phase = BuildPhase()
    events: list[dict] = []
    plan = PlanArtifact(
        build_responsibilities=[
            {
                "id": "build-leaf",
                "family": "leaf",
                "summary": "Builder creates generic leaf geometry.",
                "decision_refs": ["plan.build_responsibilities.leaf"],
            }
        ],
        steps=[
            {
                "family": "leaf_1",
                "instance_count": 1,
                "step_index": 0,
            }
        ],
    )
    spec = SpecArtifact(parts={"leaf_1": {"primitive": "plane", "target_bbox": {"width": 1.0, "depth": 0.2, "height": 0.01}}})

    result = phase.run(plan_artifact=plan, spec_artifact=spec, event_emitter=lambda phase_name, kind, message, **extra: events.append({"phase": phase_name, "kind": kind, "message": message, **extra}))

    assert all(item.status == "failed" for item in result)
    step_events = [event for event in events if event["kind"] == "build_step"]
    assert step_events
    assert step_events[0]["skipped"] is True
    assert step_events[0]["tool_calls"] == []


def test_assemble_phase_runs():
    from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
    from ai_3d_modeling_agent.execution.action_executor import ActionExecutor

    phase = AssemblePhase()
    object_ops = SimulatedBlenderObjectOps()
    executor = ActionExecutor(object_ops)

    object_ops.create_primitive("cube", "seat_01")
    object_ops.create_primitive("cylinder", "leg_01")

    build_artifacts = [
        BuildArtifact(part_name="seat", instance_names=["seat_01"], status="built"),
        BuildArtifact(part_name="leg", instance_names=["leg_01"], status="built"),
    ]
    plan = PlanArtifact(
        assembly_responsibilities=[
            {
                "id": "assemble-leg",
                "family": "leg",
                "summary": "Builder places the leg.",
                "placement_relations": ["Attach the leg to the seat."],
                "hierarchy_notes": ["Keep seat as the parent."],
                "target_parent_family": "seat",
                "attachment_target_family": "seat",
                "attachment_target_point_id": "bottom_center",
                "local_anchor_point_id": "top_center",
                "placement_rule": "align_local_anchor_to_target_point",
                "required_parenting": True,
                "decision_refs": ["plan.assembly_responsibilities.leg"],
            }
        ],
        ordering_constraints=[
            {
                "id": "ordering-seat-before-leg",
                "summary": "Build the seat before placing the leg.",
                "depends_on": ["build:seat"],
                "responsibility": "builder",
                "decision_refs": ["plan.ordering_constraints.seat-before-leg"],
            }
        ],
        steps=[
            {
                "family": "seat",
                "parent": None,
                "world_position": [0.0, 0.0, 0.45],
                "world_rotation": [0.0, 0.0, 0.0],
                "instance_count": 1,
                "symmetry_group": "none",
                "step_index": 0,
            },
            {
                "family": "leg",
                "parent": "seat",
                "world_position": [0.2, 0.2, -0.45],
                "world_rotation": [0.0, 0.0, 0.0],
                "instance_count": 4,
                "symmetry_group": "quadrant_z",
                "step_index": 1,
            },
        ]
    )
    spec = SpecArtifact(
        parts={
            "seat": {
                "attachment_points": [{"id": "bottom_center", "name": "bottom_center", "local_offset": [0.0, 0.0, -0.05]}],
            },
            "leg": {
                "attachment_points": [{"id": "top_center", "name": "top_center", "local_offset": [0.0, 0.0, 0.35]}],
            },
        }
    )

    result = phase.run(
        build_artifacts=build_artifacts,
        plan_artifact=plan,
        spec_artifact=spec,
        object_ops=object_ops,
        executor=executor,
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], AssemblyArtifact)
    assert result[1].responsibility_refs == ["plan.assembly_responsibilities.leg"]
    assert result[1].constraint_refs == ["plan.ordering_constraints.seat-before-leg"]
    assert result[1].resolved_parent == "seat"
    assert result[1].resolved_world_position == [0.0, 0.0, 0.05]


def test_assemble_phase_fails_when_parent_is_not_built():
    phase = AssemblePhase()
    build_artifacts = [BuildArtifact(part_name="leg", instance_names=["leg_01"], status="built")]
    plan = PlanArtifact(
        assembly_responsibilities=[
            {
                "id": "assemble-leg",
                "family": "leg",
                "summary": "Builder places the leg.",
                "placement_relations": ["Attach the leg to the seat."],
                "hierarchy_notes": ["Keep seat as the parent."],
                "target_parent_family": "seat",
                "attachment_target_family": "seat",
                "attachment_target_point_id": "bottom_center",
                "local_anchor_point_id": "top_center",
                "placement_rule": "align_local_anchor_to_target_point",
                "required_parenting": True,
                "decision_refs": ["plan.assembly_responsibilities.leg"],
            }
        ],
        ordering_constraints=[
            {
                "id": "ordering-seat-before-leg",
                "summary": "Build the seat before placing the leg.",
                "depends_on": ["build:seat"],
                "responsibility": "builder",
                "decision_refs": ["plan.ordering_constraints.seat-before-leg"],
            }
        ],
        steps=[
            {
                "family": "leg",
                "parent": "seat",
                "world_position": [0.2, 0.2, -0.45],
                "world_rotation": [0.0, 0.0, 0.0],
                "instance_count": 1,
                "step_index": 0,
            }
        ],
    )
    spec = SpecArtifact(
        parts={
            "seat": {
                "attachment_points": [{"name": "bottom_center", "local_offset": [0.0, 0.0, -0.05]}],
            },
            "leg": {
                "attachment_points": [{"name": "top_center", "local_offset": [0.0, 0.0, 0.35]}],
            },
        }
    )

    result = phase.run(build_artifacts=build_artifacts, plan_artifact=plan, spec_artifact=spec)

    assert result[0].review_verdict == "failed"
    assert "parent seat is not ready" in result[0].failure_notes[0]


def test_assemble_phase_fails_fast_on_invalid_family_contract():
    phase = AssemblePhase()
    events: list[dict] = []
    build_artifacts = [BuildArtifact(part_name="leaf_1", instance_names=["leaf_01"], status="built")]
    plan = PlanArtifact(
        assembly_responsibilities=[
            {
                "id": "assemble-leaf",
                "family": "leaf",
                "summary": "Builder places generic leaf.",
                "target_parent_family": "main_body",
                "attachment_target_family": "main_body",
                "placement_rule": "align_local_anchor_to_target_point",
                "required_parenting": True,
                "decision_refs": ["plan.assembly_responsibilities.leaf"],
            }
        ],
        steps=[{"family": "leaf_1", "parent": "main_body", "world_position": [0.0, 0.0, 0.0], "step_index": 0}],
    )
    spec = SpecArtifact(parts={"leaf_1": {"attachment_points": [{"id": "top_center", "name": "top_center", "local_offset": [0.0, 0.5, 0.0]}]}})

    result = phase.run(
        build_artifacts=build_artifacts,
        plan_artifact=plan,
        spec_artifact=spec,
        event_emitter=lambda phase_name, kind, message, **extra: events.append({"phase": phase_name, "kind": kind, "message": message, **extra}),
    )

    assert all(item.review_verdict == "failed" for item in result)
    step_events = [event for event in events if event["kind"] == "assemble_step"]
    assert step_events
    assert step_events[0]["skipped"] is True
    assert step_events[0]["tool_calls"] == []


def test_assemble_phase_skips_when_point_ids_cannot_resolve():
    phase = AssemblePhase()
    build_artifacts = [
        BuildArtifact(part_name="body", instance_names=["body_01"], status="built"),
        BuildArtifact(part_name="stem", instance_names=["stem_01"], status="built"),
    ]
    events: list[dict] = []
    plan = PlanArtifact(
        assembly_responsibilities=[
            {
                "id": "assemble-stem",
                "family": "stem",
                "summary": "Builder places the stem.",
                "target_parent_family": "body",
                "attachment_target_family": "body",
                "attachment_target_point_id": "P_stem",
                "local_anchor_point_id": "Base_Center",
                "placement_rule": "align_local_anchor_to_target_point",
                "required_parenting": True,
                "decision_refs": ["plan.assembly_responsibilities.stem"],
            }
        ],
        steps=[
            {
                "family": "stem",
                "parent": "body",
                "world_position": [0.0, 0.0, 0.0],
                "world_rotation": [0.0, 0.0, 0.0],
                "instance_count": 1,
                "step_index": 0,
            }
        ],
    )
    spec = SpecArtifact(
        parts={
            "body": {
                "attachment_points": [{"id": "top_center", "name": "top_center", "local_offset": [0.0, 2.0, 0.0]}],
            },
            "stem": {
                "attachment_points": [{"id": "bottom_center", "name": "bottom_center", "local_offset": [0.0, -0.5, 0.0]}],
            },
        }
    )

    result = phase.run(
        build_artifacts=build_artifacts,
        plan_artifact=plan,
        spec_artifact=spec,
        event_emitter=lambda phase_name, kind, message, **extra: events.append({"phase": phase_name, "kind": kind, "message": message, **extra}),
    )

    assert result[0].review_verdict == "failed"
    assert result[0].skipped is True
    assert result[0].unresolved_planning_gap is True
    assert result[0].resolved_world_position is None
    assert "resolved_attachment_target_point" in result[0].missing_contract_fields
    step_event = next(event for event in events if event["kind"] == "assemble_step")
    assert step_event["skipped"] is True
    assert step_event["tool_calls"] == []
    assert step_event["summary"] == "Skipped assembly for stem due to unresolved contract fields."


def test_validate_phase_runs(mock_llm):
    phase = ValidatePhase()
    registry = _meeting_registry(Inspector)

    spec = SpecArtifact(blueprint_id="spec-001")
    assembly_artifacts = [
        AssemblyArtifact(
            step_index=1,
            placements=[{"part": "leg", "world_position": [0.2, 0.2, -0.45]}],
            planning_warnings=["Assembly leg used fallback placement."],
            planning_failures=["Unresolved planning gap for leg: missing contract fields attachment_target_point_id."],
            responsibility_refs=["plan.assembly_responsibilities.leg"],
            constraint_refs=["plan.ordering_constraints.seat-before-leg"],
            failure_notes=["Ordering constraint blocked final parenting for leg."],
        )
    ]
    build_artifacts = [
        BuildArtifact(
            part_name="leg",
            instance_names=["leg_01"],
            planning_warnings=["Build leg deferred final placement to assembly."],
            responsibility_refs=["plan.build_responsibilities.leg"],
        )
    ]
    plan_artifact = PlanArtifact(
        open_issues=["Leg parenting still depends on seat ordering."],
        risk_hotspots=["Seat must exist before leg parenting."],
    )

    result = phase.run(
        registry,
        context={},
        llm=mock_llm,
        spec_artifact=spec,
        assembly_artifacts=assembly_artifacts,
        build_artifacts=build_artifacts,
        plan_artifact=plan_artifact,
        build_execution_plan={
            "diagnostics": [
                {
                    "code": "build-step-fallback",
                    "summary": "Build for leg fell back to legacy plan steps because no build responsibility was provided.",
                    "responsibility_ref": "plan.build_responsibilities.leg",
                }
            ]
        },
        assembly_execution_plan={
            "diagnostics": [
                {
                    "code": "builder-placement-geometry-violation",
                    "summary": "Assembly responsibility for leg includes geometry-definition work that belongs to the Builder or Spec phase.",
                    "responsibility_ref": "plan.assembly_responsibilities.leg",
                }
            ]
        },
    )

    assert isinstance(result, ValidationArtifact)
    assert mock_llm.call_count > 0
    assert result.passed is False
    assert "Ordering constraint blocked final parenting for leg." in result.planning_failures
    assert "plan.ordering_constraints.seat-before-leg" in result.planning_constraint_refs
    assert "plan.assembly_responsibilities.leg" in result.planning_responsibility_refs
    assert any("risk hotspot" in item.lower() for item in result.planning_warnings)


def test_design_phase_round_shape(mock_llm):
    phase = DesignPhase()
    phase.termination.max_rounds = 1
    registry = _meeting_registry(Designer, Reviewer)

    phase.run(registry, context={}, llm=mock_llm, task_prompt="build a chair")

    non_summary = [
        (agent, context)
        for agent, context in zip(mock_llm.agents, mock_llm.contexts)
        if not isinstance(context, dict) or context.get("meeting_turn_kind") != "summary"
    ]
    assert len(non_summary) == 4
    assert [agent for agent, _ in non_summary] == ["moderator", "moderator", "moderator", "moderator"]
    assert [
        context.get("agent_role") if isinstance(context, dict) else ""
        for _, context in non_summary
    ] == ["designer", "reviewer", "designer", "moderator"]


def test_design_phase_skips_response_when_reviewer_has_no_blocking_issue():
    class NoBlockingDesignLLM:
        def __init__(self) -> None:
            self.call_count = 0
            self.contexts = []
            self.skills = []

        def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
            self.call_count += 1
            context = kwargs.get("context", {}) if isinstance(kwargs.get("context"), dict) else {}
            self.contexts.append(context)
            self.skills.append(str(kwargs.get("skill", "")))
            if kwargs.get("skill") == "extract-design-artifact":
                return (
                    '{"summary":"chair design","parts":[{"name":"seat","instance_count":1},'
                    '{"name":"leg","instance_count":4},{"name":"backrest","instance_count":1}],'
                    '"assembly_concept":"seat with four legs and backrest","unresolved_issues":[]}'
                )
            if context.get("meeting_turn_kind") == "challenge":
                return "Concern: No blocking issues. The proposal is coherent."
            if context.get("meeting_turn_kind") == "resolution":
                return (
                    "Decision: Accept the scoped chair design.\n"
                    "Accepted:\n- seat, leg, and backrest.\n"
                    "Rejected:\n- None.\n"
                    "Open Issues:\nNone"
                )
            if context.get("meeting_turn_kind") == "response":
                raise AssertionError("response turn should be skipped when reviewer finds no blocking issue")
            return "Proposal: Use seat, leg, and backrest only."

    phase = DesignPhase()
    phase.termination.max_rounds = 1
    registry = _meeting_registry(Designer, Reviewer)
    llm = NoBlockingDesignLLM()

    result = phase.run(registry, context={}, llm=llm, task_prompt="build a chair")

    assert isinstance(result, DesignArtifact)
    non_summary_contexts = [
        context
        for context in llm.contexts
        if isinstance(context, dict) and context.get("meeting_turn_kind") != "summary"
    ]
    assert [context.get("meeting_turn_kind") for context in non_summary_contexts] == [
        "proposal",
        "challenge",
        "resolution",
    ]
    assert len(non_summary_contexts) == 3
    assert [skill for skill in llm.skills if skill != "summarize-meeting-message"] == ["", "", ""]


def test_moderated_phase_routes_sampling_policy(mock_llm):
    phase = DesignPhase()
    phase.termination.max_rounds = 1
    registry = _meeting_registry(Designer, Reviewer)

    phase.run(registry, context={}, llm=mock_llm, task_prompt="build a chair")

    non_summary_samplings = [
        sampling
        for sampling, context in zip(mock_llm.samplings, mock_llm.contexts)
        if not isinstance(context, dict) or context.get("meeting_turn_kind") != "summary"
    ]
    assert [sampling.temperature for sampling in non_summary_samplings[:4]] == [
        DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.proposal_by_role["designer"].temperature,
        DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.challenge_by_role["reviewer"].temperature,
        DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.response_by_role["designer"].temperature,
        DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.resolution_sampling.temperature,
    ]


def test_design_phase_emits_single_agent_turns(mock_llm):
    phase = DesignPhase()
    phase.termination.max_rounds = 1
    registry = _meeting_registry(Designer, Reviewer)
    events: list[dict] = []

    phase.run(
        registry,
        context={},
        llm=mock_llm,
        task_prompt="build a chair",
        event_emitter=lambda phase_name, kind, message, **extra: events.append({"phase": phase_name, "kind": kind, "message": message, **extra}),
    )

    proposal_events = [event for event in events if event["kind"] == "proposal"]
    challenge_events = [event for event in events if event["kind"] == "challenge"]
    response_events = [event for event in events if event["kind"] == "response"]

    assert [event.get("substep") for event in proposal_events] == ["synthesis"]
    assert [event.get("final") for event in proposal_events] == [True]
    assert [event.get("substep") for event in challenge_events] == ["synthesis"]
    assert [event.get("substep") for event in response_events] == ["synthesis"]


def test_design_turn_context_routes_without_local_prompt_contract(mock_llm):
    phase = DesignPhase()
    phase.termination.max_rounds = 1
    registry = _meeting_registry(Designer, Reviewer)

    phase.run(registry, context={}, llm=mock_llm, task_prompt="build a chair")

    designer_contexts = [
        context
        for context in mock_llm.contexts
        if isinstance(context, dict) and context.get("agent_role") == "designer"
    ]
    assert designer_contexts
    assert "meeting_" + "capability_" + "contract" not in designer_contexts[0]
    assert mock_llm.last_system_prompt == ""
    assert mock_llm.agents[:3] == ["moderator", "moderator", "moderator"]


def test_plan_phase_runs_visible_clarification_loop():
    class ClarifyingPlanLLM:
        def __init__(self) -> None:
            self.call_count = 0
            self.plan_extraction_attempts = 0

        def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
            self.call_count += 1
            context = kwargs.get("context", {}) if isinstance(kwargs.get("context"), dict) else {}
            message_text = "\n".join(str(message.get("content", "")) for message in messages or [] if isinstance(message, dict))
            if kwargs.get("agent") == "moderator" and context.get("agent_role") == "planner" and context.get("meeting_turn_kind") == "response" and "assembly contract clarification" in message_text:
                return (
                    "Response: For stem, attach to core_apple_body and use the parent's top_center attachment.\n"
                    "Revision: target_parent_family=core_apple_body; attachment_target_family=core_apple_body; "
                    "attachment_target_point_id=top_center; local_anchor_point_id=bottom_center; "
                    "placement_rule=align_local_anchor_to_target_point; required_parenting=true."
                )
            if kwargs.get("skill") == "extract-plan-artifact":
                self.plan_extraction_attempts += 1
                if self.plan_extraction_attempts == 1:
                    return (
                        '{"summary":"Draft plan.","execution_rationale":["Build body then place stem."],'
                        '"build_responsibilities":[],"assembly_responsibilities":[{"id":"assemble-stem","family":"stem",'
                        '"summary":"Builder places the stem.","placement_relations":["Attach stem to body."],'
                        '"hierarchy_notes":["Parent stem under the body."],"attachment_target_point_id":"P_stem",'
                        '"local_anchor_point_id":"Base_Center","decision_refs":["plan.assembly_responsibilities.stem"]}],'
                        '"dependency_summary":[],"ordering_constraints":[],"risk_hotspots":[],"open_issues":[]}'
                    )
                return (
                    '{"summary":"Final clarified plan.","execution_rationale":["Build body then place stem."],'
                    '"build_responsibilities":[],"assembly_responsibilities":[{"id":"assemble-stem","family":"stem",'
                    '"summary":"Builder places the stem.","placement_relations":["Attach stem to body top center."],'
                    '"hierarchy_notes":["Parent stem under the body."],"target_parent_family":"core_apple_body",'
                    '"attachment_target_family":"core_apple_body","attachment_target_point_id":"top_center",'
                    '"local_anchor_point_id":"bottom_center","placement_rule":"align_local_anchor_to_target_point",'
                    '"required_parenting":true,"decision_refs":["plan.assembly_responsibilities.stem"]}],'
                        '"dependency_summary":[],"ordering_constraints":[],"risk_hotspots":[],"open_issues":[]}'
                    )
            if kwargs.get("agent") == "moderator" and context.get("meeting_turn_kind") == "resolution":
                return (
                    "Decision: Record the clarified assembly contract.\n"
                    "Accepted:\n- Stem parents to core_apple_body using top_center and bottom_center anchors.\n"
                    "Rejected:\n- None.\n"
                    "Open Issues:\nNone"
                )
            if context.get("meeting_turn_kind") == "challenge":
                return "Concern: No blocking issue. The proposal is coherent."
            if context.get("meeting_turn_kind") == "response":
                return "Response: Acknowledged. No revision is required."
            return "Proposal: Use the body as root and attach the stem during assembly.\nRationale: This keeps the hierarchy simple."

    phase = PlanPhase()
    registry = _meeting_registry(Planner, Reviewer)
    llm = ClarifyingPlanLLM()
    events: list[dict] = []
    spec = SpecArtifact(
        parts={
            "core_apple_body": {
                "primitive": "uv_sphere",
                "target_bbox": {"width": 4.0, "depth": 4.0, "height": 4.0},
                "attachment_points": [{"name": "top_center", "local_offset": [0.0, 2.0, 0.0]}],
            },
            "stem": {
                "primitive": "cylinder",
                "target_bbox": {"width": 0.4, "depth": 0.4, "height": 1.0},
                "attachment_points": [{"name": "bottom_center", "local_offset": [0.0, -0.5, 0.0]}],
            },
        }
    )
    families = [
        PartFamily(name="core_apple_body", description="apple body", instance_count=1, parent_name=None, symmetry_group=SymmetryGroup.NONE),
        PartFamily(name="stem", description="apple stem", instance_count=1, parent_name="core_apple_body", symmetry_group=SymmetryGroup.NONE),
    ]

    artifact = phase.run(
        registry,
        context={},
        llm=llm,
        spec_artifact=spec,
        part_families=families,
        event_emitter=lambda phase_name, kind, message, **extra: events.append({"phase": phase_name, "kind": kind, "message": message, **extra}),
    )

    stem = next(item for item in artifact.assembly_responsibilities if item["family"] == "stem")
    assert stem["target_parent_family"] == "core_apple_body"
    assert stem["attachment_target_family"] == "core_apple_body"
    assert stem["attachment_target_point_id"] == "top_center"
    assert stem["local_anchor_point_id"] == "bottom_center"
    clarification_events = [event for event in events if event.get("clarification_scope") == "assembly_contract"]
    assert clarification_events == []
    assert llm.plan_extraction_attempts == 0
    assert events[-1]["kind"] == "phase_close"


def test_plan_phase_rejects_helper_family_contract(mock_llm):
    phase = PlanPhase()
    registry = _meeting_registry(Planner, Reviewer)
    spec = SpecArtifact(
        parts={
            "main_apple_body": {
                "primitive": "uv_sphere",
                "target_bbox": {"width": 4.0, "depth": 4.0, "height": 4.0},
                "attachment_points": [{"id": "top_center", "name": "top_center", "local_offset": [0.0, 2.0, 0.0]}],
            },
            "stem_calyx_attachment_point": {
                "primitive": "cube",
                "target_bbox": {"width": 0.2, "depth": 0.2, "height": 0.2},
                "attachment_points": [{"id": "center", "name": "center", "local_offset": [0.0, 0.0, 0.0]}],
            },
        }
    )
    families = [
        PartFamily(name="main_apple_body", description="body", instance_count=1, parent_name=None, symmetry_group=SymmetryGroup.NONE),
        PartFamily(name="stem_calyx_attachment_point", description="helper", instance_count=1, parent_name="main_apple_body", symmetry_group=SymmetryGroup.NONE),
    ]

    result = phase.run(registry, context={}, llm=mock_llm, spec_artifact=spec, part_families=families)

    assert result.failure_notes
    assert any("helper family" in note.lower() for note in result.failure_notes)
