"""Run a readable multi-turn AO meeting eval flow.

Unlike run_meeting_probe.py, this script is optimized for human review. It
records a chronological meeting_timeline.md with the user/Python request,
moderator-routed delegated turns, reviewer challenge, owner response,
moderator resolution, and a final Python-initiated extraction request.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.services.agent_orchestrator import (  # noqa: E402
    AgentOrchestratorClient,
    AgentOrchestratorConfig,
    provision_agent_orchestrator,
)
from run_meeting_probe import (  # noqa: E402
    CASES,
    DEFAULT_AO_URL,
    DEFAULT_MODEL,
    ProbeCase,
    capture_observable_state,
    context_for_mode,
    summarize_context,
    write_json,
)


EXTRACTION_SKILLS = {
    "design": "extract-design-artifact",
    "spec": "extract-spec-artifact",
    "plan": "extract-plan-artifact",
}


@dataclass
class TimelineTurn:
    index: int
    kind: str
    speaker: str
    delegated_agent: str
    request_text: str
    response_text: str
    message_id: str
    events: list[dict[str, Any]]
    child_sessions: list[dict[str, Any]]
    capture_errors: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a readable AO multi-turn meeting flow eval.")
    parser.add_argument("--ao-url", default=DEFAULT_AO_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", required=True, choices=sorted(name for name in CASES if not name.startswith("moderator.")))
    parser.add_argument("--context-mode", default="baseline", choices=("baseline", "compact", "long-context", "focused-task"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--keep-conversation", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id.strip() or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = REPO_ROOT / "tools" / "ao_prompt_eval" / "runs" / run_id
    output_dir = run_root / args.case / args.context_mode / "meeting-flow"
    output_dir.mkdir(parents=True, exist_ok=True)
    case = CASES[args.case]

    conversation_id = f"prompt-flow-{run_id}-{case.name.replace('.', '-')}-{args.context_mode}".replace("_", "-")
    client = AgentOrchestratorClient(
        AgentOrchestratorConfig(
            base_url=args.ao_url,
            model=args.model,
            conversation_id=conversation_id,
            destroy_on_finish=not args.keep_conversation,
            timeout_seconds=args.timeout_seconds,
        )
    )
    session = None
    try:
        session = provision_agent_orchestrator(client, repo_root=REPO_ROOT)
        meeting = run_flow(
            client=client,
            case=case,
            context_mode=args.context_mode,
            model=args.model,
            conversation_id=session.conversation_id,
        )
        payload = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "ao_url": args.ao_url,
            "model": args.model,
            "conversation_id": session.conversation_id,
            "case": case.name,
            "context_mode": args.context_mode,
            "phase": case.phase,
            "turns": [turn.__dict__ for turn in meeting],
        }
        write_json(output_dir / "meeting_timeline.json", payload)
        (output_dir / "meeting_timeline.md").write_text(render_flow_markdown(payload), encoding="utf-8-sig")
        print(output_dir)
    finally:
        client.close()
        if session is not None and not args.keep_conversation:
            try:
                client.stop(session.conversation_id)
            except Exception:
                pass
            try:
                client.delete(session.conversation_id)
            except Exception:
                pass
    return 0


def run_flow(
    *,
    client: AgentOrchestratorClient,
    case: ProbeCase,
    context_mode: str,
    model: str,
    conversation_id: str,
) -> list[TimelineTurn]:
    context = context_for_mode(case, context_mode)
    turns: list[TimelineTurn] = []
    owner = case.delegated_agent
    conversation_so_far: list[dict[str, str]] = []

    turn_specs = [
        (
            "proposal",
            owner,
            f"請用 Task Tool 委派 `{owner}` 針對目前 {case.phase} phase 提出 proposal。Task Tool input 必須包含 description，例如 `{owner} proposal for {case.phase} phase`，以及完整 prompt。回覆內容應是本輪 proposal 發言，不是 moderator 狀態報告。",
        ),
        (
            "challenge",
            "reviewer",
            "請用 Task Tool 委派 `reviewer` 審查上一個 proposal。Task Tool input 必須包含 description，例如 `reviewer blocking challenge`，以及完整 prompt。回覆內容應是 reviewer challenge 發言；只提出 blocking issue，沒有則明確說沒有。",
        ),
    ]
    for kind, delegated_agent, instruction in turn_specs:
        request_text = build_turn_request(
            case=case,
            kind=kind,
            delegated_agent=delegated_agent,
            instruction=instruction,
            context=context,
            conversation_so_far=conversation_so_far,
        )
        turn = send_timeline_turn(
            client=client,
            conversation_id=conversation_id,
            model=model,
            index=len(turns) + 1,
            kind=kind,
            delegated_agent=delegated_agent,
            request_text=request_text,
        )
        turns.append(turn)
        conversation_so_far.append({"speaker": delegated_agent, "kind": kind, "content": turn.response_text})

    if not is_non_blocking_challenge(conversation_so_far[-1]["content"] if conversation_so_far else ""):
        request_text = build_turn_request(
            case=case,
            kind="response",
            delegated_agent=owner,
            instruction=(
                f"請用 Task Tool 委派 `{owner}` 回應 reviewer challenge。Task Tool input 必須包含 description，"
                f"例如 `{owner} response to reviewer challenge`，以及完整 prompt。回覆內容應是本輪 response 發言；"
                "若 reviewer 指出 scope expansion，必須修正或明確拒絕該擴張。"
            ),
            context=context,
            conversation_so_far=conversation_so_far,
        )
        turn = send_timeline_turn(
            client=client,
            conversation_id=conversation_id,
            model=model,
            index=len(turns) + 1,
            kind="response",
            delegated_agent=owner,
            request_text=request_text,
        )
        turns.append(turn)
        conversation_so_far.append({"speaker": owner, "kind": "response", "content": turn.response_text})
    else:
        conversation_so_far.append(
            {
                "speaker": owner,
                "kind": "response_skipped",
                "content": "Skipped owner response because reviewer found no blocking issue.",
            }
        )

    request_text = build_turn_request(
        case=case,
        kind="resolution",
        delegated_agent="moderator",
        instruction="請 moderator 自己裁決本輪會議是否結束。請裁剪不必要複雜度，輸出 Accepted、Rejected、Open Issues、Resolution Summary。",
        context=context,
        conversation_so_far=conversation_so_far,
    )
    turn = send_timeline_turn(
        client=client,
        conversation_id=conversation_id,
        model=model,
        index=len(turns) + 1,
        kind="resolution",
        delegated_agent="moderator",
        request_text=request_text,
    )
    turns.append(turn)
    conversation_so_far.append({"speaker": "moderator", "kind": "resolution", "content": turn.response_text})

    skill = EXTRACTION_SKILLS.get(case.phase, "")
    if skill:
        request_text = build_extraction_request(case=case, skill=skill, conversation_so_far=conversation_so_far)
        turns.append(
            send_timeline_turn(
                client=client,
                conversation_id=conversation_id,
                model=model,
                index=len(turns) + 1,
                kind="artifact_extraction",
                delegated_agent="moderator",
                request_text=request_text,
            )
        )
    return turns


def is_non_blocking_challenge(text: str) -> bool:
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
    )
    blocking_markers = (
        "blocking issue:",
        "blocking issues:",
        "blocking challenge",
        "must be corrected",
        "requires correction",
        "cannot accept",
    )
    return any(marker in lowered for marker in non_blocking_markers) and not any(marker in lowered for marker in blocking_markers)


def send_timeline_turn(
    *,
    client: AgentOrchestratorClient,
    conversation_id: str,
    model: str,
    index: int,
    kind: str,
    delegated_agent: str,
    request_text: str,
) -> TimelineTurn:
    before = capture_observable_state(client, conversation_id)
    response = client.send_message(text=request_text, agent="moderator", model=model)
    after = capture_observable_state(client, conversation_id)
    before_child_ids = {str(child.get("id", "")) for child in flatten_children(before)}
    new_children = [child for child in flatten_children(after) if str(child.get("id", "")) not in before_child_ids]
    return TimelineTurn(
        index=index,
        kind=kind,
        speaker="moderator",
        delegated_agent=delegated_agent,
        request_text=request_text,
        response_text=str(response.get("text", "")),
        message_id=str(response.get("messageId", "")),
        events=new_events(before.get("events", []), after.get("events", [])),
        child_sessions=new_children,
        capture_errors=before.get("errors", []) + after.get("errors", []),
    )


def build_turn_request(
    *,
    case: ProbeCase,
    kind: str,
    delegated_agent: str,
    instruction: str,
    context: dict[str, Any],
    conversation_so_far: list[dict[str, str]],
) -> str:
    context_payload = {
        "phase": case.phase,
        "user_task": case.user_task,
        "phase_goal": case.phase_goal,
        "expected_behavior": case.expected_behavior,
        "risk_being_tested": case.risk,
        "context_summary": summarize_context(context),
        "conversation_so_far": conversation_so_far,
    }
    return (
        "# AO Meeting Eval Turn\n\n"
        f"You are the moderator. Route this turn to `{delegated_agent}` when delegation is requested.\n\n"
        f"Turn kind: {kind}\n"
        f"Phase: {case.phase}\n"
        f"Instruction: {instruction}\n\n"
        "Main-session policy:\n"
        "- Do not add unrequested families, components, helpers, materials, holes, attachments, or geometry.\n"
        "- For this chair task, use concrete product parts: seat, leg, backrest.\n"
        "- Do not introduce abstract container/reference/wrapper families such as Chair Body, main body, model root, or assembly container.\n"
        "- Reviewer should report only blocking issues; if none exist, say there are no blocking issues.\n"
        "- Return the meeting utterance only. Do not echo this request or the context block.\n\n"
        "Context:\n"
        "```json\n"
        f"{json.dumps(context_payload, ensure_ascii=False, indent=2)}\n"
        "```\n"
    )
    payload = {
        "meeting_eval": True,
        "ao_route": "moderator",
        "turn_kind": kind,
        "delegated_agent": delegated_agent,
        "phase": case.phase,
        "user_task": case.user_task,
        "phase_goal": case.phase_goal,
        "expected_behavior": case.expected_behavior,
        "risk_being_tested": case.risk,
        "instruction": instruction,
        "context_summary": summarize_context(context),
        "conversation_so_far": conversation_so_far,
        "main_session_policy": [
            "會議中不得新增未要求的 family/component/helper/material/hole/attachment/geometry。",
            "簡單單物件任務不得拆成 generic family + instance。",
            "會議中不得把自然名稱改寫成 generated identifier，例如 *_Family、*_Body、*_Volume。",
            "Reviewer 必須把 scope expansion 視為 blocking issue。",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_extraction_request(*, case: ProbeCase, skill: str, conversation_so_far: list[dict[str, str]]) -> str:
    payload_for_model = {
        "phase": case.phase,
        "user_task": case.user_task,
        "conversation_so_far": conversation_so_far,
    }
    input_text = (
        "# Artifact Extraction\n\n"
        f"Extract the accepted {case.phase} artifact from the meeting.\n"
        "Use only accepted decisions. Do not add content that was not accepted in the meeting.\n"
        "Return exactly one JSON object. The first character must be `{` and the last character must be `}`.\n\n"
        "Meeting:\n"
        "```json\n"
        f"{json.dumps(payload_for_model, ensure_ascii=False, indent=2)}\n"
        "```\n"
    )
    return f"/{skill} {input_text}"
    payload = {
        "meeting_eval": True,
        "ao_route": "moderator",
        "turn_kind": "artifact_extraction",
        "phase": case.phase,
        "skill": skill,
        "instruction": (
            f"請使用 `{skill}` skill，根據 moderator resolution 與會議結論提取 strict JSON artifact。"
            "只根據 accepted decisions 提取 JSON；不要加入會議沒有接受的內容。回覆必須是 exactly one JSON object，第一個字元必須是 `{`，最後一個字元必須是 `}`。"
        ),
        "user_task": case.user_task,
        "conversation_so_far": conversation_so_far,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def render_flow_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# AO Multi-Expert 會議時序",
        "",
        "## 基本資訊",
        f"- Run ID：{payload['run_id']}",
        f"- Conversation ID：{payload['conversation_id']}",
        f"- Case：{payload['case']}",
        f"- Phase：{payload['phase']}",
        f"- Context mode：{payload['context_mode']}",
        f"- Model：{payload['model']}",
        "",
        "## 重要限制",
        "- 這份紀錄只保存 AO/API 可觀測內容。",
        "- 如果 AO 沒有公開 Task Tool trace 或 child session message，就不會假裝有腦內思考。",
        "- `Moderator → Main Session 最終回覆` 是目前最可靠的 expert 發言來源。",
        "",
    ]
    for turn in payload["turns"]:
        lines.extend(
            [
                f"## {turn['index']}. {turn['kind']}",
                f"- Python/user 請求對象：moderator",
                f"- Moderator 預期委派：{turn['delegated_agent']}",
                f"- Message ID：{turn['message_id']}",
                "",
                "### Python → Moderator",
                *render_request_summary(turn["request_text"]),
                "### AO 可觀測行動",
            ]
        )
        if turn["events"]:
            for event in turn["events"]:
                lines.append(f"- {summarize_event(event)}")
        else:
            lines.append("- 沒有可觀測 tool/task event。")
        if turn["child_sessions"]:
            lines.append("- 新 child sessions：")
            for child in turn["child_sessions"]:
                lines.append(f"  - `{child.get('id', '')}` name={child.get('name', '')} parent={child.get('parent_id', '')}")
        else:
            lines.append("- 沒有觀測到新 child session metadata。")
        if turn["capture_errors"]:
            lines.append("- 擷取錯誤：")
            for error in turn["capture_errors"]:
                lines.append(f"  - {error}")
        lines.extend(
            [
                "",
                "### Moderator → Main Session 最終回覆",
                "```text",
                turn["response_text"].strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_request_summary(request_text: str) -> list[str]:
    try:
        data = json.loads(request_text)
    except json.JSONDecodeError:
        return ["```text", request_text.strip(), "```", ""]
    context = data.get("context_summary", {})
    accepted_count = _context_count(context, "accepted_decisions")
    open_count = _context_count(context, "open_issues")
    excerpt_count = _context_count(context, "conversation_excerpt")
    lines = [
        f"- Turn kind：{data.get('turn_kind', '')}",
        f"- Delegated agent：{data.get('delegated_agent', '')}",
        f"- User task：{data.get('user_task', '')}",
        f"- Phase goal：{data.get('phase_goal', '')}",
        f"- Instruction：{data.get('instruction', '')}",
        f"- Context 摘要：accepted decisions {accepted_count} 筆，open issues {open_count} 筆，conversation excerpt {excerpt_count} 筆。",
    ]
    if data.get("conversation_so_far"):
        lines.append("- 已有會議發言：")
        for item in data["conversation_so_far"]:
            content = str(item.get("content", "")).strip().replace("\n", " ")
            if len(content) > 180:
                content = content[:177] + "..."
            lines.append(f"  - {item.get('kind', '')}/{item.get('speaker', '')}：{content}")
    lines.append("")
    return lines


def summarize_event(event: dict[str, Any]) -> str:
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        return f"{event.get('timestamp', '')} `{event.get('type', '')}`"
    message_id = str(payload.get("messageId", "")).strip()
    text = str(payload.get("text", "")).strip().replace("\n", " ")
    if len(text) > 180:
        text = text[:177] + "..."
    parts = payload.get("parts", [])
    tokens: dict[str, Any] = {}
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "step-finish" and isinstance(part.get("tokens"), dict):
                tokens = dict(part.get("tokens") or {})
                break
    token_text = f" tokens={tokens.get('total')}" if tokens else ""
    text_part = f" text={json.dumps(text, ensure_ascii=False)}" if text else " text=<empty>"
    return f"{event.get('timestamp', '')} `{event.get('type', '')}` message={message_id}{token_text}{text_part}"


def _context_count(context: Any, key: str) -> int:
    if not isinstance(context, dict):
        return 0
    value = context.get(key)
    if isinstance(value, dict):
        count = value.get("count")
        if isinstance(count, int):
            return count
    return 0


def flatten_children(state: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    raw = state.get("children_by_session", {})
    if isinstance(raw, dict):
        for entries in raw.values():
            if isinstance(entries, list):
                children.extend(item for item in entries if isinstance(item, dict))
    return children


def new_events(before: Any, after: Any) -> list[dict[str, Any]]:
    if not isinstance(before, list) or not isinstance(after, list):
        return []
    before_keys = {event_key(event) for event in before if isinstance(event, dict)}
    return [event for event in after if isinstance(event, dict) and event_key(event) not in before_keys]


def event_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("type", "")),
        str(event.get("timestamp", "")),
        json.dumps(event.get("payload", {}), sort_keys=True, default=str),
    )


if __name__ == "__main__":
    raise SystemExit(main())
