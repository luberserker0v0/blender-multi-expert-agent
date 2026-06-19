# AI 3D Modeling Agent

Implementation workspace for the Blender-based multi-expert 3D modeling agent.

The executable runtime is the Agent Orchestrator-backed `multi_expert`
pipeline. It runs Design, Spec, Plan, Build, Builder placement execution, and
Validate phases while keeping the existing `multi_stage_modeling` UI snapshot
wire format.

Detailed design and engineering documents are organized under
[docs/index.md](docs/index.md). README files are indexed in
[docs/readme_index.md](docs/readme_index.md).

## Environment Setup

From `repo/`:

```powershell
conda env create -f environment.yml
conda activate ai3d-stage2
make install
```

The codebase expects Python 3.10 or newer.

## Run The Pipeline

Start a multi-expert run from the CLI:

```powershell
python scripts/run_pipeline.py --task "build a wooden chair" --session-id cli-chair-001 --agent-orchestrator-url http://127.0.0.1:4111
```

Agent Orchestrator must already be running. The Blender project provisions the
`moderator`, `designer`, `specifier`, `planner`, `reviewer`, `builder`, and
`inspector` agents from `.opencode/` at the start of each run. Python
coordinates phases, Markdown artifacts, todo/checkpoint state, validation, and
Blender execution. AO handles agent turns; Builder returns one-step Markdown
intent while Python maps, executes, and verifies Blender/MCP operations.

```powershell
python scripts/run_pipeline.py --task "build a wooden chair" --agent-orchestrator-url http://127.0.0.1:4111 --agent-orchestrator-model local-model
```

Use Blender MCP when Blender and the MCP add-on are available:

```powershell
python scripts/run_pipeline.py --task "build a wooden chair" --use-blender-mcp --blender-mcp-command uv --blender-mcp-cwd C:\blender_mcp\mcp --blender-mcp-arg=--directory --blender-mcp-arg=C:\blender_mcp\mcp --blender-mcp-arg=run --blender-mcp-arg=blender-mcp
```

Run a focused Builder execution smoke test:

```powershell
python scripts/run_builder_execution_smoke.py --agent-orchestrator-url http://127.0.0.1:4111 --agent-orchestrator-model local-model
```

The smoke writes `design.md`, `spec.md`, `build_plan.md`, `todo.md`,
`build_log.md`, and `artifact_index.json` under
`data/runtime/session_data/<session-id>/artifacts/`.

Useful make targets:

- `make install`: install Python dependencies
- `make test`: run Python unit tests
- `make ci`: run local CI checks
- `make cd`: build local release artifacts
- `make run`: run a default multi-expert task
- `make run-dev`: start the React UI bridge and Vite frontend

## React UI

Run the full local development environment from the repository root:

```powershell
make run-dev
```

This starts the Python UI bridge and the Vite frontend with aligned bridge
origins. Defaults:

- UI: `http://127.0.0.1:5173`
- Bridge HTTP: `http://127.0.0.1:8765`
- Bridge WebSocket: `ws://127.0.0.1:8766`

Optional overrides:

```powershell
$env:AI3D_DEV_UI_PORT='6173'
$env:AI3D_UI_BRIDGE_HTTP_PORT='8875'
$env:AI3D_UI_BRIDGE_WS_PORT='8876'
make run-dev
```

The bridge starts in-process multi-expert runs and streams activity through the
existing browser UI. The UI keeps the current `MultiStageProgressSnapshot`
wire contract for compatibility, with `multi_expert_mode` fixed to `true`.

Frontend commands from `ui/`:

```powershell
npm test
npm run ci
npm run test:e2e
```

## Current Focus

Open follow-up work is tracked in [docs/TODO.md](docs/TODO.md), with emphasis
on Markdown artifact quality, checkpoint/resume, Blender capture population,
and review/refinement quality in the multi-expert pipeline.
