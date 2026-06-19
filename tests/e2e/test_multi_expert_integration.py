"""Integration test for the multi-expert pipeline with a real LLM endpoint.

Requires:
  - LLM endpoint configured in tests/e2e/settings.json

Run with: pytest -m integration tests/e2e/test_multi_expert_integration.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
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
    Reviewer,
    Specifier,
)
from ai_3d_modeling_agent.multi_expert.pipeline.pipeline import Pipeline
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry


pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "tests" / "e2e" / "settings.json"


def _skip_if_no_endpoint():
    settings = load_settings(SETTINGS_PATH)
    if not settings.get("llm_endpoint_url"):
        pytest.skip("LLM endpoint not configured in settings.json")


def _make_llm_client():
    from ai_3d_modeling_agent.services.llm_endpoint import (
        OpenAiCompatibleEndpointClient,
        OpenAiCompatibleEndpointConfig,
    )

    settings = load_settings(SETTINGS_PATH)
    config = OpenAiCompatibleEndpointConfig(
        base_url=settings["llm_endpoint_url"],
        model=settings.get("llm_model", "default"),
        api_key=settings.get("llm_api_key"),
        timeout_seconds=120.0,
    )
    return OpenAiCompatibleEndpointClient(config)


def _full_registry() -> ExpertRegistry:
    registry = ExpertRegistry()
    for cls in (Designer, Specifier, Reviewer, Builder, Inspector):
        registry.register(cls())
    return registry


class TestMultiExpertIntegration:
    """Integration tests that require a real LLM endpoint."""

    def test_pipeline_with_real_llm(self):
        """Run the full pipeline with a real LLM and SimulatedBlender."""
        _skip_if_no_endpoint()

        llm = _make_llm_client()
        object_ops = SimulatedBlenderObjectOps()
        executor = ActionExecutor(object_ops)
        registry = _full_registry()

        pipeline = Pipeline(
            registry=registry,
            llm=llm,
            object_ops=object_ops,
            executor=executor,
        )
        result = pipeline.run("build a simple wooden table with a flat top and four legs")

        assert isinstance(result, FinalArtifact)
        assert result.status in (
            PipelineStatus.SUCCESS,
            PipelineStatus.SUCCESS_WITH_WARNINGS,
            PipelineStatus.DEGRADED,
            PipelineStatus.PARTIAL,
        )

        assert isinstance(result.design, DesignArtifact)
        assert len(result.design.parts) > 0
        assert result.design.summary != ""

        assert isinstance(result.specs, SpecArtifact)
        assert len(result.specs.parts) > 0

        assert result.plan is not None
        assert len(result.plan.steps) > 0

        assert len(result.build_results) > 0

        assert result.validation is not None

        created_objects = object_ops.list_object_names()
        assert len(created_objects) > 0
