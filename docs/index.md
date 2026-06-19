# Documentation Index

This is the current documentation map for the Blender multi-expert modeling
agent. Prefer these active documents before opening archived design notes.

## Current Read Order

1. [`../README.md`](../README.md)
   Quick start, local commands, CI/CD, CLI, and React UI startup.
2. [`readme_index.md`](readme_index.md)
   Index of README files and their intended scope.
3. [`system_architecture.md`](system_architecture.md)
   Current runtime architecture and ownership boundaries.
4. [`current_runtime_flow.md`](current_runtime_flow.md)
   Short operational flow from UI/CLI through AO, Markdown artifacts, todos, and
   Blender MCP execution.
5. [`agent_orchestrator_multi_expert.md`](agent_orchestrator_multi_expert.md)
   Agent Orchestrator provisioning, agent roles, and moderator-only routing.
6. [`opencode_assets.md`](opencode_assets.md)
   Active AO/OpenCode agents, skills, and provisioning rules.
7. [`react_ui.md`](react_ui.md)
   React UI, bridge, activity stream, settings, and runtime panels.

## Active Runtime Docs

- [`agent_orchestrator_multi_expert.md`](agent_orchestrator_multi_expert.md)
  Source of truth for AO-backed multi-expert runtime flow.
- [`system_architecture.md`](system_architecture.md)
  Current high-level architecture.
- [`current_runtime_flow.md`](current_runtime_flow.md)
  Runtime flow diagram and responsibility map.
- [`session_and_progress.md`](session_and_progress.md)
  Progress snapshot, session persistence, and recovery notes.
- [`opencode_assets.md`](opencode_assets.md)
  AO/OpenCode asset inventory and active/deprecated skill status.
- [`blender_mcp_integration.md`](blender_mcp_integration.md)
  Current Blender MCP integration path.
- [`blender_build_capabilities.md`](blender_build_capabilities.md)
  Builder-readable build capability manifest.
- [`blender_assembly_capabilities.md`](blender_assembly_capabilities.md)
  Builder-readable placement/assembly capability manifest.
- [`perception_and_yolo.md`](perception_and_yolo.md)
  YOLO/perception notes and current limits.

## UI And Testing

- [`react_ui.md`](react_ui.md)
  Browser UI and bridge behavior.
- [`TEST_TASKS.md`](TEST_TASKS.md)
  Manual/e2e task corpus.
- [`TODO.md`](TODO.md)
  Active follow-up work.

## Decisions

- [`decisions/0001-ao-moderator-only-routing.md`](decisions/0001-ao-moderator-only-routing.md)
  Python routes AO messages only to moderator; subagents are invoked by Task Tool.
- [`decisions/0002-markdown-first-artifacts.md`](decisions/0002-markdown-first-artifacts.md)
  Meeting outputs are Markdown-first, with thin Python-owned metadata.
- [`decisions/0003-single-builder-execution.md`](decisions/0003-single-builder-execution.md)
  Builder owns both geometry and placement as one todo-driven execution role.
- [`decisions/0004-python-owned-todo-coverage.md`](decisions/0004-python-owned-todo-coverage.md)
  Python owns todo status, coverage, and scene-validation truth.
- [`decisions/0005-conda-pip-python-environment.md`](decisions/0005-conda-pip-python-environment.md)
  Python environment management remains conda + pip; `uv` is only an external
  Blender MCP command unless a future migration supersedes this.

## Archive

- [`archive/index.md`](archive/index.md)
  Historical pipeline variants, tkinter prototype notes, draft MCP API notes,
  and older prompt-design notes.

## Source Of Truth Rules

- Current implementation under `src/` wins over docs when they conflict.
- `.opencode/` is the source of truth for AO agent and skill assets.
- `docs/blender_*_capabilities.md` are manually maintained manifests for what
  Builder can plan against.
- Archived docs are for historical context only and should not be used as active
  implementation instructions.
