"""Single-turn expert routing helpers."""

from __future__ import annotations

import json
from typing import Any

from ai_3d_modeling_agent.multi_expert.core.coverage import (
    compact_coverage_todos,
    coverage_interaction_contract,
)


def run_single_expert_turn(expert: Any, conversation: Any, context: Any, llm: Any) -> Any:
    from ai_3d_modeling_agent.multi_expert.core.conversation import Message

    payload = dict(context or {}) if isinstance(context, dict) else {}
    payload["agent_role"] = expert.role_name
    sampling = payload.get("sampling")
    turn_payload = _build_agent_turn_payload(expert, conversation, payload)
    messages = [{"role": "user", "content": _render_agent_turn_content(turn_payload)}]
    try:
        raw = llm.call(
            system_prompt="",
            messages=messages,
            sampling=sampling,
            agent="moderator",
            label=f"{expert.role_name}.turn",
            context=payload,
        )
    except TypeError as exc:
        if "unexpected keyword" not in str(exc):
            raise
        raw = llm.call(system_prompt="", messages=messages, sampling=sampling)
    return Message(
        speaker=expert.role_name,
        turn=len(conversation.messages) + 1,
        phase=conversation.phase_name,
        content=raw,
    )


def _build_agent_turn_payload(expert: Any, conversation: Any, context: dict[str, Any]) -> dict[str, Any]:
    meeting_state = context.get("meeting_state")
    turn_kind = str(context.get("meeting_turn_kind", "") or "").strip()
    delegated_agent = str(expert.role_name or "").strip()
    phase_name = str(context.get("phase_name") or getattr(conversation, "phase_name", "") or "").strip()
    delegation_mode = "moderator_task"
    return {
        "task": "Moderator-only routing: use the Task Tool to delegate this meeting turn, then return only the delegated subagent's final meeting output.",
        "ao_route": "moderator",
        "delegation_required": True,
        "delegation_mode": delegation_mode,
        "delegated_agent": delegated_agent,
        "agent_role": delegated_agent,
        "phase_name": phase_name,
        "phase_goal": context.get("phase_goal", ""),
        "turn_kind": turn_kind,
        "meeting_round_index": context.get("meeting_round_index"),
        "meeting_state": meeting_state,
        "accepted_decisions": context.get("accepted_decision_summaries", []),
        "open_issues": context.get("open_issue_summaries", []),
        "last_resolution_summary": context.get("last_resolution_summary", ""),
        "phase_quality_flags": context.get("phase_quality_flags", []),
        "round_change_summary": context.get("round_change_summary", ""),
        "missing_contract_fields": context.get("missing_contract_fields", []),
        "coverage_todos": compact_coverage_todos(context.get("coverage_todos", []) or []),
        "coverage_summary": context.get("coverage_summary", {}),
        "coverage_rule": "Missing required coverage is a blocking issue for reviewer/moderator.",
        "coverage_contract": coverage_interaction_contract(phase_name),
        "current_todo_group": context.get("current_todo_group", {}),
        "revision_request": context.get("revision_request", {}),
        "clarification_attempted": bool(context.get("clarification_attempted", False)),
        "clarification_resolved": bool(context.get("clarification_resolved", False)),
        "conversation_excerpt": _conversation_excerpt(conversation),
        "agent_orchestrator": context.get("agent_orchestrator", {}),
        "moderator_instructions": [
            f"Invoke the `{delegated_agent}` subagent with the Task Tool for this {turn_kind or 'meeting'} turn.",
            "Let the subagent reason in its child session; do not paste its private reasoning into the main session.",
            "Return only the final text that Python should record as this expert turn.",
            "Do not mention Task Tool usage, routing, child sessions, or delegation in the final answer.",
            "Do not introduce generated JSON keys or key-like object identifiers during design/spec/plan meeting turns.",
            "Treat coverage_todos as Python-owned process state: delegate the turn with the todos, but do not ask subagents to create, rename, or close todos.",
            "Do not ask subagents to declare todo status as covered, accepted, complete, or resolved.",
        ],
        "subagent_task_contract": {
            "subagent_type": delegated_agent,
            "expected_return": "final meeting text only",
            "hide_private_reasoning": True,
            "coverage_expectation": "Write phase content for pending/missing required items, or state what information is unresolved; do not declare todo status.",
        },
        "output_contract": {
            "format": "plain meeting text unless Python initiated a structured JSON output turn",
            "sections": ["Proposal", "Rationale", "Concern", "Impact", "Response", "Revision"],
            "single_turn_only": True,
            "no_delegation_narration": True,
        },
    }


def _render_agent_turn_content(payload: dict[str, Any]) -> str:
    delegated_agent = str(payload.get("delegated_agent", "") or "subagent")
    phase_name = str(payload.get("phase_name", "") or "phase")
    turn_kind = str(payload.get("turn_kind", "") or "meeting")
    coverage_todos = payload.get("coverage_todos", [])
    group = payload.get("current_todo_group") if isinstance(payload.get("current_todo_group"), dict) else {}
    focus_target = str(group.get("target_name", "") or "").strip()
    pending_todos = [
        todo
        for todo in coverage_todos
        if isinstance(todo, dict) and str(todo.get("status", "")) in {"pending", "missing"}
    ]
    todo_lines = []
    for todo in pending_todos[:8]:
        task = str(todo.get("task", "") or "").strip()
        requirement = {
            "spec_part_exists": "state whether this accepted part exists in the spec draft",
            "spec_geometry_defined": "draft geometry notes or state which geometry information is unresolved",
            "spec_instance_count_preserved": "state the upstream instance count in natural language",
            "plan_build_responsibility": "draft the build responsibility for this target",
            "plan_assembly_responsibility": "draft the assembly responsibility for this target",
            "plan_instance_count_preserved": "state the upstream instance count in natural language",
        }.get(task, task or "address this focused requirement")
        todo_lines.append(
            "- target={target}: {requirement}".format(
                target=todo.get("target_name", ""),
                requirement=requirement,
            )
        )
    if not todo_lines:
        todo_lines.append("- None")
    focus_lines: list[str] = []
    revision_request = payload.get("revision_request") if isinstance(payload.get("revision_request"), dict) else {}
    if focus_target:
        focus_lines = [
            "",
            f"Focused todo group: {group.get('id', '')}",
            f"Focus target: {focus_target}",
            "Only solve this focus target. Do not solve or specify other targets in this turn.",
            str(group.get("focused_prompt", "") or "").strip(),
        ]
    if revision_request:
        focus_lines.extend(
            [
                "",
                f"Revision request: {revision_request.get('id', '')}",
                f"Revision reason: {revision_request.get('reason', '')}",
                "This is a correction turn after Python artifact validation. Produce a concrete patch for the missing target, or state the exact user input required.",
            ]
        )

    brief = [
        f"{phase_name.title()} {turn_kind} turn.",
        f"Use the Task tool to ask the `{delegated_agent}` subagent for this turn.",
        "Return only the final meeting text that Python should record.",
        "Do not describe routing, sessions, tool calls, or delegation.",
        "Coverage todos are Python-owned process state. Write the phase content needed for pending/missing items, or state what remains unresolved. Do not create, rename, close, mark, accept, complete, or resolve todos in prose.",
        "",
        "Pending or missing coverage todos:",
        *todo_lines,
        *[line for line in focus_lines if line],
        "",
        "Structured context JSON:",
        json.dumps(_compact_payload_for_prompt(payload), ensure_ascii=False, indent=2, default=str),
    ]
    return "\n".join(brief)


def _compact_payload_for_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    keep_keys = [
        "task",
        "ao_route",
        "delegation_required",
        "delegation_mode",
        "delegated_agent",
        "agent_role",
        "phase_name",
        "phase_goal",
        "turn_kind",
        "accepted_decisions",
        "open_issues",
        "phase_quality_flags",
        "coverage_summary",
        "coverage_rule",
        "current_todo_group",
        "revision_request",
        "conversation_excerpt",
    ]
    compact = {key: payload[key] for key in keep_keys if key in payload}
    group = compact.get("current_todo_group")
    if isinstance(group, dict):
        compact["current_todo_group"] = {
            "id": group.get("id", ""),
            "phase": group.get("phase", ""),
            "target_name": group.get("target_name", ""),
            "target_kind": group.get("target_kind", ""),
            "focused_prompt": group.get("focused_prompt", ""),
            "requirements": [
                {"target_name": todo.get("target_name", ""), "task": todo.get("task", "")}
                for todo in list(group.get("todos", []) or [])
                if isinstance(todo, dict)
            ],
        }
    revision = compact.get("revision_request")
    if isinstance(revision, dict):
        compact["revision_request"] = {
            "id": revision.get("id", ""),
            "phase": revision.get("phase", ""),
            "target_name": revision.get("target_name", ""),
            "status": revision.get("status", ""),
            "reason": revision.get("reason", ""),
            "missing_todos": [
                {"target_name": todo.get("target_name", ""), "task": todo.get("task", ""), "missing_reason": todo.get("missing_reason", "")}
                for todo in list(revision.get("missing_todos", []) or [])
                if isinstance(todo, dict)
            ],
        }
    compact["coverage_contract"] = {"authority": "python_process"}
    compact["output_contract"] = {
        "format": "plain meeting text",
        "no_delegation_narration": True,
    }
    return compact


def _conversation_excerpt(conversation: Any, *, limit: int = 3) -> list[dict[str, Any]]:
    messages = list(getattr(conversation, "messages", []) or [])
    excerpt: list[dict[str, Any]] = []
    for message in messages[-limit:]:
        excerpt.append(
            {
                "speaker": getattr(message, "speaker", ""),
                "turn": getattr(message, "turn", 0),
                "phase": getattr(message, "phase", getattr(conversation, "phase_name", "")),
                "content": _truncate_text(getattr(message, "content", str(message)), 900),
            }
        )
    return excerpt


def _truncate_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
