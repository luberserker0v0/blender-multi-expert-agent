from __future__ import annotations

import json
from types import SimpleNamespace

from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
from ai_3d_modeling_agent.multi_expert.artifacts import BuildArtifact, DesignArtifact, PlanArtifact, SpecArtifact
from ai_3d_modeling_agent.multi_expert.core.builder_intent import parse_builder_intent
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import (
    build_design_artifact_from_markdown_state,
    build_spec_artifact_from_markdown_state,
    write_design_markdown,
    write_plan_markdown,
    write_spec_markdown,
)
from ai_3d_modeling_agent.multi_expert.core.validator import ProgrammaticValidator
from ai_3d_modeling_agent.multi_expert.phases import AssemblePhase, BuildPhase, BuilderExecutionPhase
from ai_3d_modeling_agent.multi_expert.phases.assemble_phase import _normalize_extracted_assembly_steps
from ai_3d_modeling_agent.multi_expert.phases.build_phase import _normalize_extracted_build_instances
from ai_3d_modeling_agent.multi_expert.core.action_plan import AgentActionPlan


def test_markdown_artifact_writer_creates_docs_and_thin_index(tmp_path):
    context = {"runtime_root": str(tmp_path), "session_id": "sess-1"}
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary="Accept `seat`, `leg`, and `backrest`; four legs.",
        rejected_alternatives=[],
        open_issues=[],
    )
    design = build_design_artifact_from_markdown_state(
        "Create a chair with a seat, four legs, and a backrest.",
        state,
    )
    spec = SpecArtifact(summary="Spec captured as Markdown", parts={"seat": {"instance_count": 1}})
    plan = PlanArtifact(
        summary="Build each part then place it.",
        build_responsibilities=[{"family": "seat"}],
        assembly_responsibilities=[{"family": "seat"}],
    )

    write_design_markdown(context, design, meeting_state=state)
    write_spec_markdown(context, spec, design=design, meeting_state=state)
    write_plan_markdown(context, plan, meeting_state=state)

    artifact_root = tmp_path / "session_data" / "sess-1" / "artifacts"
    assert (artifact_root / "design.md").read_text(encoding="utf-8").startswith("# Design")
    assert "## Part Specifications" in (artifact_root / "spec.md").read_text(encoding="utf-8")
    assert "## Ordered Todos" in (artifact_root / "build_plan.md").read_text(encoding="utf-8")
    assert "- [ ] build:seat" in (artifact_root / "todo.md").read_text(encoding="utf-8")
    index = json.loads((artifact_root / "artifact_index.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in index["artifacts"]}
    assert {"design.md", "spec.md", "build_plan.md", "todo.md"} <= paths
    assert "leg" in [part["name"] for part in design.parts]
    assert next(part for part in design.parts if part["name"] == "leg")["instance_count"] == 4


def test_builder_execution_phase_keeps_assemble_wire_name():
    phase = BuilderExecutionPhase()

    assert phase.name == "assemble"
    assert isinstance(AssemblePhase(), BuilderExecutionPhase)


def test_design_markdown_state_parser_filters_root_container_names():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary="Accepted: `Chair`, `seat`, `leg`, `backrest`; Chair is only the assembly container.",
        round_change_summary="",
        rejected_alternatives=[],
        open_issues=[],
    )

    design = build_design_artifact_from_markdown_state(
        "Create a simple chair with one seat, four legs, and one backrest.",
        state,
    )

    names = [part["name"] for part in design.parts]
    assert names == ["seat", "leg", "backrest"]
    assert next(part for part in design.parts if part["name"] == "leg")["instance_count"] == 4


def test_design_markdown_state_parser_filters_agent_role_names_from_resolution():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary=(
            "Decision: Accept the design proposal from the `designer` as proposed by the `reviewer`. "
            "Accepted Items: Root Part `chair`; Parts/Families: `seat`, `leg`, `backrest`."
        ),
        round_change_summary="",
        rejected_alternatives=[],
        open_issues=[],
    )

    design = build_design_artifact_from_markdown_state(
        "Build a simple chair with one square seat, four legs, and one backrest.",
        state,
    )

    names = [part["name"] for part in design.parts]
    assert names == ["seat", "leg", "backrest"]
    assert not {"designer", "reviewer"} & set(names)


def test_design_markdown_state_parser_uses_round_change_when_resolution_is_truncated():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary=(
            "**Decision:** The initial Design Proposal stands confirmed. "
            "**Accepted:** * **Root Part:** `chair` * **Part Families:** `seat`, `"
        ),
        round_change_summary=(
            "The design response confirms structural decomposition. "
            "Root=`chair`, Parts=`{seat, leg, backrest}`, Repeats=`leg (x4)`."
        ),
        accepted_decisions=[],
        resolution_history=[],
        resolved_challenges=[],
        rejected_alternatives=[],
        open_issues=[],
    )

    design = build_design_artifact_from_markdown_state("mojibake chair task", state)

    names = [part["name"] for part in design.parts]
    assert names == ["seat", "leg", "backrest"]
    assert next(part for part in design.parts if part["name"] == "leg")["instance_count"] == 4


def test_design_markdown_state_parser_uses_full_conversation_when_state_is_truncated():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary="## Decision Record\nAccept the proposal, with structural necessity.",
        round_change_summary="Here is the response addressing reviewer concerns. I propose t",
        accepted_decisions=[],
        resolution_history=[],
        resolved_challenges=[],
        rejected_alternatives=[],
        open_issues=[],
    )
    conversation = SimpleNamespace(
        messages=[
            SimpleNamespace(
                content=(
                    "Designer proposal for a simple chair: root `chair`; accepted part families "
                    "`seat`, `leg`, `backrest`, and optional helper `seat_support_frame`. "
                    "Use four `leg` instances."
                )
            ),
            SimpleNamespace(content="Reviewer says the seat support frame should not be a separate required family."),
            SimpleNamespace(content="Resolution: keep `seat`, `leg`, and `backrest`; four legs."),
        ]
    )

    design = build_design_artifact_from_markdown_state(
        "mojibake chair task",
        state,
        conversation=conversation,
    )

    names = [part["name"] for part in design.parts]
    assert names == ["seat", "leg", "backrest"]
    assert next(part for part in design.parts if part["name"] == "leg")["instance_count"] == 4


def test_design_markdown_state_parser_filters_instance_variant_names():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary=(
            "Accepted: Part Families are `seat`, `leg`, `backrest`. "
            "Instances & Counts: 1x `seat`, 4x `leg` (`leg_1` to `leg_4`), 1x `backrest`."
        ),
        round_change_summary="",
        rejected_alternatives=[],
        open_issues=[],
    )

    design = build_design_artifact_from_markdown_state(
        "Build a simple chair with one square seat, four legs, and one backrest.",
        state,
    )

    names = [part["name"] for part in design.parts]
    assert names == ["seat", "leg", "backrest"]
    assert next(part for part in design.parts if part["name"] == "leg")["instance_count"] == 4


def test_design_markdown_state_parser_collapses_simple_cube_noise():
    state = SimpleNamespace(
        phase_status="completed",
        last_resolution_summary=(
            "Accept the design response from `designer` and resolve `reviewer` concerns. "
            "Accepted decisions mention `Cube_Model`, `Cube_Face`, and `Cube_Edge`, but the user asked for one simple cube."
        ),
        round_change_summary="",
        rejected_alternatives=[],
        open_issues=[],
    )

    design = build_design_artifact_from_markdown_state("Build a simple cube", state)

    assert design.parts == [
        {
            "name": "cube",
            "description": "cube part from accepted design discussion",
            "instance_count": 1,
            "parent_name": None,
            "symmetry_group": "NONE",
        }
    ]


def test_spec_markdown_state_parser_uses_accepted_dimension_text(tmp_path):
    state = SimpleNamespace(
        phase_status="resolved",
        last_resolution_summary=(
            "Decision: Accept seat geometry. Defined as a "
            "$450 \\text{ mm} \\times 45 \\text{ mm}$ rectangle."
        ),
        round_change_summary="",
        open_issues=[],
        todo_groups=[
            {
                "target_name": "seat",
                "accepted_summary": (
                    "Accepted: `seat` geometry is a flat plane rectangle with "
                    "$450 \\text{ mm} \\times 45 \\text{ mm}$ dimensions."
                ),
            }
        ],
        revision_requests=[],
    )
    design = DesignArtifact(
        summary="Chair with one seat.",
        parts=[{"name": "seat", "description": "flat seat", "instance_count": 1}],
    )

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["seat"]["target_bbox"] == {"width": 0.45, "depth": 0.045, "height": 0.02}
    assert spec.parts["seat"]["geometry_source"] == "accepted_markdown_plane"
    write_spec_markdown({"runtime_root": str(tmp_path), "session_id": "spec-md"}, spec, design=design, meeting_state=state)
    text = (tmp_path / "session_data" / "spec-md" / "artifacts" / "spec.md").read_text(encoding="utf-8")
    assert "- Target bbox: width=0.45, depth=0.045, height=0.02" in text


def test_spec_markdown_state_parser_accepts_labeled_three_axis_dimensions():
    state = SimpleNamespace(
        last_resolution_summary="Backrest dimensions: width 0.5 m, depth 0.08 m, height 0.7 m.",
        round_change_summary="",
        open_issues=[],
        todo_groups=[],
        revision_requests=[],
    )
    design = DesignArtifact(parts=[{"name": "backrest", "instance_count": 1}])

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["backrest"]["target_bbox"] == {"width": 0.5, "depth": 0.08, "height": 0.7}
    assert spec.parts["backrest"]["geometry_source"] == "accepted_markdown"


def test_spec_markdown_state_parser_keeps_part_specific_dimensions():
    state = SimpleNamespace(
        last_resolution_summary=(
            "Seat uses 0.45 m x 0.45 m x 0.08 m. "
            "Leg uses 0.05 m diameter x 0.75 m height. "
            "Backrest uses 55cm H x 45cm W."
        ),
        round_change_summary="",
        open_issues=[],
        todo_groups=[
            {"target_name": "seat", "accepted_summary": "Seat dimensions: 0.45 m x 0.45 m x 0.08 m slab."},
            {"target_name": "leg", "accepted_summary": "Leg dimensions: 0.05 m diameter x 0.75 m height cylinder."},
            {"target_name": "backrest", "accepted_summary": "Backrest is a rectangular plane, 55cm H x 45cm W."},
        ],
        revision_requests=[],
    )
    design = DesignArtifact(
        parts=[
            {"name": "seat", "instance_count": 1},
            {"name": "leg", "instance_count": 4},
            {"name": "backrest", "instance_count": 1},
        ]
    )

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["seat"]["target_bbox"] == {"width": 0.45, "depth": 0.45, "height": 0.08}
    assert spec.parts["leg"]["target_bbox"] == {"width": 0.05, "depth": 0.05, "height": 0.75}
    assert spec.parts["backrest"]["target_bbox"] == {"width": 0.45, "height": 0.55, "depth": 0.02}


def test_spec_markdown_state_parser_accepts_braced_wdh_notation():
    state = SimpleNamespace(
        last_resolution_summary="",
        round_change_summary="",
        open_issues=[],
        todo_groups=[
            {
                "target_name": "seat",
                "accepted_summary": "Geometry includes {W}=0.45{m}, {D}=0.45{m}, {H}=0.08{m}.",
            },
            {
                "target_name": "leg",
                "accepted_summary": "Defined as Cylindrical ({D}=0.05{m}, {H}=0.75{m}).",
            },
        ],
        revision_requests=[],
    )
    design = DesignArtifact(parts=[{"name": "seat"}, {"name": "leg", "instance_count": 4}])

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["seat"]["target_bbox"] == {"width": 0.45, "depth": 0.45, "height": 0.08}
    assert spec.parts["leg"]["target_bbox"] == {"width": 0.05, "depth": 0.05, "height": 0.75}


def test_spec_markdown_state_parser_maps_lwh_to_width_depth_height():
    state = SimpleNamespace(
        last_resolution_summary="",
        round_change_summary="",
        open_issues=[],
        todo_groups=[
            {
                "target_name": "seat",
                "accepted_summary": "Shape=Rectangular Prism, L = 0.45 {m}, W = 0.45 {m}, H = 0.08 {m}.",
            },
            {
                "target_name": "backrest",
                "accepted_summary": "Length (L) = 0.45 {m}, Width (W) = 0.08 {m}, Height (H) = 0.55 {m}.",
            },
        ],
        revision_requests=[],
    )
    design = DesignArtifact(parts=[{"name": "seat"}, {"name": "backrest"}])

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["seat"]["target_bbox"] == {"width": 0.45, "depth": 0.45, "height": 0.08}
    assert spec.parts["backrest"]["target_bbox"] == {"width": 0.45, "depth": 0.08, "height": 0.55}


def test_spec_markdown_state_parser_infers_unit_bbox_for_simple_cube_task():
    state = SimpleNamespace(
        phase_status="resolved",
        last_resolution_summary="The cube part exists and is a cube primitive.",
        round_change_summary="",
        open_issues=[],
        todo_groups=[],
        revision_requests=[],
    )
    design = DesignArtifact(
        task_prompt="Build a simple cube",
        parts=[{"name": "cube", "description": "single cube", "instance_count": 1}],
    )

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["cube"]["target_bbox"] == {"width": 1.0, "depth": 1.0, "height": 1.0}
    assert spec.parts["cube"]["geometry_source"] == "accepted_task_primitive"


def test_spec_markdown_state_parser_infers_unit_bbox_from_simple_cube_summary():
    state = SimpleNamespace(
        phase_status="resolved",
        last_resolution_summary="The cube geometry depends on parameter L and needs user input.",
        round_change_summary="",
        open_issues=[],
        todo_groups=[],
        revision_requests=[],
    )
    design = DesignArtifact(
        summary="Accepted simple cube design.",
        assembly_concept="Build a simple cube.",
        parts=[{"name": "cube", "description": "single cube", "instance_count": 1}],
    )

    spec = build_spec_artifact_from_markdown_state(design, state)

    assert spec.parts["cube"]["target_bbox"] == {"width": 1.0, "depth": 1.0, "height": 1.0}
    assert spec.parts["cube"]["geometry_source"] == "accepted_task_primitive"


def test_builder_intent_parser_accepts_one_step_markdown():
    intent = parse_builder_intent(
        """# Builder Step

## Intent
create

## Target
seat

## Parameters
- primitive: cube
- scale: 2, 2, 0.2

## Validation
Verify object `seat` exists.
"""
    )

    assert intent.intent == "create"
    assert intent.target == "seat"
    assert intent.parameters["primitive"] == "cube"
    assert intent.parameters["scale"] == [2, 2, 0.2]


def test_builder_intent_parser_rejects_unsupported_intent():
    try:
        parse_builder_intent("## Intent\nboolean_carve\n\n## Target\nseat")
    except ValueError as exc:
        assert "Unsupported builder intent" in str(exc)
    else:
        raise AssertionError("unsupported intent should fail")


def test_builder_intent_parser_salvages_echoed_task_call_prompt():
    intent = parse_builder_intent(
        r'''
Here is the tool call for the user request: `task(description="builder execution intent for seat", prompt="Create a single, executable Blender/MCP command intended to create the 'seat' part.\n\n*   **Action:** Create (create object in scene)\n*   **Target Name:** Seat\n*   **Primitive Type:** Cylinder\n*   **Instance Count:** 1\n*   **Scale:** [0.8, 0.3, 0.02]\n\nReturn ONLY the final executable intent string in Markdown format.", subagent_type="builder")`
'''
    )

    assert intent.intent == "create"
    assert intent.target == "seat"
    assert intent.parameters["primitive_type"] == "cylinder"
    assert intent.parameters["instance_count"] == 1
    assert intent.parameters["scale"] == [0.8, 0.3, 0.02]


def test_builder_intent_parser_accepts_inline_heading_values_and_star_bullets():
    intent = parse_builder_intent(
        """## Intent: create
## Target: seat
## Parameters:
*   primitive\\_type: cube
*   source\\_name: temporary\\_seat\\_0
*   instance\\_count: 1
*   scale: [0.45, 0.45, 0.08]
## Validation: object existence and scale will be checked by Python
"""
    )

    assert intent.intent == "create"
    assert intent.target == "seat"
    assert intent.parameters["primitive_type"] == "cube"
    assert intent.parameters["source_name"] == "temporary_seat_0"
    assert intent.parameters["instance_count"] == 1
    assert intent.parameters["scale"] == [0.45, 0.45, 0.08]


def test_builder_intent_parser_maps_natural_operation_to_create():
    intent = parse_builder_intent(
        """## Operation
Build the component named "cube" by procedurally generating a standard cube geometry.

## Target
cube

## Parameters
- primitive_type: cube
- instance_count: 1
- scale: [1.0, 1.0, 1.0] (unit cube)
- source_name: cube_source

## Validation
Verify cube_01 exists and has unit scale.
""",
        expected_intent="create",
    )

    assert intent.intent == "create"
    assert intent.target == "cube"
    assert intent.parameters["primitive_type"] == "cube"
    assert intent.parameters["scale"] == [1.0, 1.0, 1.0]


def test_build_phase_executes_one_builder_markdown_todo(tmp_path):
    class BuilderIntentLLM:
        def __init__(self) -> None:
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("skill") == "blender-build-actions":
                return json.dumps(
                    {
                        "status": "ready",
                        "parts": [
                            {
                                "part_name": "seat",
                                "source_object_name": "seat_source",
                                "instance_names": ["seat_01"],
                                "actions": [
                                    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "seat_source"}},
                                    {"action_type": "set_object_scale", "parameters": {"name": "seat_source", "scale": [0.5, 0.5, 0.1]}},
                                    {"action_type": "duplicate_object", "parameters": {"name": "seat_source", "new_name": "seat_01"}},
                                    {"action_type": "delete_object", "parameters": {"name": "seat_source"}},
                                ],
                            }
                        ],
                    }
                )
            return """# Builder Intent

## Intent
create

## Target
seat

## Parameters
- primitive_type: cube
- source_name: seat_source
- instance_count: 1
- scale: [0.5, 0.5, 0.1]

## Validation
Python should verify the seat instance exists.
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    plan = PlanArtifact(
        build_responsibilities=[{"family": "seat"}],
        assembly_responsibilities=[{"family": "seat"}],
    )
    spec = SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 0.2}}})
    object_ops = SimulatedBlenderObjectOps()
    llm = BuilderIntentLLM()

    result = BuildPhase().run(
        plan_artifact=plan,
        spec_artifact=spec,
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=llm,
    )

    assert result[0].status == "built"
    assert result[0].instance_names == ["seat_01"]
    assert object_ops.object_exists("seat_01")
    assert llm.calls[0]["agent"] == "moderator"
    assert llm.calls[0]["context"]["delegated_agent"] == "builder"
    assert llm.calls[1]["skill"] == "blender-build-actions"
    assert "## Operation" in llm.calls[0]["messages"][0]["content"]
    assert "docs/blender_build_capabilities.md" in llm.calls[0]["messages"][0]["content"]
    assert "No preface" in llm.calls[0]["messages"][0]["content"]
    artifact_root = tmp_path / "session_data" / "builder-md" / "artifacts"
    assert "- [x] build:seat" in (artifact_root / "todo.md").read_text(encoding="utf-8")
    assert "Builder todo build:seat" in (artifact_root / "build_log.md").read_text(encoding="utf-8")


def test_build_phase_blocks_unsupported_builder_markdown_intent(tmp_path):
    class UnsupportedIntentLLM:
        def call(self, **kwargs):
            return """## Intent
boolean_carve

## Target
seat
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md-blocked",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    object_ops = SimulatedBlenderObjectOps()
    result = BuildPhase().run(
        plan_artifact=PlanArtifact(build_responsibilities=[{"family": "seat"}]),
        spec_artifact=SpecArtifact(parts={"seat": {"primitive": "cube"}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=UnsupportedIntentLLM(),
    )

    assert result[0].status == "failed"
    assert "Unsupported builder intent" in result[0].failure_notes[0]
    artifact_root = tmp_path / "session_data" / "builder-md-blocked" / "artifacts"
    assert "- [ ] build:seat" in (artifact_root / "todo.md").read_text(encoding="utf-8")
    assert "Result: failed" in (artifact_root / "build_log.md").read_text(encoding="utf-8")


def test_build_phase_executes_natural_builder_operation(tmp_path):
    class NaturalOperationLLM:
        def __init__(self) -> None:
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("skill") == "blender-build-actions":
                return json.dumps(
                    {
                        "status": "ready",
                        "parts": [
                            {
                                "part_name": "Cube Part",
                                "source_object_name": "cube_source",
                                "instance_names": ["cube_01"],
                                "actions": [
                                    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "cube_source"}},
                                    {"action_type": "set_object_scale", "parameters": {"name": "cube_source", "scale": [1.0, 1.0, 1.0]}},
                                    {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}},
                                    {"action_type": "delete_object", "parameters": {"name": "cube_source"}},
                                ],
                            }
                        ],
                    }
                )
            return """## Operation
Build the component named "cube" by procedurally generating a standard cube geometry.

## Target
cube

## Parameters
- primitive_type: cube
- source_name: cube_source
- instance_count: 1
- scale: [1.0, 1.0, 1.0] (unit cube)

## Validation
Python should verify the cube instance exists.
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md-natural",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    object_ops = SimulatedBlenderObjectOps()
    llm = NaturalOperationLLM()
    result = BuildPhase().run(
        plan_artifact=PlanArtifact(build_responsibilities=[{"family": "cube"}]),
        spec_artifact=SpecArtifact(parts={"cube": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=llm,
    )

    assert result[0].status == "built"
    assert result[0].part_name == "cube"
    assert object_ops.object_exists("cube_01")
    assert object_ops.get_object_scale("cube_01") == [0.5, 0.5, 0.5]
    assert result[0].action_history[-1]["extracted_action_json"]
    assert any(call.get("skill") == "blender-build-actions" for call in llm.calls)


def test_build_phase_normalizes_source_duplicate_extraction(tmp_path):
    class SourceDuplicateLLM:
        def call(self, **kwargs):
            if kwargs.get("skill") == "blender-build-actions":
                return json.dumps(
                    {
                        "operation": "create_primitive",
                        "parameters": {"primitive_type": "cube", "name": "cube_source"},
                        "post_operation_actions": [
                            {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}},
                        ],
                    }
                )
            return """## Operation
Create one cube.

## Target
cube
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md-normalize-source",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    object_ops = SimulatedBlenderObjectOps()

    result = BuildPhase().run(
        plan_artifact=PlanArtifact(build_responsibilities=[{"family": "cube"}]),
        spec_artifact=SpecArtifact(parts={"cube": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0}}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=SourceDuplicateLLM(),
    )

    assert result[0].status == "built"
    assert result[0].instance_names == ["cube_01"]
    assert object_ops.object_exists("cube_01")
    assert not object_ops.object_exists("cube_source")
    assert object_ops.get_object_scale("cube_01") == [0.5, 0.5, 0.5]


def test_build_phase_accepts_root_name_from_extracted_build_action(tmp_path):
    class RootNameExtractionLLM:
        def call(self, **kwargs):
            if kwargs.get("skill") == "blender-build-actions":
                return json.dumps(
                    {
                        "operation": "create_primitive",
                        "name": "seat_source",
                        "parameters": {"primitive_type": "cube"},
                        "action_sequence": [
                            {
                                "action_type": "set_object_scale",
                                "parameters": {"name": "seat_source", "scale": [1.0, 1.0, 1.0]},
                            },
                            {
                                "action_type": "duplicate_object",
                                "parameters": {"name": "seat_source", "new_name": "seat_01"},
                            },
                            {"action_type": "delete_object", "parameters": {"name": "seat_source"}},
                        ],
                    }
                )
            return """## Operation
Create one instance of the `seat` part geometry.

## Target
seat

## Parameters
- primitive_type: cube
- instance_count: 1
- scale: [0.5, 0.5, 0.1]
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md-root-name",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    object_ops = SimulatedBlenderObjectOps()

    result = BuildPhase().run(
        plan_artifact=PlanArtifact(build_responsibilities=[{"family": "seat"}]),
        spec_artifact=SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {"width": 0.5, "depth": 0.5, "height": 0.1}}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=RootNameExtractionLLM(),
    )

    assert result[0].status == "built"
    assert result[0].instance_names == ["seat_01"]
    assert object_ops.object_exists("seat_01")
    assert not object_ops.object_exists("seat_source")
    assert object_ops.get_object_scale("seat_01") == [0.25, 0.25, 0.05]


def test_build_phase_falls_back_to_python_plan_for_missing_builder_intent(tmp_path):
    class MissingIntentLLM:
        def call(self, **kwargs):
            return "The builder tool is unavailable, so no Markdown intent was produced."

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-md-fallback",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    object_ops = SimulatedBlenderObjectOps()
    result = BuildPhase().run(
        plan_artifact=PlanArtifact(build_responsibilities=[{"family": "seat"}]),
        spec_artifact=SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {"width": 0.5, "depth": 0.4, "height": 0.1}}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=MissingIntentLLM(),
    )

    assert result[0].status == "built"
    assert object_ops.object_exists("seat_01")
    assert "fallback" in result[0].planning_warnings[0].lower()
    artifact_root = tmp_path / "session_data" / "builder-md-fallback" / "artifacts"
    assert "Python fallback" in (artifact_root / "build_log.md").read_text(encoding="utf-8")


def test_assemble_phase_executes_one_builder_place_markdown_todo(tmp_path):
    class BuilderPlaceLLM:
        def __init__(self) -> None:
            self.calls = []

        def call(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs.get("skill") == "blender-assembly-actions":
                return json.dumps(
                    {
                        "status": "ready",
                        "steps": [
                            {
                                "step_index": 0,
                                "placements": [{"part": "seat", "instances": ["seat_01"]}],
                                "actions": [
                                    {"action_type": "show_object", "parameters": {"name": "seat_01"}},
                                    {"action_type": "move_object", "parameters": {"name": "seat_01", "location": [1.0, 2.0, 3.0]}},
                                ],
                            }
                        ],
                    }
                )
            return """# Builder Intent

## Intent
place

## Target
seat

## Parameters
- instances: seat_01
- location: [1.0, 2.0, 3.0]
- rotation_degrees: [0.0, 0.0, 0.0]

## Validation
Python should verify the seat instance location.
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-place-md",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    plan = PlanArtifact(
        build_responsibilities=[{"family": "seat"}],
        assembly_responsibilities=[{"family": "seat", "placement_rule": "place_at_world_position"}],
        steps=[{"family": "seat", "world_position": [1.0, 2.0, 3.0], "world_rotation": [0.0, 0.0, 0.0], "step_index": 0}],
    )
    object_ops = SimulatedBlenderObjectOps()
    object_ops.create_primitive("cube", "seat_01")
    llm = BuilderPlaceLLM()

    result = AssemblePhase().run(
        build_artifacts=[BuildArtifact(part_name="seat", instance_names=["seat_01"], status="built")],
        plan_artifact=plan,
        spec_artifact=SpecArtifact(parts={"seat": {"primitive": "cube"}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=llm,
    )

    assert result[0].review_verdict == "approved"
    assert object_ops.get_object_location("seat_01") == [1.0, 2.0, 3.0]
    assert llm.calls[0]["agent"] == "moderator"
    assert llm.calls[0]["context"]["delegated_agent"] == "builder"
    assert llm.calls[1]["skill"] == "blender-assembly-actions"
    assert "## Operation" in llm.calls[0]["messages"][0]["content"]
    assert "docs/blender_build_capabilities.md" in llm.calls[0]["messages"][0]["content"]
    assert "No preface" in llm.calls[0]["messages"][0]["content"]
    artifact_root = tmp_path / "session_data" / "builder-place-md" / "artifacts"
    todo_text = (artifact_root / "todo.md").read_text(encoding="utf-8")
    assert "- [x] build:seat" in todo_text
    assert "- [x] place:seat" in todo_text
    assert "Builder todo place:seat" in (artifact_root / "build_log.md").read_text(encoding="utf-8")


def test_assemble_phase_uses_python_chair_instance_layout_for_legs(tmp_path):
    class ZeroLocationPlaceLLM:
        def call(self, **kwargs):
            payload = json.loads(kwargs["messages"][0]["content"])
            family = payload["target_family"]
            if kwargs.get("skill") == "blender-assembly-actions":
                normalized = payload["normalized_assembly_item"]
                instances = payload.get("available_instances", [])
                positions = normalized.get("instance_world_positions") or [normalized.get("world_position", [0.0, 0.0, 0.0])] * len(instances)
                actions = []
                for name, position in zip(instances, positions):
                    actions.append({"action_type": "show_object", "parameters": {"name": name}})
                    actions.append({"action_type": "move_object", "parameters": {"name": name, "location": position}})
                return json.dumps(
                    {
                        "status": "ready",
                        "steps": [
                            {
                                "step_index": payload.get("required_ready_shape", {}).get("steps", [{}])[0].get("step_index", 0),
                                "placements": [{"part": family, "instances": instances}],
                                "actions": actions,
                            }
                        ],
                    }
                )
            instances = ", ".join(payload.get("available_instances", []))
            return f"""## Operation: place these instances at the normalized chair positions
## Target: {family}
## Parameters:
- instances: {instances}
- location: [0.0, 0.0, 0.0]
- rotation_degrees: [0.0, 0.0, 0.0]
- parent: null
## Validation
Python should verify placement.
"""

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-chair-layout",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    plan = PlanArtifact(
        build_responsibilities=[{"family": "seat"}, {"family": "leg"}, {"family": "backrest"}],
        assembly_responsibilities=[
            {"family": "seat", "placement_rule": "place_at_world_position"},
            {"family": "leg", "placement_rule": "place_at_world_position"},
            {"family": "backrest", "placement_rule": "place_at_world_position"},
        ],
        steps=[
            {"family": "seat", "world_position": [0.0, 0.0, 0.0], "world_rotation": [0.0, 0.0, 0.0], "step_index": 0},
            {"family": "leg", "world_position": [0.0, 0.0, 0.0], "world_rotation": [0.0, 0.0, 0.0], "step_index": 1},
            {"family": "backrest", "world_position": [0.0, 0.0, 0.0], "world_rotation": [0.0, 0.0, 0.0], "step_index": 2},
        ],
    )
    spec = SpecArtifact(
        parts={
            "seat": {"primitive": "cube", "target_bbox": {"width": 0.45, "depth": 0.45, "height": 0.08}},
            "leg": {"primitive": "cylinder", "target_bbox": {"width": 0.05, "depth": 0.05, "height": 0.75}},
            "backrest": {"primitive": "cube", "target_bbox": {"width": 0.45, "depth": 0.08, "height": 0.55}},
        }
    )
    object_ops = SimulatedBlenderObjectOps()
    for name in ("seat_01", "leg_01", "leg_02", "leg_03", "leg_04", "backrest_01"):
        object_ops.create_primitive("cube", name)

    result = AssemblePhase().run(
        build_artifacts=[
            BuildArtifact(part_name="seat", instance_names=["seat_01"], status="built"),
            BuildArtifact(part_name="leg", instance_names=["leg_01", "leg_02", "leg_03", "leg_04"], status="built"),
            BuildArtifact(part_name="backrest", instance_names=["backrest_01"], status="built"),
        ],
        plan_artifact=plan,
        spec_artifact=spec,
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=ZeroLocationPlaceLLM(),
    )

    assert [item.review_verdict for item in result] == ["approved", "approved", "approved"]
    assert object_ops.get_object_location("seat_01") == [0.0, 0.0, 0.0]
    assert object_ops.get_object_location("leg_01") == [0.2, 0.2, -0.415]
    assert object_ops.get_object_location("leg_02") == [-0.2, 0.2, -0.415]
    assert object_ops.get_object_location("leg_03") == [-0.2, -0.2, -0.415]
    assert object_ops.get_object_location("leg_04") == [0.2, -0.2, -0.415]
    assert object_ops.get_object_location("backrest_01") == [0.0, 0.265, 0.315]


def test_assemble_phase_falls_back_to_python_plan_for_missing_builder_intent(tmp_path):
    class MissingPlaceIntentLLM:
        def call(self, **kwargs):
            return "The builder placement tool is unavailable, so no Markdown intent was produced."

    context = {
        "runtime_root": str(tmp_path),
        "session_id": "builder-place-fallback",
        "agent_orchestrator": {"conversation_id": "ao-1"},
    }
    plan = PlanArtifact(
        build_responsibilities=[{"family": "seat"}],
        assembly_responsibilities=[{"family": "seat", "placement_rule": "place_at_world_position"}],
        steps=[{"family": "seat", "world_position": [1.0, 2.0, 3.0], "world_rotation": [0.0, 0.0, 0.0], "step_index": 0}],
    )
    object_ops = SimulatedBlenderObjectOps()
    object_ops.create_primitive("cube", "seat_01")

    result = AssemblePhase().run(
        build_artifacts=[BuildArtifact(part_name="seat", instance_names=["seat_01"], status="built")],
        plan_artifact=plan,
        spec_artifact=SpecArtifact(parts={"seat": {"primitive": "cube"}}),
        context=context,
        object_ops=object_ops,
        executor=ActionExecutor(object_ops),
        llm=MissingPlaceIntentLLM(),
    )

    assert result[0].review_verdict == "approved"
    assert object_ops.get_object_location("seat_01") == [1.0, 2.0, 3.0]
    assert "fallback" in result[0].planning_warnings[0].lower()
    artifact_root = tmp_path / "session_data" / "builder-place-fallback" / "artifacts"
    assert "Python fallback" in (artifact_root / "build_log.md").read_text(encoding="utf-8")


def test_build_extraction_normalization_fills_missing_instances_from_normalized_item():
    plan = AgentActionPlan(
        status="ready",
        parts=[
            {
                "part_name": "leg",
                "source_object_name": "leg_source",
                "instance_names": ["leg_01"],
                "actions": [
                    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "leg_source"}},
                    {"action_type": "duplicate_object", "parameters": {"name": "leg_source", "new_name": "leg_01"}},
                    {"action_type": "delete_object", "parameters": {"name": "leg_source"}},
                ],
            }
        ],
    )

    _normalize_extracted_build_instances(plan, "leg", {"instance_count": 4})

    part = plan.parts[0]
    assert part["instance_names"] == ["leg_01", "leg_02", "leg_03", "leg_04"]
    duplicate_names = [
        action["parameters"]["new_name"]
        for action in part["actions"]
        if action["action_type"] == "duplicate_object"
    ]
    assert duplicate_names == ["leg_01", "leg_02", "leg_03", "leg_04"]
    assert part["actions"][-1]["action_type"] == "delete_object"


def test_programmatic_validator_skips_dimension_check_for_incomplete_bbox():
    object_ops = SimulatedBlenderObjectOps()
    object_ops.create_primitive("cube", "seat_01")
    result = ProgrammaticValidator().validate(
        SpecArtifact(parts={"seat": {"primitive": "cube", "target_bbox": {}}}),
        [BuildArtifact(part_name="seat", instance_names=["seat_01"], status="built")],
        [],
        object_ops,
    )

    assert result.passed is True
    assert not any(item.get("check") == "dimensions" for item in result.comparisons)
    assert any("target_bbox is incomplete" in warning for warning in result.warnings)


def test_assembly_extraction_normalization_uses_normalized_per_instance_positions():
    plan = AgentActionPlan(
        status="ready",
        steps=[
            {
                "step_index": 0,
                "actions": [
                    {"action_type": "move_object", "parameters": {"name": "leg_01", "location": [0.0, 0.0, 0.0]}}
                ],
            }
        ],
    )
    build = BuildArtifact(part_name="leg", instance_names=["leg_01", "leg_02", "leg_03", "leg_04"], status="built")

    _normalize_extracted_assembly_steps(
        plan,
        "leg",
        {
            "step_index": 1,
            "instance_world_positions": [
                [0.2, 0.2, -0.4],
                [-0.2, 0.2, -0.4],
                [-0.2, -0.2, -0.4],
                [0.2, -0.2, -0.4],
            ],
            "world_rotation": [0.0, 0.0, 0.0],
        },
        build,
    )

    moves = [action for action in plan.steps[0]["actions"] if action["action_type"] == "move_object"]
    assert [move["parameters"]["name"] for move in moves] == ["leg_01", "leg_02", "leg_03", "leg_04"]
    assert moves[1]["parameters"]["location"] == [-0.2, 0.2, -0.4]
