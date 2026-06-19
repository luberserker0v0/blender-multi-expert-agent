"""Run the multi-expert pipeline from command line.

Usage::

    # Use settings file
    python scripts/run_pipeline.py --settings settings.json --task "build a chair"

    # Override specific settings
    python scripts/run_pipeline.py --settings settings.json --task "build a table" --agent-orchestrator-model gpt-4

    # Pure CLI (no settings file)
    python scripts/run_pipeline.py --task "build a chair" --agent-orchestrator-url http://localhost:4111

    # Use saved GUI settings
    python scripts/run_pipeline.py --task "build a chair" --use-gui-settings
"""

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the multi-expert 3D modeling pipeline.",
    )
    parser.add_argument(
        "--task",
        default="",
        help="Task prompt (e.g. 'build a simple table').",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Path to a JSON settings file.",
    )
    parser.add_argument(
        "--use-gui-settings",
        action="store_true",
        help="Use the saved GUI settings from data/runtime/gui/saved_settings.json.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID (auto-generated if not provided).",
    )
    parser.add_argument("--max-part-refinement-rounds", default=None)
    parser.add_argument("--max-assembly-rounds", default=None)
    parser.add_argument("--reference-text", action="append", default=[])
    parser.add_argument("--reference-image", action="append", default=[])

    ao_group = parser.add_argument_group("Agent Orchestrator settings")
    ao_group.add_argument("--agent-orchestrator-url", default=None)
    ao_group.add_argument("--agent-orchestrator-model", default=None)
    ao_group.add_argument("--agent-orchestrator-conversation-id", default=None)
    ao_group.add_argument("--agent-orchestrator-timeout-seconds", type=int, default=None)
    ao_group.add_argument("--keep-agent-orchestrator-conversation", action="store_true")

    # Blender MCP settings
    mcp_group = parser.add_argument_group("Blender MCP settings")
    mcp_group.add_argument("--use-blender-mcp", action="store_true", default=None)
    mcp_group.add_argument("--blender-mcp-command", default=None)
    mcp_group.add_argument("--blender-mcp-cwd", default=None)
    mcp_group.add_argument("--blender-mcp-arg", action="append", default=[])
    mcp_group.add_argument("--blender-mcp-env", action="append", default=[])

    yolo_group = parser.add_argument_group("YOLO settings")
    yolo_group.add_argument("--use-yolo-perception", action="store_true", default=None)
    yolo_group.add_argument("--yolo-model-path", default=None)
    yolo_group.add_argument("--yolo-viewpoint", action="append", default=[])

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Determine settings path
    settings_path = args.settings
    if args.use_gui_settings:
        gui_path = REPO_ROOT / "data" / "runtime" / "gui" / "saved_settings.json"
        if gui_path.exists():
            settings_path = str(gui_path)
        else:
            print(f"Warning: GUI settings not found at {gui_path}", file=sys.stderr)

    # Build overrides from CLI args
    overrides = {}
    if args.task:
        overrides["task"] = args.task
    if args.session_id:
        overrides["session_id"] = args.session_id
    if args.agent_orchestrator_url is not None:
        overrides["agent_orchestrator_base_url"] = args.agent_orchestrator_url
    if args.agent_orchestrator_model is not None:
        overrides["agent_orchestrator_model"] = args.agent_orchestrator_model
    if args.agent_orchestrator_conversation_id is not None:
        overrides["agent_orchestrator_conversation_id"] = args.agent_orchestrator_conversation_id
    if args.agent_orchestrator_timeout_seconds is not None:
        overrides["agent_orchestrator_timeout_seconds"] = args.agent_orchestrator_timeout_seconds
    if args.keep_agent_orchestrator_conversation:
        overrides["agent_orchestrator_destroy_on_finish"] = False
    if args.use_blender_mcp is not None:
        overrides["use_blender_mcp"] = args.use_blender_mcp
    if args.blender_mcp_command is not None:
        overrides["blender_mcp_command"] = args.blender_mcp_command
    if args.blender_mcp_cwd is not None:
        overrides["blender_mcp_cwd"] = args.blender_mcp_cwd
    if args.blender_mcp_arg:
        overrides["blender_mcp_args"] = list(args.blender_mcp_arg)

    try:
        from ai_3d_modeling_agent.io.settings_loader import load_settings, settings_to_run_pipeline_kwargs
        from ai_3d_modeling_agent.pipelines.runners import run_pipeline

        settings = load_settings(settings_path, overrides=overrides)
        kwargs = settings_to_run_pipeline_kwargs(settings)

        if not kwargs.get("task"):
            print("Error: --task is required (or provide it in the settings file).", file=sys.stderr)
            return 1

        if not kwargs.get("session_id"):
            import time
            kwargs["session_id"] = f"cli-{int(time.time())}"

        print(f"Task: {kwargs['task']}")
        print(f"Session: {kwargs['session_id']}")
        print(f"Agent Orchestrator: {kwargs.get('agent_orchestrator_base_url', 'none')}")
        print(f"MCP: {kwargs.get('use_blender_mcp', False)}")
        print()

        result = run_pipeline(**kwargs)

        print()
        print("=== Pipeline Result ===")
        print(f"Status: {result.status}")
        print(f"Design parts: {len(result.design.parts) if result.design else 0}")
        print(f"Spec parts: {len(result.specs.parts) if result.specs else 0}")
        print(f"Build results: {len(result.build_results)}")
        print(f"Assembly results: {len(result.assembly_results)}")
        print(f"Validation passed: {result.validation.passed if result.validation else 'N/A'}")

        return 0 if str(result.status) == "PipelineStatus.SUCCESS" else 1

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
