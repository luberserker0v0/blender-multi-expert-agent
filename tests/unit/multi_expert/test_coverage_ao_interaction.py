"""Tests for Python-owned coverage todos passed to AO meetings."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation, Message
from ai_3d_modeling_agent.multi_expert.core.expert import SamplingOptions
from ai_3d_modeling_agent.multi_expert.core.meeting import (
    PhaseMeetingState,
    DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
    generate_resolution,
    run_moderated_phase,
    summarize_meeting_message_with_skill,
    update_state_after_challenge,
)
from ai_3d_modeling_agent.multi_expert.experts import Designer, Reviewer
from ai_3d_modeling_agent.multi_expert.experts._turn import _build_agent_turn_payload
from ai_3d_modeling_agent.multi_expert.experts._turn import _render_agent_turn_content
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry


def test_agent_turn_payload_declares_python_owned_coverage_contract() -> None:
    conversation = Conversation(phase_name="spec")
    expert = SimpleNamespace(role_name="specifier")

    payload = _build_agent_turn_payload(
        expert,
        conversation,
        {
            "phase_name": "spec",
            "meeting_turn_kind": "proposal",
            "coverage_todos": [
                {
                    "id": "spec:leg:part_exists",
                    "target_name": "leg",
                    "task": "spec_part_exists",
                    "status": "pending",
                    "required": True,
                },
                {
                    "id": "spec:seat:part_exists",
                    "target_name": "seat",
                    "task": "spec_part_exists",
                    "status": "covered",
                    "required": True,
                },
            ],
            "coverage_summary": {"total": 2, "complete": False},
        },
    )

    assert payload["coverage_contract"]["authority"] == "python_process"
    assert "create new authoritative todo ids" in payload["coverage_contract"]["agent_must_not"]
    assert payload["coverage_summary"] == {"total": 2, "complete": False}
    assert payload["coverage_todos"] == [
        {
            "id": "spec:leg:part_exists",
            "target_name": "leg",
            "task": "spec_part_exists",
            "status": "pending",
            "required": True,
            "missing_reason": "",
        }
    ]
    assert any("Treat coverage_todos as Python-owned process state" in item for item in payload["moderator_instructions"])
    assert payload["subagent_task_contract"]["coverage_expectation"].startswith("Write phase content")
    assert "do not declare todo status" in payload["subagent_task_contract"]["coverage_expectation"]


def test_focused_prompt_still_uses_moderator_task_delegation() -> None:
    conversation = Conversation(phase_name="spec")
    expert = SimpleNamespace(role_name="specifier")

    payload = _build_agent_turn_payload(
        expert,
        conversation,
        {
            "phase_name": "spec",
            "meeting_turn_kind": "proposal",
            "current_todo_group": {
                "id": "spec:leg",
                "target_name": "leg",
                "focused_prompt": "Focus only on `leg`.",
            },
            "coverage_todos": [
                {
                    "id": "spec:leg:part_exists",
                    "target_name": "leg",
                    "task": "spec_part_exists",
                    "status": "pending",
                    "required": True,
                }
            ],
        },
    )
    rendered = _render_agent_turn_content(payload)

    assert payload["ao_route"] == "moderator"
    assert payload["delegation_required"] is True
    assert "Use the Task tool to ask the `specifier` subagent" in rendered
    assert "Focus target: leg" in rendered


def test_resolution_payload_keeps_coverage_under_python_authority() -> None:
    class RecordingLlm:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def call(self, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            return "Decision: keep leg unresolved\nOpen Issues:\n- Coverage gap for leg"

    llm = RecordingLlm()
    state = PhaseMeetingState(
        phase_name="plan",
        goal="Plan accepted parts",
        owner_role="planner",
        reviewer_role="reviewer",
        coverage_todos=[
            {
                "id": "plan:leg:assembly_responsibility",
                "target_name": "leg",
                "task": "plan_assembly_responsibility",
                "status": "missing",
                "required": True,
                "missing_reason": "missing assembly responsibility",
            }
        ],
        coverage_summary={"total": 1, "complete": False, "required_missing": ["plan:leg:assembly_responsibility"]},
    )

    generate_resolution(
        llm,
        state,
        Message(speaker="planner", turn=1, phase="plan", content="Proposal: build leg"),
        Message(speaker="reviewer", turn=2, phase="plan", content="Concern: leg assembly missing"),
        Message(speaker="planner", turn=3, phase="plan", content="Response: cannot resolve yet"),
        sampling=SamplingOptions(temperature=0.1),
    )

    sent = json.loads(llm.calls[0]["messages"][0]["content"])
    assert sent["coverage_contract"]["authority"] == "python_process"
    assert "mark todos covered by assertion alone" in sent["coverage_contract"]["agent_must_not"]
    assert sent["coverage_summary"]["complete"] is False
    assert "Do not mark Python-owned coverage todos complete in prose" in sent["output_contract"]["notes"][-1]


def test_no_blocking_challenge_does_not_create_open_issue() -> None:
    state = PhaseMeetingState(
        phase_name="design",
        goal="Choose part families",
        owner_role="designer",
        reviewer_role="reviewer",
    )

    challenge_id = update_state_after_challenge(
        state,
        1,
        Message(speaker="reviewer", turn=2, phase="design", content="Concern: No blocking issues. The proposal is coherent."),
    )

    assert challenge_id == ""
    assert state.open_issues == []
    assert "needs_review" not in state.phase_quality_flags


def test_meeting_summary_skill_returns_short_markdown_and_records_call() -> None:
    class SummaryLlm:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def call(self, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            return "結論：接受單一 cube 設計。\n下一步：進入規格階段。"

    llm = SummaryLlm()

    summary = summarize_meeting_message_with_skill(
        llm,
        phase_name="design",
        turn_kind="proposal",
        speaker="designer",
        role="designer",
        content="Proposal: Use one cube part. Rationale: no decomposition is needed.",
        fallback_keys=["proposal"],
        context={"session_id": "s-1"},
    )

    assert summary == "結論：接受單一 cube 設計。\n下一步：進入規格階段。"
    assert llm.calls[0]["agent"] == "moderator"
    assert llm.calls[0]["skill"] == "summarize-meeting-message"
    assert llm.calls[0]["context"]["meeting_turn_kind"] == "summary"
    assert llm.calls[0]["context"]["summary_source_turn_kind"] == "proposal"


def test_meeting_summary_skill_failure_falls_back_to_local_summary() -> None:
    class FailingSummaryLlm:
        def call(self, **kwargs: Any) -> str:
            raise RuntimeError("summary unavailable")

    summary = summarize_meeting_message_with_skill(
        FailingSummaryLlm(),
        phase_name="design",
        turn_kind="proposal",
        speaker="designer",
        role="designer",
        content="Proposal: Use one cube part.\nRationale: no decomposition is needed.",
        fallback_keys=["proposal"],
    )

    assert summary == "Use one cube part."


def test_moderated_phase_uses_skill_summary_but_preserves_full_content() -> None:
    class MeetingLlm:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def call(self, **kwargs: Any) -> str:
            self.calls.append(kwargs)
            if kwargs.get("skill") == "summarize-meeting-message":
                source_kind = kwargs.get("context", {}).get("summary_source_turn_kind", "turn")
                return f"結論：{source_kind} 短結論"
            label = str(kwargs.get("label", ""))
            if label == "designer.turn":
                return "Proposal: Use one cube part.\nRationale: simple cube should not be decomposed."
            if label == "reviewer.turn":
                return "Concern: No blocking issues. The proposal is coherent."
            if label == "design.resolution":
                return "Decision: Accept proposal.\nAccepted:\n- Use one cube part.\nRejected:\n- None.\nOpen Issues:\nNone"
            return "OK"

    registry = ExpertRegistry()
    registry.register(Designer())
    registry.register(Reviewer())
    state = PhaseMeetingState(
        phase_name="design",
        goal="Choose part families",
        owner_role="designer",
        reviewer_role="reviewer",
    )
    events: list[dict[str, Any]] = []

    run_moderated_phase(
        conversation=Conversation(phase_name="design"),
        registry=registry,
        base_context={},
        llm=MeetingLlm(),
        state=state,
        sampling_policy=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
        emit=lambda phase, kind, message, **extra: events.append({"phase": phase, "kind": kind, "message": message, **extra}),
        max_rounds=1,
    )

    proposal_event = next(event for event in events if event["kind"] == "proposal")
    resolution_event = next(event for event in events if event["kind"] == "resolution")
    assert proposal_event["summary"] == "結論：proposal 短結論"
    assert proposal_event["full_content"].startswith("Proposal: Use one cube part.")
    assert resolution_event["summary"] == "結論：resolution 短結論"
    assert "Decision: Accept proposal." in resolution_event["full_content"]
