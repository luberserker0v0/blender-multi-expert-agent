"""Run Agent Orchestrator meeting prompt probes.

This tool provisions the current .opencode documents into a fresh AO
conversation for each probe, sends one design/spec/plan meeting prompt, and
writes request.json, response.txt, and a Traditional Chinese comment.md for
manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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


DEFAULT_AO_URL = "http://127.0.0.1:6919"
DEFAULT_MODEL = "my_local_lmstudio/gemma-4-e4b-uncensored-hauhaucs-aggressive"
CONTEXT_MODES = ("baseline", "compact", "long-context", "focused-task")


@dataclass(frozen=True)
class ProbeCase:
    name: str
    phase: str
    delegated_agent: str
    turn_kind: str
    user_task: str
    phase_goal: str
    expected_behavior: str
    risk: str
    base_context: dict[str, Any]


CASES: dict[str, ProbeCase] = {
    "design.simple_cube": ProbeCase(
        name="design.simple_cube",
        phase="design",
        delegated_agent="designer",
        turn_kind="proposal",
        user_task="Create one simple cube named E2E_Cube at the origin.",
        phase_goal="Decompose the user's task into logical part families and a high-level assembly concept.",
        expected_behavior="Return one deliverable family for E2E_Cube; do not introduce face, edge, vertex, or surface families.",
        risk="Designer or reviewer may over-decompose a simple primitive into helper geometry.",
        base_context={
            "allowed_families": [],
            "accepted_decisions": [],
            "open_issues": [],
            "last_resolution_summary": "",
        },
    ),
    "design.chair.multi_part": ProbeCase(
        name="design.chair.multi_part",
        phase="design",
        delegated_agent="designer",
        turn_kind="proposal",
        user_task="Create a simple wooden chair with a seat, four legs, and a backrest.",
        phase_goal="Decompose the user's task into logical part families and a high-level assembly concept.",
        expected_behavior="Use meaningful deliverable families such as seat, legs, and backrest; do not split into edges, faces, or vertices.",
        risk="Designer may confuse useful product parts with raw geometric sub-elements.",
        base_context={
            "allowed_families": [],
            "accepted_decisions": [],
            "open_issues": [],
            "last_resolution_summary": "",
        },
    ),
    "spec.allowed_family_guard": ProbeCase(
        name="spec.allowed_family_guard",
        phase="spec",
        delegated_agent="specifier",
        turn_kind="proposal",
        user_task="Specify geometry for a previously accepted simple cube design.",
        phase_goal="Specify geometry, attachment points, and constraints for every accepted part family.",
        expected_behavior="Specify only the accepted single cube deliverable; do not add face, edge, surface, body, or helper deliverables.",
        risk="Specifier may create new deliverables that design did not accept.",
        base_context={
            "allowed_families": ["E2E_Cube"],
            "design_parts": [
                {
                    "name": "E2E_Cube",
                    "description": "A single cube object at the origin.",
                    "instance_count": 1,
                    "parent_name": None,
                    "symmetry_group": "NONE",
                }
            ],
            "accepted_decisions": ["The design has exactly one deliverable family: E2E_Cube."],
            "open_issues": [],
            "last_resolution_summary": "Use one monolithic cube deliverable named E2E_Cube.",
        },
    ),
    "plan.allowed_family_guard": ProbeCase(
        name="plan.allowed_family_guard",
        phase="plan",
        delegated_agent="planner",
        turn_kind="proposal",
        user_task="Plan execution for a previously specified simple cube.",
        phase_goal="Define execution order, assembly order, dependencies, and planning rationale.",
        expected_behavior="Plan build and assembly only for the accepted single cube deliverable; do not introduce helper deliverables or unsupported operations.",
        risk="Planner may expand the plan with helper geometry or extra objects absent from accepted decisions.",
        base_context={
            "allowed_families": ["E2E_Cube"],
            "spec_parts": {
                "E2E_Cube": {
                    "primitive": "cube",
                    "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
                    "attachment_points": [{"id": "center", "name": "center", "local_offset": [0.0, 0.0, 0.0]}],
                }
            },
            "part_families": [
                {
                    "name": "E2E_Cube",
                    "description": "A single cube object at the origin.",
                    "instance_count": 1,
                    "parent_name": None,
                    "symmetry_group": "NONE",
                }
            ],
            "accepted_decisions": ["Build one cube primitive and place it at the origin."],
            "open_issues": [],
            "last_resolution_summary": "The specification is complete for E2E_Cube only.",
        },
    ),
    "moderator.over_complexity_rejection": ProbeCase(
        name="moderator.over_complexity_rejection",
        phase="design",
        delegated_agent="moderator",
        turn_kind="resolution",
        user_task="Resolve a design meeting for one simple cube named E2E_Cube at the origin.",
        phase_goal="Resolve proposal, challenge, and response into accepted/rejected/open issues.",
        expected_behavior="Accept the minimal one-family cube design and reject unnecessary face/edge/vertex decomposition.",
        risk="Moderator may accept every suggestion and amplify unnecessary complexity.",
        base_context={
            "accepted_decisions": [],
            "open_issues": [
                "Reviewer suggested splitting the cube into separate face and edge deliverables for rigor, but the user asked for one simple cube."
            ],
            "proposal": "Designer proposed one deliverable family: E2E_Cube.",
            "challenge": "Reviewer challenged that cube faces and edges could be separate deliverables.",
            "response": "Designer agreed that helper geometry is not needed for this task.",
        },
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AO meeting prompt eval probes.")
    parser.add_argument("--ao-url", default=DEFAULT_AO_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", action="append", choices=sorted(CASES))
    parser.add_argument("--context-mode", nargs="+", default=["baseline"], choices=CONTEXT_MODES)
    parser.add_argument("--all", action="store_true", help="Run all probe cases.")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--keep-conversation", action="store_true")
    args = parser.parse_args()

    selected_cases = sorted(CASES) if args.all else (args.case or [])
    if not selected_cases:
        parser.error("Provide --case or --all.")

    run_id = args.run_id.strip() or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_root = REPO_ROOT / "tools" / "ao_prompt_eval" / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    failures = 0
    for case_name in selected_cases:
        for mode in args.context_mode:
            try:
                output_dir = run_probe(
                    case=CASES[case_name],
                    context_mode=mode,
                    ao_url=args.ao_url,
                    model=args.model,
                    timeout_seconds=args.timeout_seconds,
                    keep_conversation=args.keep_conversation,
                    run_root=run_root,
                    run_id=run_id,
                )
                print(f"[ok] {case_name} / {mode}: {output_dir}")
            except Exception as exc:  # noqa: BLE001 - CLI should keep running other cases.
                failures += 1
                print(f"[failed] {case_name} / {mode}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def run_probe(
    *,
    case: ProbeCase,
    context_mode: str,
    ao_url: str,
    model: str,
    timeout_seconds: int,
    keep_conversation: bool,
    run_root: Path,
    run_id: str,
) -> Path:
    output_dir = run_root / case.name / context_mode
    output_dir.mkdir(parents=True, exist_ok=True)

    conversation_id = f"prompt-eval-{run_id}-{case.name.replace('.', '-')}-{context_mode}".replace("_", "-")
    client = AgentOrchestratorClient(
        AgentOrchestratorConfig(
            base_url=ao_url,
            model=model,
            conversation_id=conversation_id,
            destroy_on_finish=not keep_conversation,
            timeout_seconds=timeout_seconds,
        )
    )
    session = None
    try:
        session = provision_agent_orchestrator(client, repo_root=REPO_ROOT)
        prompt_payload = build_prompt_payload(case, context_mode=context_mode)
        message_text = json.dumps(prompt_payload, ensure_ascii=False, indent=2)
        before_state = capture_observable_state(client, session.conversation_id)
        response = client.send_message(text=message_text, agent="moderator", model=model)
        after_state = capture_observable_state(client, session.conversation_id)
        response_text = str(response.get("text", ""))
        request_payload = {
            "eval_id": f"{run_id}/{case.name}/{context_mode}",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "ao_url": ao_url,
            "model": model,
            "conversation_id": session.conversation_id,
            "case": case.name,
            "phase": case.phase,
            "ao_agent": "moderator",
            "delegated_agent": case.delegated_agent,
            "turn_kind": case.turn_kind,
            "task_delegation_required": True,
            "context_mode": context_mode,
            "prompt_payload": prompt_payload,
            "tested_documents": list_opencode_documents(),
            "response_message_id": response.get("messageId", ""),
            "kept_conversation": keep_conversation,
        }
        timeline_payload = build_meeting_timeline(
            request=request_payload,
            response=response,
            response_text=response_text,
            before_state=before_state,
            after_state=after_state,
        )
        write_json(output_dir / "request.json", request_payload)
        write_json(output_dir / "meeting_timeline.json", timeline_payload)
        (output_dir / "response.txt").write_text(response_text, encoding="utf-8-sig")
        (output_dir / "meeting_timeline.md").write_text(render_meeting_timeline(timeline_payload), encoding="utf-8-sig")
        write_comment_template(
            output_dir / "comment.md",
            template_path=REPO_ROOT / "tools" / "ao_prompt_eval" / "templates" / "eval_comment_template.md",
            request=request_payload,
            case=case,
        )
    finally:
        client.close()
        if session is not None and not keep_conversation:
            try:
                client.stop(session.conversation_id)
            except Exception:
                pass
            try:
                client.delete(session.conversation_id)
            except Exception:
                pass
    return output_dir


def capture_observable_state(client: AgentOrchestratorClient, conversation_id: str) -> dict[str, Any]:
    state: dict[str, Any] = {"sessions": [], "children_by_session": {}, "events": [], "errors": []}
    try:
        state["sessions"] = client.list_sessions(conversation_id)
    except Exception as exc:  # noqa: BLE001 - eval diagnostics should continue.
        state["errors"].append(f"list_sessions failed: {exc}")
    for session in state["sessions"]:
        session_id = str(session.get("id", "")).strip()
        if not session_id:
            continue
        try:
            state["children_by_session"][session_id] = client.list_session_children(conversation_id, session_id)
        except Exception as exc:  # noqa: BLE001
            state["errors"].append(f"list_session_children({session_id}) failed: {exc}")
    try:
        state["events"] = client.get_events(conversation_id)
    except Exception as exc:  # noqa: BLE001
        state["errors"].append(f"get_events failed: {exc}")
    return state


def build_meeting_timeline(
    *,
    request: dict[str, Any],
    response: dict[str, Any],
    response_text: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> dict[str, Any]:
    prompt_payload = request["prompt_payload"]
    before_children = _flatten_children(before_state)
    after_children = _flatten_children(after_state)
    child_sessions = [
        child for child in after_children if str(child.get("id", "")) not in {str(item.get("id", "")) for item in before_children}
    ]
    events = _new_events(before_state.get("events", []), after_state.get("events", []))
    response_parts = response.get("parts", [])
    if not isinstance(response_parts, list):
        response_parts = []
    return {
        "eval_id": request["eval_id"],
        "conversation_id": request["conversation_id"],
        "context_mode": request["context_mode"],
        "phase": request["phase"],
        "turn_kind": request["turn_kind"],
        "ao_route": request["ao_agent"],
        "delegated_agent": request["delegated_agent"],
        "model": request["model"],
        "user_to_moderator": {
            "task": prompt_payload.get("task", ""),
            "user_task": prompt_payload.get("user_task", ""),
            "phase_goal": prompt_payload.get("phase_goal", ""),
            "expected_behavior": prompt_payload.get("expected_behavior", ""),
            "risk_being_tested": prompt_payload.get("risk_being_tested", ""),
            "provided_context_summary": summarize_context(prompt_payload.get("provided_context", {})),
        },
        "observable_ao": {
            "main_sessions_before": before_state.get("sessions", []),
            "main_sessions_after": after_state.get("sessions", []),
            "new_child_sessions": child_sessions,
            "new_events": events,
            "capture_errors": before_state.get("errors", []) + after_state.get("errors", []),
        },
        "message_response": {
            "message_id": response.get("messageId", ""),
            "text": response_text,
            "parts": response_parts,
        },
        "limitations": [
            "AO/OpenCode REST response exposes the main-session final response and session/event metadata.",
            "Subagent child-session private reasoning is not available unless AO exposes message/tool trace APIs.",
            "Do not infer hidden chain-of-thought from the final response.",
        ],
    }


def summarize_context(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {"type": type(context).__name__}
    summary: dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, list):
            summary[key] = {"type": "list", "count": len(value), "preview": value[:3]}
        elif isinstance(value, dict):
            summary[key] = {"type": "object", "keys": sorted(str(item) for item in value.keys())[:12]}
        else:
            summary[key] = value
    return summary


def render_meeting_timeline(timeline: dict[str, Any]) -> str:
    request = timeline["user_to_moderator"]
    response = timeline["message_response"]
    observable = timeline["observable_ao"]
    events = observable.get("new_events", [])
    child_sessions = observable.get("new_child_sessions", [])
    errors = observable.get("capture_errors", [])
    lines = [
        "# AO 會議時序紀錄",
        "",
        "## 基本資訊",
        f"- Eval ID：{timeline['eval_id']}",
        f"- Conversation ID：{timeline['conversation_id']}",
        f"- Phase：{timeline['phase']}",
        f"- Turn：{timeline['turn_kind']}",
        f"- AO route：{timeline['ao_route']}",
        f"- 目標 delegated agent：{timeline['delegated_agent']}",
        f"- Model：{timeline['model']}",
        f"- Context mode：{timeline['context_mode']}",
        "",
        "## 時序",
        "### 1. 使用者 / Python → Moderator",
        f"- 任務：{request.get('user_task', '')}",
        f"- Phase 目標：{request.get('phase_goal', '')}",
        f"- 預期行為：{request.get('expected_behavior', '')}",
        f"- 測試風險：{request.get('risk_being_tested', '')}",
        f"- 要求：請 moderator 使用 Task Tool 委派 `{timeline['delegated_agent']}`，main session 只回傳可用結論。",
        "",
        "### 2. Moderator 行動 / AO 可觀測事件",
    ]
    if events:
        for event in events:
            lines.append(f"- {event.get('timestamp', '')} `{event.get('type', '')}` {json.dumps(event.get('payload', {}), ensure_ascii=False)}")
    else:
        lines.append("- AO events API 沒有提供本 turn 的 tool/task 細節事件。")
    if child_sessions:
        lines.append("")
        lines.append("### 3. Subagent Child Sessions")
        for child in child_sessions:
            lines.append(f"- `{child.get('id', '')}` name={child.get('name', '')} parent={child.get('parent_id', '')}")
        lines.append("- 注意：目前只看得到 child session metadata，還看不到 child session 內的思考或完整訊息。")
    else:
        lines.append("")
        lines.append("### 3. Subagent Child Sessions")
        lines.append("- 未觀測到新的 child session metadata。可能原因：AO 未暴露、Task Tool 未建立可列出的 child session，或本 probe 是 moderator 自己 resolution。")
    lines.extend(
        [
            "",
            "### 4. Moderator → Main Session 最終回覆",
            f"- Message ID：{response.get('message_id', '')}",
            "",
            "```text",
            str(response.get("text", "")).strip(),
            "```",
            "",
            "### 5. Skill / JSON Extraction",
            "- 本 probe 目前只測單一會議 turn，尚未接續呼叫 extraction skill。",
            "- 完整 pipeline 應在 moderator resolution 後，另送 extraction skill call，並把結果記到同一份 timeline。",
            "",
            "## 可取得與不可取得",
            "- 可取得：Python 給 moderator 的精簡輸入、AO lifecycle events、session/child-session metadata、main session 最終回覆。",
            "- 不可取得：subagent 私有 child session 的腦內思考或 hidden chain-of-thought，除非 AO/OpenCode 額外提供可審計 trace API。",
            "- 可建議 AO 補強：提供 Task Tool invocation trace、subagent final output、tool result 摘要，以及可選的 debug transcript。",
        ]
    )
    if errors:
        lines.extend(["", "## 擷取錯誤"])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"


def _flatten_children(state: dict[str, Any]) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    raw = state.get("children_by_session", {})
    if isinstance(raw, dict):
        for entries in raw.values():
            if isinstance(entries, list):
                children.extend(item for item in entries if isinstance(item, dict))
    return children


def _new_events(before: Any, after: Any) -> list[dict[str, Any]]:
    if not isinstance(before, list) or not isinstance(after, list):
        return []
    before_keys = {_event_key(event) for event in before if isinstance(event, dict)}
    return [event for event in after if isinstance(event, dict) and _event_key(event) not in before_keys]


def _event_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("type", "")),
        str(event.get("timestamp", "")),
        json.dumps(event.get("payload", {}), sort_keys=True, default=str),
    )


def build_prompt_payload(case: ProbeCase, *, context_mode: str) -> dict[str, Any]:
    base = {
        "task": "Moderator-only prompt eval: use the Task Tool to delegate this probe, then return only the delegated subagent's final output for manual review.",
        "ao_route": "moderator",
        "delegation_required": True,
        "delegated_agent": case.delegated_agent,
        "phase_name": case.phase,
        "phase_goal": case.phase_goal,
        "agent_role": case.delegated_agent,
        "turn_kind": case.turn_kind,
        "user_task": case.user_task,
        "expected_behavior": case.expected_behavior,
        "risk_being_tested": case.risk,
        "moderator_instructions": [
            f"Invoke `{case.delegated_agent}` with the Task Tool unless this is a pure moderator resolution probe.",
            "Let the delegated subagent reason in its own child session.",
            "Return only the final result that should appear in the main meeting session.",
            "Do not narrate Task Tool usage or child-session reasoning.",
        ],
        "output_contract": {
            "format": "plain meeting text",
            "required_sections": required_sections(case.turn_kind),
            "single_turn_only": True,
            "do_not_return_json": True,
            "no_delegation_narration": True,
        },
    }
    context = context_for_mode(case, context_mode)
    base["context_mode"] = context_mode
    base["provided_context"] = context
    return base


def context_for_mode(case: ProbeCase, context_mode: str) -> dict[str, Any]:
    compact = {
        "allowed_families": case.base_context.get("allowed_families", []),
        "accepted_decisions": case.base_context.get("accepted_decisions", []),
        "open_issues": case.base_context.get("open_issues", []),
        "last_resolution_summary": case.base_context.get("last_resolution_summary", ""),
    }
    if context_mode == "compact":
        return compact
    if context_mode == "focused-task":
        return {
            "current_question": case.expected_behavior,
            "blocking_risk": case.risk,
            "allowed_families": case.base_context.get("allowed_families", []),
        }
    if context_mode == "long-context":
        return {
            **case.base_context,
            "conversation_excerpt": long_context_excerpt(case),
            "prior_round_summaries": [
                "Round 1 proposal introduced a minimal interpretation.",
                "Round 1 challenge raised possible edge cases and optional decomposition.",
                "Round 1 response clarified that optional complexity should not override the user task.",
                "Round 1 resolution must decide what remains in scope.",
            ],
        }
    return {
        **case.base_context,
        "meeting_state": {
            "phase_name": case.phase,
            "goal": case.phase_goal,
            "current_round": 1,
            "accepted_decisions": case.base_context.get("accepted_decisions", []),
            "open_issues": case.base_context.get("open_issues", []),
            "last_resolution_summary": case.base_context.get("last_resolution_summary", ""),
        },
        "conversation_excerpt": long_context_excerpt(case)[-3:],
    }


def long_context_excerpt(case: ProbeCase) -> list[dict[str, str]]:
    if case.name == "moderator.over_complexity_rejection":
        return [
            {"speaker": "designer", "content": str(case.base_context.get("proposal", ""))},
            {"speaker": "reviewer", "content": str(case.base_context.get("challenge", ""))},
            {"speaker": "designer", "content": str(case.base_context.get("response", ""))},
        ]
    return [
        {"speaker": "system", "content": f"User task: {case.user_task}"},
        {"speaker": case.delegated_agent, "content": f"Proposal should satisfy: {case.expected_behavior}"},
        {"speaker": "reviewer", "content": f"Challenge only if blocking: {case.risk}"},
        {"speaker": case.delegated_agent, "content": "Response should keep the task scoped to accepted deliverables."},
        {"speaker": "moderator", "content": "Resolution should accept minimal executable decisions and reject optional complexity."},
    ]


def required_sections(turn_kind: str) -> list[str]:
    if turn_kind == "resolution":
        return ["Decision", "Accepted", "Rejected", "Open Issues"]
    if turn_kind == "challenge":
        return ["Concern", "Impact"]
    if turn_kind == "response":
        return ["Response", "Revision"]
    return ["Proposal", "Rationale"]


def list_opencode_documents() -> list[dict[str, str]]:
    root = REPO_ROOT / ".opencode"
    documents: list[dict[str, str]] = []
    for path in sorted(root.rglob("*.md")) + sorted(root.glob("opencode.json")):
        if path.is_file():
            documents.append(
                {
                    "path": path.relative_to(REPO_ROOT).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return documents


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_comment_template(path: Path, *, template_path: Path, request: dict[str, Any], case: ProbeCase) -> None:
    template = template_path.read_text(encoding="utf-8-sig")
    tested_docs = "\n".join(f"  - {item['path']} ({item['sha256'][:12]})" for item in request["tested_documents"])
    preface = (
        "<!--\n"
        "此檔案由 run_meeting_probe.py 產生。請由 Codex 讀取 response.txt 後，以繁體中文填寫評論。\n"
        "-->\n\n"
    )
    replacements = {
        "- 評估 ID：": f"- 評估 ID：{request['eval_id']}",
        "- 日期：": f"- 日期：{request['created_at']}",
        "- AO URL：": f"- AO URL：{request['ao_url']}",
        "- 模型：": f"- 模型：{request['model']}",
        "- Conversation ID：": f"- Conversation ID：{request['conversation_id']}",
        "- 測試案例：": f"- 測試案例：{request['case']}",
        "- Phase：": f"- Phase：{request['phase']}",
        "- Agent：": f"- Agent：{request['delegated_agent']} (AO route: {request['ao_agent']})",
        "- Turn 類型：": f"- Turn 類型：{request['turn_kind']}",
        "- 本次測試文件：": f"- 本次測試文件：\n{tested_docs}",
        "- 上下文模式：baseline / compact / long-context / focused-task": f"- 上下文模式：{request['context_mode']}",
        "- 使用者任務：": f"- 使用者任務：{case.user_task}",
        "- Phase 目標：": f"- Phase 目標：{case.phase_goal}",
        "- 預期行為：": f"- 預期行為：{case.expected_behavior}",
        "- 本次測試風險：": f"- 本次測試風險：{case.risk}",
        "- Request JSON：": "- Request JSON：`request.json`",
        "- Response Text：": "- Response Text：`response.txt`",
    }
    rendered = template
    for old, new in replacements.items():
        rendered = rendered.replace(old, new)
    path.write_text(preface + rendered, encoding="utf-8-sig")

if __name__ == "__main__":
    raise SystemExit(main())

