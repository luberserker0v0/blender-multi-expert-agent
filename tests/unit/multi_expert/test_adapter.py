"""Tests for final_artifact_to_snapshot adapter.

Covers all PipelineStatus variants, None-field gracefulness, and
every mapped sub-structure (part_tasks, assembly, final_validation).
"""

from __future__ import annotations

import pytest

from ai_3d_modeling_agent.multi_expert.artifacts.assembly import AssemblyArtifact
from ai_3d_modeling_agent.multi_expert.artifacts.build import BuildArtifact
from ai_3d_modeling_agent.multi_expert.artifacts.final import (
    FinalArtifact,
    PipelineStatus,
)
from ai_3d_modeling_agent.multi_expert.artifacts.validation import ValidationArtifact
from ai_3d_modeling_agent.multi_expert.pipeline.adapter import (
    final_artifact_to_snapshot,
)


class TestPipelineStatusMapping:
    """Verify that each PipelineStatus maps to the correct snapshot strings."""

    def test_success(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "completed"
        assert snap.stage == "completed"
        assert snap.stage_status == "completed"

    def test_success_with_warnings(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS_WITH_WARNINGS,
            phase_statuses={"validation": PipelineStatus.SUCCESS_WITH_WARNINGS},
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "completed"  # overall is still completed
        assert snap.stage == "completed"
        assert snap.stage_status == "completed_with_warnings"

    def test_degraded(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.DEGRADED,
            degraded_parts=["leg"],
            phase_statuses={"build": PipelineStatus.DEGRADED},
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "degraded"
        assert snap.stage == "completed"
        assert snap.stage_status == "degraded"

    def test_partial(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.PARTIAL,
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "partial"
        assert snap.stage == "completed"
        assert snap.stage_status == "partial"

    def test_failed(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.FAILED,
            phase_statuses={
                "design": PipelineStatus.SUCCESS,
                "specs": PipelineStatus.FAILED,
            },
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "failed"
        assert snap.stage == "specs"
        assert snap.stage_status == "failed"

    def test_failed_without_explicit_phase(self):
        """FAILED with no phase_statuses → fallback stage 'unknown'."""
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.FAILED,
            phase_statuses={},
        )
        snap = final_artifact_to_snapshot(artifact, "test task", "s1")
        assert snap.status == "failed"
        assert snap.stage == "unknown"
        assert snap.stage_status == "failed"


class TestBuildResultsMapping:
    """Verify build_results → part_tasks conversion."""

    def test_built_part_creates_task(self):
        artifact = FinalArtifact(
            task_prompt="build a chair",
            status=PipelineStatus.SUCCESS,
            build_results={
                "leg": BuildArtifact(
                    part_name="leg",
                    source_object_name="LegObject",
                    status="built",
                    capture_paths=["round1.png"],
                    refinement_rounds=1,
                    action_history=[
                        {"action_type": "create_cylinder", "parameters": {"radius": 0.1}}
                    ],
                ),
            },
        )
        snap = final_artifact_to_snapshot(artifact, "build a chair", "s1")
        assert len(snap.part_tasks) == 1
        pt = snap.part_tasks[0]
        assert pt.task_id == "leg"
        assert pt.title == "leg"
        assert pt.object_name == "LegObject"
        assert pt.status == "approved"
        assert pt.approved is True
        assert snap.active_task_id == "s1"
        assert "leg" in snap.completed_task_ids

    def test_multiple_parts(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            build_results={
                "leg": BuildArtifact(part_name="leg", status="built", refinement_rounds=0),
                "seat": BuildArtifact(part_name="seat", status="built", refinement_rounds=0),
                "back": BuildArtifact(part_name="back", status="failed"),
            },
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert len(snap.part_tasks) == 3
        statuses = {pt.task_id: pt.status for pt in snap.part_tasks}
        assert statuses["leg"] == "approved"
        assert statuses["seat"] == "approved"
        assert statuses["back"] == "failed"

    def test_empty_build_results(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            build_results={},
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.part_tasks == []

    def test_rounds_populated(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            build_results={
                "leg": BuildArtifact(
                    part_name="leg",
                    status="built",
                    refinement_rounds=2,
                    capture_paths=["r1.png", "r2.png"],
                    action_history=[
                        {"action_type": "resize", "parameters": {"scale": 0.5}},
                        {"action_type": "move", "parameters": {"x": 1.0}},
                    ],
                ),
            },
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        pt = snap.part_tasks[0]
        assert len(pt.rounds) == 2
        assert pt.rounds[0].round_index == 0
        assert pt.rounds[0].capture_path == "r1.png"
        assert pt.rounds[0].requested_action is not None
        assert pt.rounds[0].requested_action.action_type == "resize"
        assert pt.rounds[1].round_index == 1
        assert pt.rounds[1].capture_path == "r2.png"
        assert pt.rounds[1].requested_action.action_type == "move"


class TestAssemblyMapping:
    """Verify assembly_results → assembly conversion."""

    def test_empty_assembly(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            assembly_results=[],
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.assembly.status == "pending"
        assert snap.assembly.rounds == []
        assert snap.assembly.approved is False

    def test_single_assembly_round(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            assembly_results=[
                AssemblyArtifact(
                    step_index=0,
                    placements=[{"part": "leg", "position": [0, 0, 0]}],
                ),
            ],
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert len(snap.assembly.rounds) == 1
        assert snap.assembly.rounds[0].assembly_step_index == 0
        assert snap.assembly.rounds[0].round_index == 0

    def test_multiple_assembly_rounds(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            assembly_results=[
                AssemblyArtifact(step_index=0),
                AssemblyArtifact(step_index=1, review_verdict="approved"),
            ],
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert len(snap.assembly.rounds) == 2
        assert snap.assembly.rounds[0].assembly_step_index == 0
        assert snap.assembly.rounds[1].assembly_step_index == 1

    def test_assembly_review_not_approved(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            assembly_results=[
                AssemblyArtifact(
                    step_index=0, review_verdict="needs_adjustment"
                ),
            ],
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.assembly.approved is False
        assert snap.assembly.status == "pending"


class TestValidationMapping:
    """Verify validation → final_validation conversion."""

    def test_passed_validation(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            validation=ValidationArtifact(passed=True, errors=[], warnings=[]),
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.final_validation.status == "completed"
        assert snap.final_validation.missing_critical_parts == []

    def test_failed_validation(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.DEGRADED,
            validation=ValidationArtifact(
                passed=False,
                errors=["Missing backrest", "Wrong proportions"],
            ),
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.final_validation.status == "failed"
        assert "Missing backrest" in snap.final_validation.missing_critical_parts
        assert "Wrong proportions" in snap.final_validation.missing_critical_parts

    def test_none_validation(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
            validation=None,
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.final_validation.status == "pending"
        assert snap.final_validation.detected_parts == []
        assert snap.final_validation.missing_critical_parts == []


class TestNoneFieldsGraceful:
    """Verify adapter handles None/missing optional fields without error."""

    def test_default_artifact(self):
        """A bare-minimum FinalArtifact with all defaults should not crash."""
        artifact = FinalArtifact()
        snap = final_artifact_to_snapshot(
            artifact, "default test", "default-session"
        )
        assert snap.workflow_type == "multi_stage_modeling"
        assert snap.task == "default test"
        assert snap.part_tasks == []
        assert snap.assembly.status == "pending"
        assert snap.final_validation.status == "pending"

    def test_no_phase_statuses(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.FAILED,
            phase_statuses={},
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        # Should fall back gracefully
        assert snap.stage == "unknown"
        assert snap.stage_status == "failed"

    def test_empty_session_id(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
        )
        snap = final_artifact_to_snapshot(artifact, "test", "")
        assert snap.active_task_id == ""


class TestRequestAndPlanDefaults:
    """Verify request and plan fields have sensible defaults."""

    def test_request_has_task_prompt(self):
        artifact = FinalArtifact(
            task_prompt="internal prompt",
            status=PipelineStatus.SUCCESS,
        )
        snap = final_artifact_to_snapshot(artifact, "external prompt", "s1")
        assert snap.request.task_prompt == "external prompt"

    def test_plan_is_none(self):
        artifact = FinalArtifact(
            task_prompt="test",
            status=PipelineStatus.SUCCESS,
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.plan is None


class TestStopReason:
    """Verify stop_reason is derived correctly from artifact status."""

    def test_success_stop_reason(self):
        artifact = FinalArtifact(status=PipelineStatus.SUCCESS)
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.stop_reason == ""

    def test_failed_stop_reason(self):
        artifact = FinalArtifact(status=PipelineStatus.FAILED)
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert "FAILED" in snap.stop_reason

    def test_failed_stop_reason_prefers_validation_detail(self):
        artifact = FinalArtifact(
            status=PipelineStatus.FAILED,
            validation=ValidationArtifact(
                passed=False,
                errors=["Coverage gap for cube: spec_geometry_defined (missing geometry spec)."],
            ),
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert snap.stop_reason == "Pipeline failed: Coverage gap for cube: spec_geometry_defined (missing geometry spec)."

    def test_degraded_stop_reason(self):
        artifact = FinalArtifact(
            status=PipelineStatus.DEGRADED,
            degraded_parts=["leg", "seat"],
        )
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert "leg" in snap.stop_reason
        assert "seat" in snap.stop_reason

    def test_partial_stop_reason(self):
        artifact = FinalArtifact(status=PipelineStatus.PARTIAL)
        snap = final_artifact_to_snapshot(artifact, "test", "s1")
        assert "partial" in snap.stop_reason.lower()
