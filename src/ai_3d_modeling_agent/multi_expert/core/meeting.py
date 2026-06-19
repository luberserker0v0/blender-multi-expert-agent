"""Helpers for moderated multi-expert decision phases."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ai_3d_modeling_agent.memory.session_paths import (
    ensure_session_runtime_dir,
    list_session_meeting_state_paths,
    session_meeting_state_path,
)
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation, Message
from ai_3d_modeling_agent.multi_expert.core.coverage import coverage_interaction_contract
from ai_3d_modeling_agent.multi_expert.core.expert import SamplingOptions


SECTION_PATTERN = re.compile(
    r"(?im)^(proposal|rationale|concern|impact|missing constraint|response|revision|decision|accepted|rejected|open issues):\s*"
)
MEETING_SCHEMA_VERSION = 1


def _replace_with_retries(temp_path: Path, path: Path, *, attempts: int = 5) -> None:
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


@dataclass
class AcceptedDecision:
    id: str
    summary: str
    source_round: int
    decision_refs: list[str] = field(default_factory=list)
    status: str = "accepted"
    category: str = "general"
    rationale: str = ""
    evidence: str = ""


@dataclass
class RejectedAlternative:
    id: str
    summary: str
    reason: str
    source_round: int


@dataclass
class OpenIssue:
    id: str
    summary: str
    owner: str
    blocking: bool = True
    issue_type: str = "general"
    impact: str = ""
    introduced_by: str = "reviewer"


@dataclass
class ResolvedChallenge:
    challenge_id: str
    resolution_round: int
    resolution_note: str
    resolved_by: str = "moderator"
    accepted_revision: str = ""


@dataclass
class ResolutionRecord:
    round: int
    summary: str
    accepted_ids: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)
    remaining_open_issue_ids: list[str] = field(default_factory=list)
    change_summary: str = ""


@dataclass
class PhaseMeetingState:
    phase_name: str
    goal: str
    owner_role: str
    reviewer_role: str
    schema_version: int = MEETING_SCHEMA_VERSION
    current_round: int = 0
    accepted_decisions: list[AcceptedDecision] = field(default_factory=list)
    rejected_alternatives: list[RejectedAlternative] = field(default_factory=list)
    open_issues: list[OpenIssue] = field(default_factory=list)
    resolved_challenges: list[ResolvedChallenge] = field(default_factory=list)
    resolution_history: list[ResolutionRecord] = field(default_factory=list)
    last_resolution_summary: str = ""
    phase_status: str = "in_progress"
    round_change_summary: str = ""
    phase_quality_flags: list[str] = field(default_factory=list)
    missing_contract_fields: list[dict[str, Any]] = field(default_factory=list)
    coverage_todos: list[dict[str, Any]] = field(default_factory=list)
    coverage_summary: dict[str, Any] = field(default_factory=dict)
    todo_groups: list[dict[str, Any]] = field(default_factory=list)
    current_todo_group: dict[str, Any] = field(default_factory=dict)
    revision_requests: list[dict[str, Any]] = field(default_factory=list)
    clarification_requests: list[dict[str, Any]] = field(default_factory=list)
    clarification_attempted: bool = False
    clarification_resolved: bool = False
    updated_at: int = 0


@dataclass(frozen=True)
class MultiExpertSamplingPolicy:
    proposal_by_role: dict[str, SamplingOptions] = field(
        default_factory=lambda: {
            "designer": SamplingOptions(temperature=0.5),
            "specifier": SamplingOptions(temperature=0.4),
            "planner": SamplingOptions(temperature=0.4),
        }
    )
    response_by_role: dict[str, SamplingOptions] = field(
        default_factory=lambda: {
            "designer": SamplingOptions(temperature=0.4),
            "specifier": SamplingOptions(temperature=0.3),
            "planner": SamplingOptions(temperature=0.3),
        }
    )
    challenge_by_role: dict[str, SamplingOptions] = field(
        default_factory=lambda: {
            "reviewer": SamplingOptions(temperature=0.2),
        }
    )
    resolution_sampling: SamplingOptions = SamplingOptions(temperature=0.1)
    extractor_sampling: SamplingOptions = SamplingOptions(temperature=0.0)

    def for_turn(self, role_name: str, turn_kind: str) -> SamplingOptions:
        normalized_role = str(role_name or "").strip().lower()
        normalized_turn = str(turn_kind or "").strip().lower()
        if normalized_turn == "proposal":
            return self.proposal_by_role.get(normalized_role, SamplingOptions())
        if normalized_turn == "challenge":
            return self.challenge_by_role.get(normalized_role, SamplingOptions(temperature=0.2))
        if normalized_turn == "response":
            return self.response_by_role.get(normalized_role, SamplingOptions())
        if normalized_turn == "resolution":
            return self.resolution_sampling
        return SamplingOptions()

    def for_extractor(self) -> SamplingOptions:
        return self.extractor_sampling


DEFAULT_MULTI_EXPERT_SAMPLING_POLICY = MultiExpertSamplingPolicy()


def create_phase_meeting_state(phase_name: str, goal: str, owner_role: str, reviewer_role: str) -> PhaseMeetingState:
    return PhaseMeetingState(
        phase_name=phase_name,
        goal=goal,
        owner_role=owner_role,
        reviewer_role=reviewer_role,
    )


def meeting_state_to_dict(state: PhaseMeetingState) -> dict[str, Any]:
    payload = asdict(state)
    payload["schema_version"] = MEETING_SCHEMA_VERSION
    payload["updated_at"] = int(payload.get("updated_at", 0) or 0)
    return payload


def _normalize_phase_meeting_state_record(raw: Any, phase_name: str | None = None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    normalized_phase_name = str(raw.get("phase_name", phase_name or "")).strip()
    if not normalized_phase_name:
        return None

    return {
        "schema_version": int(raw.get("schema_version", MEETING_SCHEMA_VERSION) or MEETING_SCHEMA_VERSION),
        "phase_name": normalized_phase_name,
        "goal": str(raw.get("goal", "")).strip(),
        "owner_role": str(raw.get("owner_role", "")).strip(),
        "reviewer_role": str(raw.get("reviewer_role", "")).strip(),
        "current_round": int(raw.get("current_round", 0) or 0),
        "accepted_decisions": list(raw.get("accepted_decisions", []) or []),
        "rejected_alternatives": list(raw.get("rejected_alternatives", []) or []),
        "open_issues": list(raw.get("open_issues", []) or []),
        "resolved_challenges": list(raw.get("resolved_challenges", []) or []),
        "resolution_history": list(raw.get("resolution_history", []) or []),
        "last_resolution_summary": str(raw.get("last_resolution_summary", "")).strip(),
        "phase_status": str(raw.get("phase_status", "in_progress")).strip() or "in_progress",
        "round_change_summary": str(raw.get("round_change_summary", "")).strip(),
        "phase_quality_flags": [str(flag) for flag in raw.get("phase_quality_flags", []) or [] if str(flag).strip()],
        "missing_contract_fields": list(raw.get("missing_contract_fields", []) or []),
        "coverage_todos": list(raw.get("coverage_todos", []) or []),
        "coverage_summary": dict(raw.get("coverage_summary", {}) or {}),
        "todo_groups": list(raw.get("todo_groups", []) or []),
        "current_todo_group": dict(raw.get("current_todo_group", {}) or {}),
        "revision_requests": list(raw.get("revision_requests", []) or []),
        "clarification_requests": list(raw.get("clarification_requests", []) or []),
        "clarification_attempted": bool(raw.get("clarification_attempted", False)),
        "clarification_resolved": bool(raw.get("clarification_resolved", False)),
        "updated_at": int(raw.get("updated_at", 0) or 0),
    }


def load_phase_meeting_state(runtime_root: Path, session_id: str, phase_name: str) -> dict[str, Any] | None:
    path = session_meeting_state_path(runtime_root, session_id, phase_name)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return _normalize_phase_meeting_state_record(raw, phase_name=phase_name)


def load_all_phase_meeting_states(runtime_root: Path, session_id: str) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for path in list_session_meeting_state_paths(runtime_root, session_id):
        phase_name = path.stem.replace("meeting_state_", "", 1).strip()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        normalized = _normalize_phase_meeting_state_record(raw, phase_name=phase_name)
        if normalized is not None:
            states.append(normalized)
    return sorted(
        states,
        key=lambda item: (int(item.get("updated_at", 0) or 0), int(item.get("current_round", 0) or 0), item.get("phase_name", "")),
    )


def select_latest_meeting_state(runtime_root: Path, session_id: str) -> dict[str, Any] | None:
    states = load_all_phase_meeting_states(runtime_root, session_id)
    return states[-1] if states else None


def persist_phase_meeting_state(context: Any, state: PhaseMeetingState) -> None:
    payload = context if isinstance(context, dict) else {}
    runtime_root_value = payload.get("runtime_root")
    session_id = str(payload.get("session_id", "")).strip()
    if not runtime_root_value or not session_id:
        return

    runtime_root = Path(str(runtime_root_value))
    ensure_session_runtime_dir(runtime_root, session_id)
    path = session_meeting_state_path(runtime_root, session_id, state.phase_name)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    state.updated_at = int(__import__("time").time())
    try:
        temp_path.write_text(json.dumps(meeting_state_to_dict(state), ensure_ascii=False, indent=2), encoding="utf-8")
        _replace_with_retries(temp_path, path)
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass


def build_meeting_context(
    base_context: Any,
    state: PhaseMeetingState,
    turn_kind: str,
    *,
    sampling: SamplingOptions | None = None,
    emit: Callable[..., None] | None = None,
    round_index: int | None = None,
) -> dict[str, Any]:
    payload = dict(base_context or {})
    payload.update(
        {
            "phase_name": state.phase_name,
            "phase_goal": state.goal,
            "meeting_turn_kind": turn_kind,
            "meeting_state": meeting_state_to_dict(state),
            "accepted_decision_summaries": [item.summary for item in state.accepted_decisions],
            "open_issue_summaries": [item.summary for item in state.open_issues],
            "last_resolution_summary": state.last_resolution_summary,
            "phase_quality_flags": list(state.phase_quality_flags),
            "round_change_summary": state.round_change_summary,
            "missing_contract_fields": list(state.missing_contract_fields),
            "coverage_todos": list(state.coverage_todos),
            "coverage_summary": dict(state.coverage_summary),
            "todo_groups": list(state.todo_groups),
            "current_todo_group": dict(state.current_todo_group),
            "revision_requests": list(state.revision_requests),
            "clarification_requests": list(state.clarification_requests),
            "clarification_attempted": bool(state.clarification_attempted),
            "clarification_resolved": bool(state.clarification_resolved),
        }
    )
    if sampling is not None:
        payload["sampling"] = sampling
    if emit is not None:
        payload["meeting_event_emitter"] = emit
    if round_index is not None:
        payload["meeting_round_index"] = round_index
    return payload


def parse_labeled_sections(text: str) -> dict[str, str]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return {}

    matches = list(SECTION_PATTERN.finditer(cleaned))
    if not matches:
        return {}

    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        key = match.group(1).strip().lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
        sections[key] = cleaned[start:end].strip()
    return sections


def summarize_turn_text(text: str, preferred_keys: list[str] | None = None) -> str:
    sections = parse_labeled_sections(text)
    for key in preferred_keys or []:
        value = sections.get(key.lower())
        if value:
            return _first_sentence(value)
    return _first_sentence(str(text or "").strip())


def _first_sentence(text: str) -> str:
    compact = " ".join(part.strip() for part in str(text or "").splitlines() if part.strip())
    if not compact:
        return ""
    return compact[:220].strip()


def split_summary_items(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    if text.lower() in {"none", "n/a", "no open issues"}:
        return []
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        items.append(line)
    if items:
        return items
    return [item.strip() for item in text.split(";") if item.strip()]


def recent_conversation_excerpt(conversation: Conversation, *, limit: int = 3) -> list[dict[str, str]]:
    excerpt: list[dict[str, str]] = []
    recent = [msg for msg in conversation.messages if msg.speaker != "system"][-limit:]
    for msg in recent:
        excerpt.append({"speaker": msg.speaker, "content": _first_sentence(msg.content)[:900]})
    return excerpt


def create_seed_message(phase_name: str, content: str) -> Message:
    return Message(
        speaker="system",
        turn=0,
        phase=phase_name,
        content=content,
    )


def emit_meeting_event(
    emit: Callable[..., None] | None,
    phase_name: str,
    kind: str,
    *,
    round_index: int,
    speaker: str,
    role: str,
    full_content: str,
    summary: str,
    message: str | None = None,
    **extra: Any,
) -> None:
    if emit is None:
        return
    emit(
        phase_name,
        kind,
        message or summary,
        schema_version=MEETING_SCHEMA_VERSION,
        round=round_index,
        speaker=speaker,
        role=role,
        summary=summary,
        full_content=full_content,
        timestamp=__import__("time").strftime("%H:%M"),
        **extra,
    )


def summarize_meeting_message_with_skill(
    llm: Any,
    *,
    phase_name: str,
    turn_kind: str,
    speaker: str,
    role: str,
    content: str,
    fallback_keys: list[str] | None = None,
    context: Any = None,
) -> str:
    fallback = summarize_turn_text(content, fallback_keys)
    if llm is None or not content.strip():
        return fallback
    payload = {
        "task": "Summarize one multi-expert meeting message for the Conversation Surface.",
        "phase": phase_name,
        "turn_kind": turn_kind,
        "speaker": speaker,
        "role": role,
        "message_markdown": content,
        "output": {
            "language": "Traditional Chinese",
            "format": "short Markdown",
            "max_lines": 5,
            "must_not": [
                "JSON",
                "tool routing details",
                "new decisions not present in the source message",
            ],
        },
    }
    base_context = dict(context or {}) if isinstance(context, dict) else {}
    try:
        raw = llm.call(
            system_prompt="",
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)}],
            agent="moderator",
            label=f"{phase_name}.{turn_kind}.summary",
            skill="summarize-meeting-message",
            context={
                **base_context,
                "phase_name": phase_name,
                "agent_role": "moderator",
                "meeting_turn_kind": "summary",
                "summary_source_turn_kind": turn_kind,
            },
        )
    except Exception:
        return fallback
    summary = _clean_meeting_summary(raw)
    return summary or fallback


def _clean_meeting_summary(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md|text)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:5]).strip()


def generate_resolution(
    llm: Any,
    state: PhaseMeetingState,
    proposal_message: Message,
    challenge_message: Message,
    response_message: Message,
    *,
    sampling: SamplingOptions,
) -> str:
    user_payload = {
        "task": "Resolve one moderated multi-expert meeting round.",
        "phase_name": state.phase_name,
        "goal": state.goal,
        "round": state.current_round,
        "accepted_so_far": [item.summary for item in state.accepted_decisions],
        "open_issues_so_far": [item.summary for item in state.open_issues],
        "coverage_todos": state.coverage_todos,
        "coverage_summary": state.coverage_summary,
        "coverage_rule": "Missing required coverage is a blocking issue.",
        "coverage_contract": coverage_interaction_contract(state.phase_name),
        "proposal": {
            "speaker": proposal_message.speaker,
            "content": proposal_message.content,
        },
        "challenge": {
            "speaker": challenge_message.speaker,
            "content": challenge_message.content,
        },
        "response": {
            "speaker": response_message.speaker,
            "content": response_message.content,
        },
        "output_contract": {
            "format": "plain text",
            "required_sections": ["Decision", "Accepted", "Rejected", "Open Issues"],
            "notes": [
                "Explain what changed this round and why the current decision wins.",
                "Keep remaining uncertainty in Open Issues.",
                "Do not mark Python-owned coverage todos complete in prose; if required coverage is still uncertain, keep it in Open Issues.",
            ],
        },
    }
    messages = [{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)}]
    try:
        return llm.call(
            system_prompt="",
            messages=messages,
            sampling=sampling,
            agent="moderator",
            label=f"{state.phase_name}.resolution",
            context={
                "phase_name": state.phase_name,
                "agent_role": "moderator",
                "meeting_turn_kind": "resolution",
                "meeting_state": meeting_state_to_dict(state),
            },
        )
    except TypeError as exc:
        if "unexpected keyword" not in str(exc):
            raise
        return llm.call(
            system_prompt="",
            messages=messages,
            sampling=sampling,
        )


def _bullet_text(values: list[str]) -> str:
    if not values:
        return "- None"
    return "\n".join(f"- {value}" for value in values if value.strip()) or "- None"


def _phase_category(phase_name: str) -> str:
    return {
        "design": "structure",
        "spec": "geometry",
        "plan": "execution_plan",
    }.get(phase_name, "general")


def _issue_type_from_text(text: str) -> str:
    lowered = text.lower()
    if "capability" in lowered or "builder" in lowered or "assembler" in lowered:
        return "capability_boundary"
    if "risk" in lowered:
        return "execution_risk"
    if "constraint" in lowered:
        return "missing_constraint"
    if "contradiction" in lowered:
        return "contradiction"
    if "ambigu" in lowered:
        return "ambiguity"
    return "general"


def update_state_after_challenge(state: PhaseMeetingState, round_index: int, challenge_message: Message) -> str:
    sections = parse_labeled_sections(challenge_message.content)
    concern = summarize_turn_text(challenge_message.content, ["concern"])
    if not concern:
        concern = summarize_turn_text(challenge_message.content)
    impact = sections.get("impact", "").strip()
    issue_id = f"{state.phase_name}-challenge-{round_index}"
    state.open_issues = [issue for issue in state.open_issues if issue.id != issue_id]
    if _is_non_blocking_challenge(challenge_message.content):
        state.phase_quality_flags = [flag for flag in state.phase_quality_flags if flag != "needs_review"]
        return ""
    state.open_issues.append(
        OpenIssue(
            id=issue_id,
            summary=concern or f"Challenge raised in round {round_index}",
            owner=state.owner_role,
            blocking=True,
            issue_type=_issue_type_from_text(" ".join(filter(None, [concern, impact, sections.get("missing constraint", "")]))),
            impact=impact,
            introduced_by=challenge_message.speaker,
        )
    )
    state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "needs_review"]))
    return issue_id


def _is_non_blocking_challenge(text: str) -> bool:
    lowered = " ".join(str(text or "").lower().split())
    if not lowered:
        return False
    non_blocking_markers = (
        "no blocking issue",
        "no blocking issues",
        "no blocker",
        "no blockers",
        "no open issue",
        "no open issues",
        "none remaining",
    )
    blocking_markers = (
        "blocking issue:",
        "blocking issues:",
        "blocking challenge",
        "must be corrected",
        "requires correction",
        "cannot accept",
    )
    return any(marker in lowered for marker in non_blocking_markers) and not any(
        marker in lowered for marker in blocking_markers
    )


def apply_resolution_to_state(
    state: PhaseMeetingState,
    round_index: int,
    resolution_text: str,
    challenge_id: str,
    *,
    proposal_message: Message,
    challenge_message: Message,
    response_message: Message,
) -> None:
    sections = parse_labeled_sections(resolution_text)
    decision = summarize_turn_text(resolution_text, ["decision"])
    accepted_items = split_summary_items(sections.get("accepted", ""))
    rejected_items = split_summary_items(sections.get("rejected", ""))
    open_issue_items = split_summary_items(sections.get("open issues", ""))
    rationale = sections.get("decision", "").strip()
    response_summary = summarize_turn_text(response_message.content, ["response"])
    challenge_summary = summarize_turn_text(challenge_message.content, ["concern"])

    accepted_ids: list[str] = []
    rejected_ids: list[str] = []

    for index, summary in enumerate(accepted_items, start=1):
        decision_id = f"{state.phase_name}-accepted-{round_index}-{index}"
        state.accepted_decisions.append(
            AcceptedDecision(
                id=decision_id,
                summary=summary,
                source_round=round_index,
                category=_phase_category(state.phase_name),
                rationale=rationale,
                evidence=response_summary or proposal_message.content,
            )
        )
        accepted_ids.append(decision_id)

    for index, summary in enumerate(rejected_items, start=1):
        rejected_id = f"{state.phase_name}-rejected-{round_index}-{index}"
        state.rejected_alternatives.append(
            RejectedAlternative(
                id=rejected_id,
                summary=summary,
                reason=decision,
                source_round=round_index,
            )
        )
        rejected_ids.append(rejected_id)

    state.open_issues = [
        OpenIssue(
            id=f"{state.phase_name}-open-{round_index}-{index}",
            summary=summary,
            owner=state.owner_role,
            blocking=True,
            issue_type=_issue_type_from_text(summary),
            impact="Follow-up required before the phase can be considered fully settled.",
            introduced_by="moderator",
        )
        for index, summary in enumerate(open_issue_items, start=1)
    ]

    if challenge_id and not state.open_issues:
        state.resolved_challenges.append(
            ResolvedChallenge(
                challenge_id=challenge_id,
                resolution_round=round_index,
                resolution_note=decision,
                resolved_by="moderator",
                accepted_revision=response_summary,
            )
        )

    state.last_resolution_summary = decision or summarize_turn_text(resolution_text)
    state.round_change_summary = response_summary or proposal_message.content
    state.resolution_history.append(
        ResolutionRecord(
            round=round_index,
            summary=state.last_resolution_summary,
            accepted_ids=accepted_ids,
            rejected_ids=rejected_ids,
            remaining_open_issue_ids=[issue.id for issue in state.open_issues],
            change_summary=state.round_change_summary,
        )
    )
    state.phase_quality_flags = [flag for flag in state.phase_quality_flags if flag not in {"needs_review", "resolved"}]
    if state.open_issues:
        state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "needs_followup"]))
        state.phase_status = "needs_followup"
    else:
        state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "resolved"]))
        state.phase_status = "resolved"
    if not accepted_items and not rejected_items:
        state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "underspecified_resolution"]))
    if challenge_summary and response_summary and challenge_summary.lower() in response_summary.lower():
        state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "weak_revision"]))


def should_continue_rounds(state: PhaseMeetingState, max_rounds: int) -> bool:
    return state.current_round < max_rounds and any(issue.blocking for issue in state.open_issues)


def run_moderated_phase(
    *,
    conversation: Conversation,
    registry: Any,
    llm: Any,
    base_context: Any,
    state: PhaseMeetingState,
    emit: Callable[..., None] | None,
    max_rounds: int = 2,
    sampling_policy: MultiExpertSamplingPolicy = DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
    emit_phase_close: bool = True,
) -> tuple[Conversation, PhaseMeetingState]:
    owner = registry.get(state.owner_role)
    reviewer = registry.get(state.reviewer_role)
    if owner is None:
        raise ValueError(f"Missing owner expert '{state.owner_role}' for phase '{state.phase_name}'")
    if reviewer is None:
        raise ValueError(f"Missing reviewer expert '{state.reviewer_role}' for phase '{state.phase_name}'")

    if emit is not None:
        emit(
            state.phase_name,
            "phase_open",
            f"{state.phase_name.title()} meeting opened.",
            role="moderator",
            round=0,
            summary=f"{state.phase_name.title()} meeting opened.",
        )

    while True:
        state.current_round += 1
        round_index = state.current_round

        proposal_sampling = sampling_policy.for_turn(state.owner_role, "proposal")
        proposal = owner.speak(
            conversation,
            build_meeting_context(
                base_context,
                state,
                "proposal",
                sampling=proposal_sampling,
                emit=emit,
                round_index=round_index,
            ),
            llm,
        )
        conversation.append(proposal)
        proposal_structured = proposal.structured if isinstance(proposal.structured, dict) else {}
        emit_meeting_event(
            emit,
            state.phase_name,
            "proposal",
            round_index=round_index,
            speaker=proposal.speaker,
            role=state.owner_role,
            full_content=proposal.content,
            summary=summarize_meeting_message_with_skill(
                llm,
                phase_name=state.phase_name,
                turn_kind="proposal",
                speaker=proposal.speaker,
                role=state.owner_role,
                content=proposal.content,
                fallback_keys=["proposal"],
                context=base_context,
            ),
            substep=str(proposal_structured.get("substep", "synthesis")),
            final=bool(proposal_structured.get("final", True)),
            deliberation_group_id=proposal_structured.get("deliberation_group_id"),
            guardrail_flags=list(proposal_structured.get("guardrail_flags", []) or []),
        )
        persist_phase_meeting_state(base_context, state)

        challenge_sampling = sampling_policy.for_turn(state.reviewer_role, "challenge")
        challenge = reviewer.speak(
            conversation,
            build_meeting_context(
                base_context,
                state,
                "challenge",
                sampling=challenge_sampling,
                emit=emit,
                round_index=round_index,
            ),
            llm,
        )
        conversation.append(challenge)
        challenge_structured = challenge.structured if isinstance(challenge.structured, dict) else {}
        challenge_id = update_state_after_challenge(state, round_index, challenge)
        emit_meeting_event(
            emit,
            state.phase_name,
            "challenge",
            round_index=round_index,
            speaker=challenge.speaker,
            role=state.reviewer_role,
            full_content=challenge.content,
            summary=summarize_meeting_message_with_skill(
                llm,
                phase_name=state.phase_name,
                turn_kind="challenge",
                speaker=challenge.speaker,
                role=state.reviewer_role,
                content=challenge.content,
                fallback_keys=["concern"],
                context=base_context,
            ),
            open_issue_refs=[challenge_id] if challenge_id else [],
            substep=str(challenge_structured.get("substep", "synthesis")),
            final=bool(challenge_structured.get("final", True)),
            deliberation_group_id=challenge_structured.get("deliberation_group_id"),
            guardrail_flags=list(challenge_structured.get("guardrail_flags", []) or []),
        )
        persist_phase_meeting_state(base_context, state)

        if challenge_id:
            response_sampling = sampling_policy.for_turn(state.owner_role, "response")
            response = owner.speak(
                conversation,
                build_meeting_context(
                    base_context,
                    state,
                    "response",
                    sampling=response_sampling,
                    emit=emit,
                    round_index=round_index,
                ),
                llm,
            )
            conversation.append(response)
            response_structured = response.structured if isinstance(response.structured, dict) else {}
            emit_meeting_event(
                emit,
                state.phase_name,
                "response",
                round_index=round_index,
                speaker=response.speaker,
                role=state.owner_role,
                full_content=response.content,
                summary=summarize_meeting_message_with_skill(
                    llm,
                    phase_name=state.phase_name,
                    turn_kind="response",
                    speaker=response.speaker,
                    role=state.owner_role,
                    content=response.content,
                    fallback_keys=["response"],
                    context=base_context,
                ),
                open_issue_refs=[challenge_id],
                substep=str(response_structured.get("substep", "synthesis")),
                final=bool(response_structured.get("final", True)),
                deliberation_group_id=response_structured.get("deliberation_group_id"),
                guardrail_flags=list(response_structured.get("guardrail_flags", []) or []),
            )
            persist_phase_meeting_state(base_context, state)
        else:
            response = Message(
                speaker=state.owner_role,
                turn=len(conversation.messages) + 1,
                phase=conversation.phase_name,
                content="No owner response required because reviewer found no blocking issue.",
                structured={"kind": "response", "round": round_index, "skipped": True},
            )

        resolution_sampling = sampling_policy.for_turn("moderator", "resolution")
        resolution_text = generate_resolution(
            llm,
            state,
            proposal,
            challenge,
            response,
            sampling=resolution_sampling,
        )
        resolution = Message(
            speaker="moderator",
            turn=len(conversation.messages) + 1,
            phase=conversation.phase_name,
            content=resolution_text,
            structured={"kind": "resolution", "round": round_index},
        )
        conversation.append(resolution)
        apply_resolution_to_state(
            state,
            round_index,
            resolution_text,
            challenge_id,
            proposal_message=proposal,
            challenge_message=challenge,
            response_message=response,
        )
        emit_meeting_event(
            emit,
            state.phase_name,
            "resolution",
            round_index=round_index,
            speaker=resolution.speaker,
            role="moderator",
            full_content=resolution.content,
            summary=summarize_meeting_message_with_skill(
                llm,
                phase_name=state.phase_name,
                turn_kind="resolution",
                speaker=resolution.speaker,
                role="moderator",
                content=resolution.content,
                fallback_keys=["decision"],
                context=base_context,
            ),
            decision_refs=[item.id for item in state.accepted_decisions if item.source_round == round_index],
            open_issue_refs=[issue.id for issue in state.open_issues],
            quality_flags=list(state.phase_quality_flags),
            change_summary=state.round_change_summary,
        )
        persist_phase_meeting_state(base_context, state)

        if not should_continue_rounds(state, max_rounds):
            break

    state.phase_status = "completed" if not state.open_issues else "completed_with_open_issues"
    persist_phase_meeting_state(base_context, state)
    if emit_phase_close and emit is not None:
        emit(
            state.phase_name,
            "phase_close",
            state.last_resolution_summary or f"{state.phase_name.title()} meeting closed.",
            role="moderator",
            round=state.current_round,
            summary=state.last_resolution_summary or f"{state.phase_name.title()} meeting closed.",
            full_content=conversation.messages[-1].content if conversation.messages else "",
            rounds=state.current_round,
            quality_flags=list(state.phase_quality_flags),
            change_summary=state.round_change_summary,
        )
    return conversation, state
