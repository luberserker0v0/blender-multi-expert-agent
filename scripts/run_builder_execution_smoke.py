"""Run an AO-backed Builder execution smoke test.

This smoke uses the production pipeline entrypoint but checks the Markdown-first
handoff artifacts that matter for Builder execution: todo.md and build_log.md.
By default it uses SimulatedBlender; pass --use-blender-mcp to exercise Blender.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


DEFAULT_SMOKE_TASK = (
    "Create a simple chair with one square seat, four cylindrical legs, and one rectangular backrest. "
    "Use these accepted dimensions: seat 0.45 m wide x 0.45 m deep x 0.08 m thick; "
    "each leg 0.05 m diameter x 0.75 m high; "
    "backrest 0.45 m wide x 0.08 m deep x 0.55 m high. "
    "Place the seat at the origin, attach the four legs under the seat corners, and place the backrest behind the seat."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Builder execution smoke test.")
    parser.add_argument("--agent-orchestrator-url", required=True)
    parser.add_argument("--agent-orchestrator-model", default="")
    parser.add_argument("--task", default=DEFAULT_SMOKE_TASK)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--keep-agent-orchestrator-conversation", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--use-blender-mcp", action="store_true")
    parser.add_argument("--blender-mcp-command", default="uv")
    parser.add_argument("--blender-mcp-cwd", default="")
    parser.add_argument("--blender-mcp-arg", action="append", default=[])
    return parser


def main() -> int:
    from ai_3d_modeling_agent.pipelines.runners import run_pipeline

    args = build_parser().parse_args()
    session_id = args.session_id or f"builder-smoke-{int(time.time())}"
    result = run_pipeline(
        task=args.task,
        session_id=session_id,
        agent_orchestrator_base_url=args.agent_orchestrator_url,
        agent_orchestrator_model=args.agent_orchestrator_model,
        agent_orchestrator_destroy_on_finish=not args.keep_agent_orchestrator_conversation,
        agent_orchestrator_timeout_seconds=args.timeout_seconds,
        use_blender_mcp=args.use_blender_mcp,
        blender_mcp_command=args.blender_mcp_command,
        blender_mcp_cwd=args.blender_mcp_cwd,
        blender_mcp_args=list(args.blender_mcp_arg or []),
    )

    artifact_root = REPO_ROOT / "data" / "runtime" / "session_data" / session_id / "artifacts"
    todo_path = artifact_root / "todo.md"
    build_log_path = artifact_root / "build_log.md"

    print("=== Builder Execution Smoke ===")
    print(f"Session: {session_id}")
    print(f"Status: {result.status}")
    print(f"Build results: {len(result.build_results)}")
    print(f"Assembly results: {len(result.assembly_results)}")
    print(f"Artifacts: {artifact_root}")
    print()

    missing = [str(path) for path in (todo_path, build_log_path) if not path.exists()]
    if missing:
        print("Missing expected artifacts:")
        for path in missing:
            print(f"- {path}")
        return 1

    todo_text = todo_path.read_text(encoding="utf-8")
    build_log_text = build_log_path.read_text(encoding="utf-8")
    print("todo.md preview:")
    print("\n".join(todo_text.splitlines()[:20]))
    print()
    print("build_log.md preview:")
    print("\n".join(build_log_text.splitlines()[:30]))

    if "Builder todo" not in build_log_text:
        print("\nNo Builder todo entries were written to build_log.md.")
        return 1
    status_name = getattr(result.status, "name", str(result.status)).upper()
    status_value = getattr(result.status, "value", str(result.status)).upper()
    if "SUCCESS" not in {status_name, status_value}:
        print(f"\nPipeline did not finish successfully: {result.status}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
