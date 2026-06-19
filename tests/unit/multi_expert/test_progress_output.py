"""Integration tests verifying multi-expert pipeline writes progress.json during execution."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.multi_expert.artifacts import (
    BuildArtifact,
    FinalArtifact,
    PipelineStatus,
)
from ai_3d_modeling_agent.multi_expert.pipeline.adapter import (
    final_artifact_to_snapshot,
)
from ai_3d_modeling_agent.pipelines import runners
from ai_3d_modeling_agent.pipelines.runners import run_pipeline


# ------------------------------------------------------------------
# Mock helpers
# ------------------------------------------------------------------


class MockLLM:
    """Mock LLM returning a fixed response for any call."""

    def __init__(self, fixed_response: str = '{"status": "ok"}') -> None:
        self.fixed_response = fixed_response
        self.call_count = 0

    def call(
        self,
        system_prompt: str = "",
        messages: Optional[list] = None,
        response_model: Any = None,
        sampling: Any = None,
    ) -> str:
        self.call_count += 1
        return self.fixed_response


def _progress_path(session_id: str) -> Path:
    """Compute the expected progress.json path for a given session."""
    return (
        runners.Path(__file__).resolve().parents[3]
        / "data"
        / "runtime"
        / "session_data"
        / session_id
        / "progress.json"
    )


class _FakeAgentOrchestratorClient:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.deleted: list[str] = []

    def send_message(self, *, text: str, agent: str = "", model: str = "") -> dict[str, Any]:
        family = _extract_jsonish_value(text, "target_family")
        if '"Intent": "create"' in text or "builder_todo" in text:
            target = family or "tabletop"
            return {
                "text": (
                    "## Intent\ncreate\n\n"
                    f"## Target\n{target}\n\n"
                    "## Parameters\n"
                    "- primitive_type: cube\n"
                    f"- source_name: {target}_source\n"
                    "- instance_count: 1\n"
                    "- scale: [1.0, 1.0, 0.1]\n\n"
                    "## Validation\nPython verifies the created instance."
                ),
                "messageId": "fake-message",
            }
        if '"Intent": "place"' in text or "builder_place_todo" in text:
            target = family or "tabletop"
            return {
                "text": (
                    "## Intent\nplace\n\n"
                    f"## Target\n{target}\n\n"
                    "## Parameters\n"
                    f"- instances: {target}_01\n"
                    "- location: [0.0, 0.0, 0.0]\n"
                    "- rotation_degrees: [0.0, 0.0, 0.0]\n\n"
                    "## Validation\nPython verifies placement."
                ),
                "messageId": "fake-message",
            }
        return {
            "text": (
                "## Meeting Output\n"
                "Accepted parts: `tabletop` and `leg`.\n"
                "The tabletop is a rectangle with width 1.2 m x depth 0.8 m x height 0.08 m.\n"
                "The leg is a rectangular support with width 0.08 m x depth 0.08 m x height 0.75 m.\n"
                "Instance count: tabletop 1, leg 4."
            ),
            "messageId": "fake-message",
        }

    def close(self) -> None:
        pass

    def delete(self, conversation_id: str) -> None:
        self.deleted.append(conversation_id)


def _extract_jsonish_value(text: str, key: str) -> str:
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"', text or "")
    return match.group(1) if match else ""


def _run_pipeline_with_fake_ao(**kwargs: Any) -> Any:
    session = SimpleNamespace(
        conversation_id="fake-conversation",
        skill_hashes={"extract-design-artifact": "fake-sha"},
    )
    with (
        patch(
            "ai_3d_modeling_agent.services.agent_orchestrator.AgentOrchestratorClient",
            _FakeAgentOrchestratorClient,
        ),
        patch(
            "ai_3d_modeling_agent.services.agent_orchestrator.provision_agent_orchestrator",
            return_value=session,
        ),
    ):
        return run_pipeline(
            agent_orchestrator_base_url="http://fake-agent-orchestrator",
            **kwargs,
        )


# ==================================================================
# Test 1: progress.json is created during multi-expert execution
# ==================================================================


def test_multi_expert_creates_progress_json() -> None:
    """Running multi-expert path creates progress.json in the session directory."""
    session_id = "me-create-test"
    _run_pipeline_with_fake_ao(task="Build a simple table.", session_id=session_id)

    ppath = _progress_path(session_id)
    assert ppath.exists(), f"progress.json not found at {ppath}"

    data = json.loads(ppath.read_text(encoding="utf-8"))
    assert "status" in data
    assert "session_id" in data
    assert data["session_id"] == session_id
    assert "workflow_type" in data
    assert "stage" in data


# ==================================================================
# Test 2: progress.json is updated at each phase transition
# ==================================================================


def test_progress_updated_at_each_phase_transition() -> None:
    """progress.json is written multiple times: initial + per-phase callbacks + final."""
    session_id = "me-phase-test"

    snapshots_written: list[dict] = []
    from ai_3d_modeling_agent.memory.session_progress import SessionProgressStore

    original_write = SessionProgressStore.write_multi_stage_snapshot

    def spy_write(self, sid: str, snapshot: Any) -> Path:
        snapshots_written.append(snapshot.to_dict())
        return original_write(self, sid, snapshot)

    with patch.object(
        SessionProgressStore,
        "write_multi_stage_snapshot",
        autospec=True,
        side_effect=spy_write,
    ):
        _run_pipeline_with_fake_ao(task="Build a simple table.", session_id=session_id)

    # Minimum: 1 initial + 12 phase callbacks (6 phases x start/end) + 1 final = 14
    assert len(snapshots_written) >= 14, (
        f"Expected >=14 snapshot writes, got {len(snapshots_written)}"
    )

    # First write is the initial "running" snapshot before pipeline.run
    assert snapshots_written[0]["status"] == "running"
    assert snapshots_written[0]["stage"] == "design"

    # Intermediate writes should include phase transitions
    stages_seen = {s["stage"] for s in snapshots_written}
    assert "design" in stages_seen

    # Last write is the final snapshot with a terminal status
    last = snapshots_written[-1]
    assert last["status"] in ("completed", "degraded", "partial", "failed")


# ==================================================================
# Test 3: final snapshot has status="completed" and stage="completed"
#         after a SUCCESS pipeline run
# ==================================================================


def test_final_snapshot_status_completed_on_success() -> None:
    """Adapter maps PipelineStatus.SUCCESS to status='completed', stage='completed'."""
    artifact = FinalArtifact(
        task_prompt="Build a table.",
        status=PipelineStatus.SUCCESS,
        phase_statuses={
            "design": PipelineStatus.SUCCESS,
            "specs": PipelineStatus.SUCCESS,
            "plan": PipelineStatus.SUCCESS,
            "build": PipelineStatus.SUCCESS,
            "assembly": PipelineStatus.SUCCESS,
            "validation": PipelineStatus.SUCCESS,
        },
    )
    snapshot = final_artifact_to_snapshot(
        artifact,
        task_prompt="Build a table.",
        session_id="test-session",
    )

    assert snapshot.status == "completed"
    assert snapshot.stage == "completed"
    assert snapshot.stage_status == "completed"
    assert snapshot.task == "Build a table."
    assert snapshot.workflow_type == "multi_stage_modeling"
    assert snapshot.multi_expert_mode is True


# ==================================================================
# Test 4: llm_prompt_events array is populated in progress.json
# ==================================================================


def test_llm_prompt_events_populated() -> None:
    """Multi-expert execution populates llm_prompt_events in progress.json."""
    session_id = "me-events-test"
    _run_pipeline_with_fake_ao(task="Build a simple table.", session_id=session_id)

    ppath = _progress_path(session_id)
    data = json.loads(ppath.read_text(encoding="utf-8"))

    events = data.get("llm_prompt_events", [])
    # Pipeline fires prompt_observer for 5 LLM phases
    # (design, spec, build, assemble, validate — plan is deterministic)
    assert len(events) >= 6, f"Expected >=6 llm_prompt_events, got {len(events)}"

    # Each event has the expected structure
    for event in events:
        assert "event_id" in event
        assert "stage" in event
        assert "label" in event
        assert "prompt_preview" in event

    # Verify key stages are represented
    stages = {e["stage"] for e in events}
    assert "design" in stages
    assert "plan" in stages
    assert "build" in stages


# ==================================================================
# Test 5: part_tasks mapped from build_results
# ==================================================================


def test_part_tasks_mapped_from_build_results() -> None:
    """Adapter converts build_results dict into part_tasks with correct structure."""
    build_results = {
        "table_top": BuildArtifact(
            part_name="table_top",
            source_object_name="table_top_mesh",
            status="built",
            capture_paths=["/captures/top_r1.png"],
            refinement_rounds=1,
            action_history=[
                {
                    "action_type": "scale_axis_z",
                    "parameters": {"factor": 1.2},
                    "reason": "Too thin",
                }
            ],
        ),
        "table_leg": BuildArtifact(
            part_name="table_leg",
            source_object_name="table_leg_mesh",
            status="built",
            capture_paths=["/captures/leg_r1.png"],
            refinement_rounds=1,
            action_history=[],
        ),
    }
    artifact = FinalArtifact(
        task_prompt="Build a table.",
        status=PipelineStatus.SUCCESS,
        build_results=build_results,
        phase_statuses={
            "design": PipelineStatus.SUCCESS,
            "specs": PipelineStatus.SUCCESS,
            "plan": PipelineStatus.SUCCESS,
            "build": PipelineStatus.SUCCESS,
            "assembly": PipelineStatus.SUCCESS,
            "validation": PipelineStatus.SUCCESS,
        },
    )
    snapshot = final_artifact_to_snapshot(
        artifact,
        task_prompt="Build a table.",
        session_id="test-session",
    )

    # Both parts should appear in part_tasks
    assert len(snapshot.part_tasks) == 2
    part_ids = {pt.task_id for pt in snapshot.part_tasks}
    assert "table_top" in part_ids
    assert "table_leg" in part_ids

    # Verify table_top mapping
    top_task = next(pt for pt in snapshot.part_tasks if pt.task_id == "table_top")
    assert top_task.status == "approved"
    assert top_task.approved is True
    assert top_task.object_name == "table_top_mesh"
    assert len(top_task.rounds) >= 1
    assert top_task.rounds[0].requested_action is not None
    assert top_task.rounds[0].requested_action.action_type == "scale_axis_z"

    # completed_task_ids should include both built parts
    assert set(snapshot.completed_task_ids) == {"table_top", "table_leg"}


# ==================================================================
# Test 6: adapter handles missing optional artifact fields gracefully
# ==================================================================


def test_adapter_handles_missing_optional_fields() -> None:
    """Adapter produces valid snapshot from a minimal FinalArtifact with all defaults."""
    artifact = FinalArtifact()  # All defaults: empty build_results, no assembly, no validation

    snapshot = final_artifact_to_snapshot(
        artifact,
        task_prompt="",
        session_id="",
    )

    # Should not crash and should produce valid defaults
    assert snapshot.status == "failed"  # Default PipelineStatus is FAILED
    assert snapshot.part_tasks == []
    assert snapshot.completed_task_ids == []
    assert snapshot.assembly is not None
    assert snapshot.assembly.rounds == []
    assert snapshot.final_validation is not None
    assert snapshot.llm_prompt_events == []

    # to_dict should serialize without error
    d = snapshot.to_dict()
    assert isinstance(d, dict)
    assert "status" in d
    assert "part_tasks" in d
    assert "assembly" in d
    assert "final_validation" in d
    assert "llm_prompt_events" in d
    assert "completed_task_ids" in d
