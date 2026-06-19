"""Unit tests for the in-process pipeline runner."""

from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.multi_expert.artifacts import FinalArtifact, PipelineStatus
from ai_3d_modeling_agent.multi_expert.experts import (
    Builder, Designer, Inspector, Planner, Reviewer, Specifier,
)
from ai_3d_modeling_agent.multi_expert.pipeline.pipeline import Pipeline
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry
from ai_3d_modeling_agent.pipelines.runners import run_pipeline


class _MockLLM:
    """Minimal mock LLM for runner tests."""

    def __init__(self):
        self.call_count = 0

    def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
        self.call_count += 1
        skill = kwargs.get("skill", "")
        context = kwargs.get("context", {}) if isinstance(kwargs.get("context"), dict) else {}
        if skill == "extract-validation-artifact":
            return '{"passed": true, "errors": [], "warnings": [], "comparisons": []}'
        if skill == "extract-plan-artifact":
            return '{"summary": "ok", "execution_rationale": [], "open_issues": []}'
        if skill == "extract-spec-artifact":
            return '{"parts": {}, "validation_notes": [], "summary": "ok"}'
        if skill == "extract-design-artifact":
            return '{"parts": [], "assembly_concept": "", "unresolved_issues": [], "summary": "ok"}'
        if kwargs.get("agent") == "moderator" and context.get("meeting_turn_kind") == "resolution":
            return "Decision: Proceed.\nAccepted:\n- Use the proposal.\nRejected:\n- None.\nOpen Issues:\nNone"
        if context.get("meeting_turn_kind") == "challenge":
            return "Concern: No blocking issue."
        if context.get("meeting_turn_kind") == "response":
            return "Response: Acknowledged."
        return "Proposal: Use a simple plan.\nRationale: Keep it straightforward."


def _full_registry() -> ExpertRegistry:
    registry = ExpertRegistry()
    for cls in (Designer, Specifier, Planner, Reviewer, Builder, Inspector):
        registry.register(cls())
    return registry


class TestRunPipeline:
    """Tests for run_pipeline function."""

    def test_run_pipeline_produces_final_artifact(self):
        """run_pipeline produces FinalArtifact."""
        llm = _MockLLM()
        object_ops = SimulatedBlenderObjectOps()

        registry = _full_registry()
        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=__import__('ai_3d_modeling_agent.execution.action_executor', fromlist=['ActionExecutor']).ActionExecutor(object_ops),
        )
        result = pipeline.run("build a simple table")

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

    def test_event_callback_receives_events(self):
        """event_callback is called for each meeting event."""
        llm = _MockLLM()
        object_ops = SimulatedBlenderObjectOps()
        registry = _full_registry()

        events = []
        def on_event(event):
            events.append(event)

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=__import__('ai_3d_modeling_agent.execution.action_executor', fromlist=['ActionExecutor']).ActionExecutor(object_ops),
            event_callback=on_event,
        )
        pipeline.run("build a simple table")

        assert len(events) > 0
        kinds = [e["kind"] for e in events]
        assert "phase_open" in kinds
        assert "phase_close" in kinds

    def test_pipeline_completes_without_crash(self):
        """Pipeline completes all phases without crashing."""
        llm = _MockLLM()
        object_ops = SimulatedBlenderObjectOps()
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=__import__('ai_3d_modeling_agent.execution.action_executor', fromlist=['ActionExecutor']).ActionExecutor(object_ops),
        )
        result = pipeline.run("build a simple table")

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )
        # All 6 phases should have run
        assert "design" in result.phase_statuses
        assert "spec" in result.phase_statuses
        assert "plan" in result.phase_statuses
        assert "build" in result.phase_statuses
        assert "assemble" in result.phase_statuses
        assert "validate" in result.phase_statuses
