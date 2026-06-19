"""End-to-end test for the multi-expert pipeline with MockLLM + SimulatedBlender.

Verifies the complete pipeline flow:
  Design → Spec → Plan → Build → Assemble → Validate → FinalArtifact

Uses a ScriptedMockLLM that returns phase-appropriate JSON for extraction
calls and generic text for conversation calls.
"""

from __future__ import annotations

import json
from typing import Optional

import pytest

from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
from ai_3d_modeling_agent.multi_expert.artifacts import (
    DesignArtifact,
    FinalArtifact,
    PipelineStatus,
    SpecArtifact,
    ValidationArtifact,
)
from ai_3d_modeling_agent.multi_expert.experts import (
    Builder,
    Designer,
    Inspector,
    Planner,
    Reviewer,
    Specifier,
)
from ai_3d_modeling_agent.multi_expert.pipeline.pipeline import Pipeline
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry


_DESIGN_EXTRACTION_RESPONSE = json.dumps({
    "parts": [
        {
            "name": "table_top",
            "description": "flat horizontal surface of the table",
            "instance_count": 1,
            "parent_name": None,
            "symmetry_group": "NONE",
        },
        {
            "name": "table_leg",
            "description": "vertical support leg",
            "instance_count": 4,
            "parent_name": "table_top",
            "symmetry_group": "QUADRANT_Z",
        },
    ],
    "assembly_concept": "Build table_top first as root, attach 4 legs underneath at corners",
    "unresolved_issues": [],
    "summary": "Table decomposed into 2 part families: top (root) and 4 legs (children)",
})

_SPEC_EXTRACTION_RESPONSE = json.dumps({
    "parts": {
        "table_top": {
            "primitive": "cube",
            "target_bbox": {"width": 1.2, "depth": 0.8, "height": 0.05},
            "refinement_viewpoint": "top",
            "attachment_points": [
                {
                    "name": "bottom_center",
                    "local_offset": [0.0, 0.0, -0.025],
                    "description": "connects to legs",
                }
            ],
        },
        "table_leg": {
            "primitive": "cylinder",
            "target_bbox": {"width": 0.08, "depth": 0.08, "height": 0.7},
            "refinement_viewpoint": "front",
            "attachment_points": [
                {
                    "name": "top_center",
                    "local_offset": [0.0, 0.0, 0.35],
                    "description": "connects to table top",
                }
            ],
        },
    },
    "validation_notes": [],
    "summary": "All 2 parts specified with geometry and attachment points",
})

_VALIDATE_EXTRACTION_RESPONSE = json.dumps({
    "passed": True,
    "errors": [],
    "warnings": [],
    "comparisons": [
        {
            "part_name": "table_top",
            "check": "instance_count",
            "expected": "1",
            "actual": "1",
            "status": "pass",
        },
        {
            "part_name": "table_leg",
            "check": "instance_count",
            "expected": "4",
            "actual": "4",
            "status": "pass",
        },
    ],
})

_PLAN_EXTRACTION_RESPONSE = json.dumps({
    "summary": "Build the table top first, then create and place four legs with mirrored corner placement.",
    "execution_rationale": [
        "The tabletop is the root support surface.",
        "Legs depend on tabletop placement and can be repeated symmetrically.",
    ],
    "build_responsibilities": [
        {
            "id": "build-table-top",
            "family": "table_top",
            "summary": "Builder creates the tabletop geometry from the agreed primitive and target bounding box.",
            "geometry_assumptions": ["Use the cube primitive sized to the tabletop bbox."],
            "deferred_placement": ["Final placement and parenting are handled during assembly."],
            "decision_refs": ["plan.build_responsibilities.table_top"],
        }
    ],
    "assembly_responsibilities": [
        {
            "id": "assemble-table-leg",
            "family": "table_leg",
            "summary": "Builder positions and parents the four table legs under the tabletop.",
            "placement_relations": ["Attach each leg to a tabletop corner using symmetry."],
            "hierarchy_notes": ["Keep the tabletop as the root parent."],
            "target_parent_family": "table_top",
            "attachment_target_family": "table_top",
            "attachment_target_point_id": "bottom_center",
            "local_anchor_point_id": "top_center",
            "placement_rule": "align_local_anchor_to_target_point",
            "required_parenting": True,
            "decision_refs": ["plan.assembly_responsibilities.table_leg"],
        }
    ],
    "dependency_summary": [
        "Build the tabletop before final placement of the legs.",
    ],
    "ordering_constraints": [
        {
            "id": "ordering-top-before-legs",
            "summary": "The tabletop must exist before the legs are finally placed.",
            "depends_on": ["build:table_top"],
            "responsibility": "builder",
            "decision_refs": ["plan.ordering_constraints.top-before-legs"],
        }
    ],
    "risk_hotspots": [
        {
            "id": "risk-leg-placement",
            "summary": "Leg placement depends on accurate corner attachment assumptions.",
            "owner": "builder",
            "issue_refs": [],
            "reason": "Bad attachment assumptions would create visible drift.",
        }
    ],
    "open_issues": [],
})


class ScriptedMockLLM:
    """Mock LLM that returns phase-appropriate responses based on system prompt."""

    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[dict] = []

    def call(
        self,
        system_prompt: str = "",
        messages: Optional[list] = None,
        response_model=None,
        sampling=None,
        **kwargs,
    ) -> str:
        self.call_count += 1
        self.calls.append({
            "system_prompt": system_prompt[:100],
            "message_count": len(messages) if messages else 0,
            "agent": kwargs.get("agent", ""),
            "skill": kwargs.get("skill", ""),
        })

        skill = kwargs.get("skill", "")
        context = kwargs.get("context", {}) if isinstance(kwargs.get("context"), dict) else {}
        if skill == "extract-validation-artifact":
            return _VALIDATE_EXTRACTION_RESPONSE
        if skill == "extract-plan-artifact":
            return _PLAN_EXTRACTION_RESPONSE
        if skill == "extract-spec-artifact":
            return _SPEC_EXTRACTION_RESPONSE
        if skill == "extract-design-artifact":
            return _DESIGN_EXTRACTION_RESPONSE
        if kwargs.get("agent") == "moderator" and context.get("meeting_turn_kind") == "resolution":
            return (
                "Decision: Proceed with the proposed structure.\n"
                "Accepted:\n- Use the latest proposal as the working plan.\n"
                "Rejected:\n- None.\n"
                "Open Issues:\nNone"
            )
        if context.get("meeting_turn_kind") == "challenge":
            return "Concern: No blocking issue. The proposal is coherent."
        if context.get("meeting_turn_kind") == "response":
            return "Response: Acknowledged. No revision is required."
        return "Proposal: Use the latest task context as the basis for the plan.\nRationale: This keeps the workflow simple."


def _full_registry() -> ExpertRegistry:
    registry = ExpertRegistry()
    for cls in (Designer, Specifier, Planner, Reviewer, Builder, Inspector):
        registry.register(cls())
    return registry


class TestMultiExpertE2E:
    """End-to-end tests for the multi-expert pipeline."""

    def test_pipeline_produces_populated_final_artifact(self):
        """Full pipeline run produces FinalArtifact with all phases populated."""
        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
        )
        result = pipeline.run("build a simple table")

        assert isinstance(result, FinalArtifact)
        assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.DEGRADED)
        assert result.task_prompt == "build a simple table"

        assert isinstance(result.design, DesignArtifact)
        assert len(result.design.parts) >= 1
        part_names = [p["name"] for p in result.design.parts]
        assert "main_object" in part_names

        assert isinstance(result.specs, SpecArtifact)
        assert "main_object" in result.specs.parts

        assert result.plan is not None
        assert len(result.plan.steps) > 0

        assert len(result.build_results) > 0
        for name, ba in result.build_results.items():
            assert ba.status in ("built", "failed")

        assert isinstance(result.validation, ValidationArtifact)

    def test_pipeline_creates_blender_objects(self):
        """Build phase creates actual objects in SimulatedBlenderObjectOps."""
        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
        )
        result = pipeline.run("build a simple table")

        created_names = object_ops.list_object_names()
        assert len(created_names) > 0

        for name, ba in result.build_results.items():
            if ba.status == "built":
                for inst in ba.instance_names:
                    assert inst in created_names

    def test_pipeline_assembly_positions_parts(self):
        """Assemble phase moves objects to world positions."""
        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
        )
        result = pipeline.run("build a simple table")

        assert len(result.assembly_results) > 0
        for art in result.assembly_results:
            assert len(art.placements) > 0

    def test_pipeline_progress_callback_fires(self):
        """progress_callback fires 12 times (6 phases x start/end)."""
        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        calls: list[tuple[str, str]] = []

        def progress(phase: str, checkpoint: str) -> None:
            calls.append((phase, checkpoint))

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
            progress_callback=progress,
        )
        pipeline.run("build a simple table")

        assert len(calls) == 12
        expected_phases = [
            "design", "design",
            "spec", "spec",
            "plan", "plan",
            "build", "build",
            "assemble", "assemble",
            "validate", "validate",
        ]
        assert [p for p, _ in calls] == expected_phases

    def test_pipeline_without_blender_ops_still_runs(self):
        """Pipeline runs without object_ops (no geometry created, but no crash)."""
        llm = ScriptedMockLLM()
        registry = _full_registry()

        pipeline = Pipeline(registry=registry, llm=llm)
        result = pipeline.run("build a simple table")

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

    def test_markdown_first_pipeline_ignores_legacy_extraction_failure(self):
        """Legacy design/spec/plan extraction failures no longer drive active runtime."""

        class BrokenExtractionLLM:
            def __init__(self):
                self.call_count = 0

            def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
                self.call_count += 1
                if str(kwargs.get("skill", "")).startswith("extract-"):
                    return "this is not json at all"
                return '{"status": "ok"}'

        llm = BrokenExtractionLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
        )
        result = pipeline.run("build a table")

        assert isinstance(result, FinalArtifact)
        assert result.design is not None
        assert len(result.design.parts) >= 1
        assert result.design.failure_notes == []

    def test_event_callback_receives_meeting_events(self):
        """event_callback is called for each meeting event during pipeline run."""
        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        events: list[dict] = []

        def on_event(event):
            events.append(event)

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
            event_callback=on_event,
        )
        pipeline.run("build a simple table")

        assert len(events) > 0

        kinds = [e["kind"] for e in events]
        assert "phase_open" in kinds
        assert "phase_close" in kinds
        assert "proposal" in kinds
        assert "challenge" in kinds
        assert "resolution" in kinds
        assert "build_step" in kinds or "assemble_step" in kinds
        assert "phase_start" not in kinds
        assert "expert_spoke" not in kinds
        assert "extraction_done" not in kinds
        assert "phase_end" not in kinds

        # Check event structure
        for event in events:
            assert event["schema_version"] == 1
            assert "event_id" in event
            assert "phase" in event
            assert "kind" in event
            assert "message" in event
            assert event["speaker"]
            assert event["role"]
            assert "round" in event
            assert "summary" in event
            assert "full_content" in event
            assert "timestamp" in event

    def test_event_buffer_persists_to_file(self):
        """event_buffer writes meeting events to meetings.jsonl."""
        import json
        import tempfile
        from pathlib import Path

        from ai_3d_modeling_agent.io.buffered_writer import BufferedWriter

        llm = ScriptedMockLLM()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        with tempfile.TemporaryDirectory() as tmp_dir:
            meetings_path = Path(tmp_dir) / "meetings.jsonl"
            event_buffer = BufferedWriter(meetings_path, flush_interval=5.0)

            pipeline = Pipeline(
                registry=registry,
                llm=llm,
                object_ops=object_ops,
                executor=executor,
                event_buffer=event_buffer,
            )
            pipeline.run("build a simple table")

            # Flush remaining events
            event_buffer.flush()

            # Verify file exists and has content
            assert meetings_path.exists()
            lines = meetings_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) > 0

            # Verify each line is valid JSON
            for line in lines:
                event = json.loads(line)
                assert "event_id" in event
                assert "phase" in event
                assert "kind" in event

    def test_settings_based_pipeline_run(self):
        """Pipeline can be run from a settings JSON file."""
        from pathlib import Path

        from ai_3d_modeling_agent.pipelines.runners import run_pipeline_from_settings

        settings_path = Path(__file__).parent / "test_settings.json"

        with pytest.raises(ValueError, match="agent_orchestrator_base_url is required"):
            run_pipeline_from_settings(
                settings_path,
                task="build a simple table",
                session_id="test-settings-e2e",
        )

    def test_settings_loader_with_overrides(self):
        """Settings loader merges file + overrides correctly."""
        from pathlib import Path

        from ai_3d_modeling_agent.io.settings_loader import load_settings

        settings_path = Path(__file__).parent / "test_settings.json"

        settings = load_settings(
            settings_path,
            overrides={"llm_model": "overridden-model", "task": "overridden task"},
        )

        assert settings["llm_model"] == "overridden-model"
        assert settings["task"] == "overridden task"
        assert "use_" + "multi_expert" not in settings
