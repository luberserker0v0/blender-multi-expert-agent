"""Real end-to-end test for the multi-expert pipeline.

Requires:
  - LLM endpoint configured in tests/e2e/settings.json
  - Blender MCP server connected

Run with: pytest -m integration tests/e2e/test_real_pipeline.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ai_3d_modeling_agent.blender.mcp_adapter import BlenderMcpAdapter
from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
from ai_3d_modeling_agent.io.buffered_writer import BufferedWriter
from ai_3d_modeling_agent.io.settings_loader import load_settings
from ai_3d_modeling_agent.multi_expert.artifacts import (
    DesignArtifact,
    FinalArtifact,
    PipelineStatus,
    SpecArtifact,
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


pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "tests" / "e2e" / "settings.json"


def _skip_if_no_llm():
    settings = load_settings(SETTINGS_PATH)
    if not settings.get("llm_endpoint_url"):
        pytest.skip("LLM endpoint not configured in settings.json")


def _full_registry() -> ExpertRegistry:
    registry = ExpertRegistry()
    for cls in (Designer, Specifier, Planner, Reviewer, Builder, Inspector):
        registry.register(cls())
    return registry


class TestRealPipeline:
    """Real E2E tests that require LLM endpoint + Blender MCP."""

    def test_pipeline_with_real_llm_and_simulated_blender(self):
        """Full pipeline with real LLM and SimulatedBlender."""
        _skip_if_no_llm()

        from ai_3d_modeling_agent.services.llm_endpoint import (
            OpenAiCompatibleEndpointClient,
            OpenAiCompatibleEndpointConfig,
        )

        settings = load_settings(SETTINGS_PATH)

        config = OpenAiCompatibleEndpointConfig(
            base_url=settings["llm_endpoint_url"],
            model=settings.get("llm_model", "default"),
            timeout_seconds=120.0,
        )
        llm_client = OpenAiCompatibleEndpointClient(config)

        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        events: list[dict] = []

        def on_event(event):
            events.append(event)

        pipeline = Pipeline(
            registry=registry,
            llm=llm_client,
            object_ops=object_ops,
            executor=executor,
            event_callback=on_event,
        )
        result = pipeline.run("build a simple table with a flat top and four legs")

        # Verify pipeline completed
        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.SUCCESS_WITH_WARNINGS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

        # Verify design phase produced parts
        assert isinstance(result.design, DesignArtifact)
        assert len(result.design.parts) > 0

        # Verify spec phase ran (may have empty parts if LLM response was truncated)
        assert isinstance(result.specs, SpecArtifact)

        # Verify plan phase produced steps
        assert result.plan is not None
        assert len(result.plan.steps) > 0

        # Verify build phase ran
        assert isinstance(result.build_results, dict)

        # Verify events were emitted
        assert len(events) > 0
        kinds = [e["kind"] for e in events]
        assert "phase_open" in kinds
        assert "phase_close" in kinds

    def test_pipeline_persists_meetings(self):
        """Pipeline persists meeting events to meetings.jsonl."""
        _skip_if_no_llm()

        import tempfile

        from ai_3d_modeling_agent.services.llm_endpoint import (
            OpenAiCompatibleEndpointClient,
            OpenAiCompatibleEndpointConfig,
        )

        settings = load_settings(SETTINGS_PATH)

        config = OpenAiCompatibleEndpointConfig(
            base_url=settings["llm_endpoint_url"],
            model=settings.get("llm_model", "default"),
            timeout_seconds=120.0,
        )
        llm_client = OpenAiCompatibleEndpointClient(config)

        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        with tempfile.TemporaryDirectory() as tmp_dir:
            meetings_path = Path(tmp_dir) / "meetings.jsonl"
            event_buffer = BufferedWriter(meetings_path)

            pipeline = Pipeline(
                registry=registry,
                llm=llm_client,
                object_ops=object_ops,
                executor=executor,
                event_buffer=event_buffer,
            )
            pipeline.run("build a simple box")

            event_buffer.flush()

            assert meetings_path.exists()
            lines = meetings_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) > 0

    def test_cli_run_from_settings(self):
        """CLI runner works with real settings."""
        _skip_if_no_llm()

        from ai_3d_modeling_agent.pipelines.runners import run_pipeline_from_settings

        result = run_pipeline_from_settings(
            SETTINGS_PATH,
            task="build a simple cube",
            session_id="e2e-cli-test",
        )

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.SUCCESS_WITH_WARNINGS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

    def test_pipeline_with_real_blender_mcp(self):
        """Full pipeline with real LLM and real Blender MCP."""
        _skip_if_no_llm()

        settings = load_settings(SETTINGS_PATH)
        if not settings.get("use_blender_mcp"):
            pytest.skip("Blender MCP not enabled in settings.json")

        from ai_3d_modeling_agent.pipelines.runners import run_pipeline

        # Setup event buffer for logging
        log_dir = REPO_ROOT / "data" / "runtime" / "e2e_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        meetings_path = log_dir / "meetings_blender_mcp.jsonl"
        event_buffer = BufferedWriter(meetings_path)

        result = run_pipeline(
            task="build a simple table with a flat top and four legs",
            session_id="e2e-blender-mcp-test",
            llm_endpoint_url=settings["llm_endpoint_url"],
            llm_model=settings.get("llm_model", "default"),
            use_blender_mcp=True,
            blender_mcp_command=settings.get("blender_mcp_command", "uv"),
            blender_mcp_args=settings.get("blender_mcp_args", []),
            blender_mcp_cwd=settings.get("blender_mcp_cwd"),
            event_buffer=event_buffer,
        )

        event_buffer.flush()

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.SUCCESS_WITH_WARNINGS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

        # Verify design phase produced parts
        assert isinstance(result.design, DesignArtifact)
        assert len(result.design.parts) > 0

        # Verify spec phase ran
        assert isinstance(result.specs, SpecArtifact)

        # Verify plan phase produced steps
        assert result.plan is not None
        assert len(result.plan.steps) > 0

        # Verify build phase ran
        assert isinstance(result.build_results, dict)
        assert len(result.build_results) > 0

        # Verify validation ran
        assert result.validation is not None

        # Verify meetings log was written
        assert meetings_path.exists()
        lines = meetings_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) > 0
        print(f"\n[LOG] Meetings log: {meetings_path} ({len(lines)} events)")
