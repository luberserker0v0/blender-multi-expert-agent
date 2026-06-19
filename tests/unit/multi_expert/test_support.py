"""Tests for pipeline support systems: ScopeEngine, Rejection, PipelineCheckpoint, Adapter."""

import pytest

from ai_3d_modeling_agent.multi_expert.artifacts.final import (
    FinalArtifact,
    PipelineStatus,
)
from ai_3d_modeling_agent.multi_expert.artifacts.design import DesignArtifact
from ai_3d_modeling_agent.multi_expert.pipeline.adapter import final_artifact_to_snapshot
from ai_3d_modeling_agent.multi_expert.pipeline.checkpoint import PipelineCheckpoint
from ai_3d_modeling_agent.multi_expert.pipeline.rejection import (
    CorrectionRequest,
    CorrectionResponse,
    Rejection,
    RejectionReason,
)
from ai_3d_modeling_agent.multi_expert.pipeline.scope_engine import ScopeEngine


# ===================================================================
# ScopeEngine
# ===================================================================


class TestScopeEngine:
    """Verify ScopeEngine impact computation and cascade ordering."""

    def test_design_impact_all_phases(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("design", {})
        assert impacted == ["design", "spec", "plan", "build", "assemble", "validate"]

    def test_spec_impact(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("spec", {})
        assert impacted == ["spec", "plan", "build", "assemble", "validate"]

    def test_plan_impact(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("plan", {})
        assert impacted == ["plan", "build", "assemble", "validate"]

    def test_build_impact(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("build", {})
        assert impacted == ["build", "assemble", "validate"]

    def test_assembly_impact(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("assembly", {})
        assert impacted == ["assemble", "validate"]

    def test_validation_impact(self):
        engine = ScopeEngine()
        impacted = engine.compute_impact("validation", {})
        assert impacted == ["validate"]

    def test_unknown_type_returns_empty(self):
        engine = ScopeEngine()
        assert engine.compute_impact("unknown", {}) == []

    def test_cascade_strategy_topological_order(self):
        engine = ScopeEngine()
        impacted = ["validate", "build", "spec"]
        ordered = engine.cascade_strategy(impacted)
        assert ordered == ["spec", "build", "validate"]

    def test_cascade_strategy_all_phases(self):
        engine = ScopeEngine()
        impacted = ["build", "design", "validate", "plan", "spec", "assemble"]
        ordered = engine.cascade_strategy(impacted)
        assert ordered == ["design", "spec", "plan", "build", "assemble", "validate"]

    def test_cascade_strategy_empty(self):
        engine = ScopeEngine()
        assert engine.cascade_strategy([]) == []

    def test_cascade_strategy_single_phase(self):
        engine = ScopeEngine()
        assert engine.cascade_strategy(["validate"]) == ["validate"]
        assert engine.cascade_strategy(["design"]) == ["design"]

    def test_cascade_preserves_no_extra_phases(self):
        engine = ScopeEngine()
        # Only phases present in impacted are included
        impacted = ["spec", "assemble"]
        ordered = engine.cascade_strategy(impacted)
        assert ordered == ["spec", "assemble"]
        assert "design" not in ordered
        assert "plan" not in ordered


# ===================================================================
# RejectionReason
# ===================================================================


class TestRejectionReason:
    """Verify RejectionReason enum values."""

    def test_values(self):
        assert RejectionReason.UNSUPPORTED_PRIMITIVE.value == "UNSUPPORTED_PRIMITIVE"
        assert RejectionReason.UNSUPPORTED_OPERATION.value == "UNSUPPORTED_OPERATION"
        assert RejectionReason.UNSUPPORTED_MATERIAL.value == "UNSUPPORTED_MATERIAL"
        assert RejectionReason.INSTANCE_LIMIT_EXCEEDED.value == "INSTANCE_LIMIT_EXCEEDED"
        assert RejectionReason.UNSUPPORTED_TRANSFORM.value == "UNSUPPORTED_TRANSFORM"
        assert RejectionReason.DIMENSION_OUT_OF_RANGE.value == "DIMENSION_OUT_OF_RANGE"
        assert RejectionReason.EXECUTION_FAILURE.value == "EXECUTION_FAILURE"

    def test_all_are_strings(self):
        for reason in RejectionReason:
            assert isinstance(reason.value, str)

    def test_unique_values(self):
        values = [r.value for r in RejectionReason]
        assert len(values) == len(set(values))


# ===================================================================
# Rejection
# ===================================================================


class TestRejection:
    """Verify Rejection dataclass."""

    def test_minimal_rejection(self):
        r = Rejection(reason=RejectionReason.UNSUPPORTED_PRIMITIVE, detail="torus not supported", phase_name="spec")
        assert r.reason == RejectionReason.UNSUPPORTED_PRIMITIVE
        assert r.detail == "torus not supported"
        assert r.phase_name == "spec"
        assert r.artifact_field == ""

    def test_rejection_with_artifact_field(self):
        r = Rejection(
            reason=RejectionReason.DIMENSION_OUT_OF_RANGE,
            detail="width exceeds max",
            phase_name="spec",
            artifact_field="parts.body.target_bbox.width",
        )
        assert r.artifact_field == "parts.body.target_bbox.width"

    def test_rejection_repr(self):
        r = Rejection(reason=RejectionReason.EXECUTION_FAILURE, detail="timeout", phase_name="build")
        s = repr(r)
        assert "EXECUTION_FAILURE" in s or "timeout" in s


# ===================================================================
# CorrectionRequest
# ===================================================================


class TestCorrectionRequest:
    """Verify CorrectionRequest dataclass."""

    def test_minimal_request(self):
        rejection = Rejection(reason=RejectionReason.UNSUPPORTED_PRIMITIVE, detail="torus", phase_name="spec")
        req = CorrectionRequest(rejection=rejection, current_artifact={})
        assert req.rejection.reason == RejectionReason.UNSUPPORTED_PRIMITIVE
        assert req.current_artifact == {}
        assert req.suggested_fix == ""

    def test_with_suggested_fix(self):
        rejection = Rejection(reason=RejectionReason.UNSUPPORTED_PRIMITIVE, detail="torus", phase_name="spec")
        req = CorrectionRequest(rejection=rejection, current_artifact={"primitive": "torus"}, suggested_fix="designer")
        assert req.suggested_fix == "designer"

    def test_fields(self):
        rejection = Rejection(reason=RejectionReason.INSTANCE_LIMIT_EXCEEDED, detail="too many", phase_name="design")
        req = CorrectionRequest(rejection=rejection, current_artifact={"count": 100})
        assert hasattr(req, "rejection")
        assert hasattr(req, "current_artifact")
        assert hasattr(req, "suggested_fix")


# ===================================================================
# CorrectionResponse
# ===================================================================


class TestCorrectionResponse:
    """Verify CorrectionResponse dataclass."""

    def test_minimal_response(self):
        resp = CorrectionResponse(revised_artifact={"primitive": "cube"})
        assert resp.revised_artifact == {"primitive": "cube"}
        assert resp.approved is False
        assert resp.reviewer_notes == ""

    def test_approved_response(self):
        resp = CorrectionResponse(revised_artifact={"primitive": "cube"}, approved=True)
        assert resp.approved is True

    def test_with_notes(self):
        resp = CorrectionResponse(
            revised_artifact={"primitive": "cube"},
            approved=True,
            reviewer_notes="looks good now",
        )
        assert resp.reviewer_notes == "looks good now"

    def test_fields(self):
        resp = CorrectionResponse(revised_artifact={})
        assert hasattr(resp, "revised_artifact")
        assert hasattr(resp, "approved")
        assert hasattr(resp, "reviewer_notes")


# ===================================================================
# PipelineCheckpoint
# ===================================================================


class TestPipelineCheckpoint:
    """Verify PipelineCheckpoint data schema."""

    def test_minimal_checkpoint(self):
        cp = PipelineCheckpoint(session_id="sess-001", task_prompt="build a chair")
        assert cp.session_id == "sess-001"
        assert cp.task_prompt == "build a chair"
        assert cp.phase_statuses == {}
        assert cp.artifacts == {}
        assert cp.revision_count == 0
        assert cp.timestamp == ""

    def test_with_all_fields(self):
        cp = PipelineCheckpoint(
            session_id="sess-002",
            task_prompt="build a table",
            phase_statuses={"design": "completed", "spec": "in_progress"},
            artifacts={"design": {"parts": []}},
            revision_count=2,
            timestamp="2025-01-01T00:00:00",
        )
        assert cp.revision_count == 2
        assert cp.timestamp == "2025-01-01T00:00:00"
        assert cp.artifacts["design"]["parts"] == []

    def test_phase_statuses_mutable(self):
        cp = PipelineCheckpoint(session_id="s-1", task_prompt="t")
        cp.phase_statuses["design"] = "completed"
        assert cp.phase_statuses["design"] == "completed"

    def test_artifacts_mutable(self):
        cp = PipelineCheckpoint(session_id="s-1", task_prompt="t")
        cp.artifacts["spec"] = {"blueprint_id": "b-1"}
        assert cp.artifacts["spec"]["blueprint_id"] == "b-1"


# ===================================================================
# Adapter
# ===================================================================


class TestFinalArtifactToSnapshot:
    """Verify Adapter converts FinalArtifact to MultiStageProgressSnapshot."""

    def test_empty_final_artifact(self):
        artifact = FinalArtifact()
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="build a cube")
        assert snapshot.task == "build a cube"
        assert snapshot.stage_status is not None

    def test_with_task_prompt(self):
        artifact = FinalArtifact()
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="build a chair")
        assert snapshot.task == "build a chair"

    def test_status_mapping_success(self):
        artifact = FinalArtifact(status=PipelineStatus.SUCCESS)
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="test")
        assert snapshot.stage_status == "completed"

    def test_status_mapping_failed(self):
        artifact = FinalArtifact(status=PipelineStatus.FAILED)
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="test")
        assert snapshot.stage_status == "failed"

    def test_status_mapping_degraded(self):
        artifact = FinalArtifact(status=PipelineStatus.DEGRADED)
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="test")
        assert snapshot.stage_status == "degraded"

    def test_status_mapping_partial(self):
        artifact = FinalArtifact(status=PipelineStatus.PARTIAL)
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="test")
        assert snapshot.stage_status == "partial"

    def test_returns_snapshot_type(self):
        from ai_3d_modeling_agent.schemas.session_progress import MultiStageProgressSnapshot

        artifact = FinalArtifact()
        snapshot = final_artifact_to_snapshot(artifact, task_prompt="test")
        assert isinstance(snapshot, MultiStageProgressSnapshot)
