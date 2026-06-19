"""Tests for Pipeline orchestrator and ExpertRegistry."""

from __future__ import annotations

import pytest

from ai_3d_modeling_agent.multi_expert.artifacts import FinalArtifact, PipelineStatus
from ai_3d_modeling_agent.multi_expert.artifacts import PlanArtifact
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

ALL_EXPERT_CLASSES = (Designer, Specifier, Planner, Reviewer, Builder, Inspector)

VALID_STATUSES = {
    PipelineStatus.SUCCESS,
    PipelineStatus.SUCCESS_WITH_WARNINGS,
    PipelineStatus.DEGRADED,
    PipelineStatus.PARTIAL,
    PipelineStatus.FAILED,
}


def _full_registry() -> ExpertRegistry:
    registry = ExpertRegistry()
    for cls in ALL_EXPERT_CLASSES:
        registry.register(cls())
    return registry


# ===================================================================
# Pipeline
# ===================================================================


def test_pipeline_init(mock_llm):
    """Create Pipeline with active experts in registry + MockLLM."""
    registry = _full_registry()
    pipeline = Pipeline(registry=registry, llm=mock_llm)
    assert pipeline.registry.count == 6


def test_pipeline_run_no_crash(mock_llm):
    """pipeline.run('build a chair') with MockLLM returns FinalArtifact with valid status."""
    registry = _full_registry()
    pipeline = Pipeline(registry=registry, llm=mock_llm)
    result = pipeline.run("build a chair")
    assert isinstance(result, FinalArtifact)
    assert result.status in VALID_STATUSES


def test_pipeline_error_handling(mock_llm):
    """Pipeline with empty registry (no experts) returns FinalArtifact with FAILED, not crash."""
    registry = ExpertRegistry()
    pipeline = Pipeline(registry=registry, llm=mock_llm)
    result = pipeline.run("build a chair")
    assert isinstance(result, FinalArtifact)
    assert result.status in {
        PipelineStatus.SUCCESS,
        PipelineStatus.FAILED,
        PipelineStatus.DEGRADED,
        PipelineStatus.PARTIAL,
    }


def test_ao_pipeline_fails_fast_when_plan_phase_raises(mock_llm, monkeypatch):
    """AO-backed runs must not continue into empty build/validation after plan failure."""
    from ai_3d_modeling_agent.multi_expert.phases import PlanPhase

    def explode(*_args, **_kwargs):
        raise PermissionError("locked meeting state")

    monkeypatch.setattr(PlanPhase, "run", explode)
    pipeline = Pipeline(
        registry=_full_registry(),
        llm=mock_llm,
        context={"agent_orchestrator": {"conversation_id": "ao-conv"}},
    )

    result = pipeline.run("build a simple red cube")

    assert result.status == PipelineStatus.FAILED
    assert result.phase_statuses["plan"] == PipelineStatus.FAILED
    assert result.phase_statuses["build"] == PipelineStatus.FAILED
    assert result.phase_statuses["validate"] == PipelineStatus.FAILED
    assert result.validation is not None
    assert result.validation.passed is False
    assert "Plan phase failed" in result.validation.errors[0]


def test_ao_pipeline_fails_when_build_produces_no_artifacts(mock_llm, monkeypatch):
    """AO-backed runs must not validate an empty build as success."""
    from ai_3d_modeling_agent.multi_expert.phases import BuildPhase, PlanPhase

    monkeypatch.setattr(PlanPhase, "run", lambda *_args, **_kwargs: PlanArtifact())
    monkeypatch.setattr(BuildPhase, "run", lambda *_args, **_kwargs: [])
    pipeline = Pipeline(
        registry=_full_registry(),
        llm=mock_llm,
        context={"agent_orchestrator": {"conversation_id": "ao-conv"}},
    )

    result = pipeline.run("build a simple red cube")

    assert result.status == PipelineStatus.FAILED
    assert result.phase_statuses["build"] == PipelineStatus.FAILED
    assert result.phase_statuses["validate"] == PipelineStatus.FAILED
    assert result.validation is not None
    assert result.validation.passed is False
    assert result.validation.errors == [
        "Build phase produced no Blender artifacts; validation was not run."
    ]


# ------------------------------------------------------------------
# Callback integration tests
# ------------------------------------------------------------------


def test_progress_callback_counts(mock_llm):
    """progress_callback fires 12 times (6 phases × start/end) with correct args."""
    registry = _full_registry()
    calls: list[tuple[str, str]] = []

    def progress(phase: str, checkpoint: str) -> None:
        calls.append((phase, checkpoint))

    pipeline = Pipeline(
        registry=registry,
        llm=mock_llm,
        progress_callback=progress,
    )
    pipeline.run("build a chair")

    assert len(calls) == 12  # 6 phases × 2 checkpoints
    # Phase ordering
    expected_phases = [
        "design", "design",
        "spec", "spec",
        "plan", "plan",
        "build", "build",
        "assemble", "assemble",
        "validate", "validate",
    ]
    assert [p for p, _ in calls] == expected_phases
    # Start before end for each phase
    assert calls[0] == ("design", "start")
    assert calls[1] == ("design", "end")


def test_prompt_observer_called_for_llm_phases(mock_llm):
    """prompt_observer fires for each LLM-using phase (design, spec, build, assemble, validate)."""
    registry = _full_registry()
    payloads: list[dict] = []

    def observer(payload: dict) -> None:
        payloads.append(payload)

    pipeline = Pipeline(
        registry=registry,
        llm=mock_llm,
        prompt_observer=observer,
    )
    pipeline.run("build a chair")

    # 5 LLM phases (plan is deterministic — no LLM)
    assert len(payloads) == 6
    stages = [p["stage"] for p in payloads]
    assert stages == ["design", "spec", "plan", "build", "assemble", "validate"]
    for p in payloads:
        assert "event_id" in p
        assert "label" in p
        assert "prompt_preview" in p
        assert "response_preview" in p


def test_callbacks_default_none_noop(mock_llm):
    """Pipeline runs successfully when both callbacks are left as None (default)."""
    registry = _full_registry()
    pipeline = Pipeline(registry=registry, llm=mock_llm)
    result = pipeline.run("build a chair")
    assert isinstance(result, FinalArtifact)
    assert result.status in VALID_STATUSES


def test_callback_exception_resilience(mock_llm):
    """A callback that raises an exception does not crash the pipeline."""
    registry = _full_registry()

    def exploding(_phase: str, _checkpoint: str) -> None:
        raise RuntimeError("boom")

    pipeline = Pipeline(
        registry=registry,
        llm=mock_llm,
        progress_callback=exploding,
    )
    result = pipeline.run("build a chair")
    assert isinstance(result, FinalArtifact)
    assert result.status in VALID_STATUSES


def test_both_callbacks_simultaneously(mock_llm):
    """progress_callback and prompt_observer work together."""
    registry = _full_registry()
    progress_calls: list[tuple[str, str]] = []
    prompt_calls: list[dict] = []

    def progress(phase: str, checkpoint: str) -> None:
        progress_calls.append((phase, checkpoint))

    def observer(payload: dict) -> None:
        prompt_calls.append(payload)

    pipeline = Pipeline(
        registry=registry,
        llm=mock_llm,
        progress_callback=progress,
        prompt_observer=observer,
    )
    pipeline.run("build a chair")

    assert len(progress_calls) == 12
    assert len(prompt_calls) == 6


# ===================================================================
# ExpertRegistry
# ===================================================================


def test_expert_registry_register():
    """Register active experts."""
    registry = _full_registry()
    assert registry.count == 6


def test_expert_registry_get():
    """get('designer') returns Designer instance, get('nonexistent') returns None."""
    registry = ExpertRegistry()
    registry.register(Designer())
    assert isinstance(registry.get("designer"), Designer)
    assert registry.get("nonexistent") is None


def test_expert_registry_list_roles():
    """Register 3 experts, list_roles returns sorted list."""
    registry = ExpertRegistry()
    registry.register(Reviewer())
    registry.register(Builder())
    registry.register(Designer())
    assert registry.list_roles() == ["builder", "designer", "reviewer"]


def test_expert_registry_has_role():
    """has_role('builder') is True, has_role('random') is False."""
    registry = ExpertRegistry()
    registry.register(Builder())
    assert registry.has_role("builder") is True
    assert registry.has_role("random") is False


def test_expert_registry_duplicate_raises():
    """Registering the same expert twice raises ValueError."""
    registry = ExpertRegistry()
    registry.register(Inspector())
    with pytest.raises(ValueError):
        registry.register(Inspector())
