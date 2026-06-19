# Agent Orchestrator Multi-Expert Runtime

The only executable modeling pipeline is the AO-backed `multi_expert` runtime.
Local Python is the coordinator: it sequences phases, provisions AO assets,
persists progress, maintains Markdown artifacts and thin indexes, validates
phase/todo coverage, and executes Blender/MCP actions. Agent turns are delegated
to Agent Orchestrator.

## Roles

- `moderator` is the primary agent. It controls meeting flow, resolution,
  correction routing, and stop conditions.
- `designer`, `specifier`, `planner`, and `reviewer` participate in design,
  specification, planning, review, and correction meetings.
- `builder` handles both geometry creation and placement. It returns one-step
  Markdown intent; Python maps, executes, and validates the Blender/MCP actions.
- `inspector` participates in validation and execution correction.

## Provisioning

At run start, `run_pipeline` requires `agent_orchestrator_base_url` and performs:

1. `GET /health`
2. `POST /api/conversations`
3. `GET /api/conversations/:id/config`
4. `POST /api/conversations/:id/config` to merge the default AO config with
   project `.opencode/opencode.json`, `default_agent: "moderator"`, and the
   selected AO model when configured
5. `PUT /api/conversations/:id/agent/config` to write shared rules from local
   `.opencode/AGENTS.md` into AO workspace root `AGENTS.md`
6. `PUT /api/conversations/:id/agents` for every `.opencode/agents/*.md`,
   using the file stem as the API `name` because AO writes `{name}.md`
7. `POST /api/conversations/:id/start`
8. Poll `GET /api/conversations/:id` until `ready: true` and `sessionId`
   is present
9. `message.send` with `agent: "moderator"`

The active runtime does not upload `.opencode/skills/*`. Those directories are
kept only as deprecated reference material for the old JSON extraction/action
flow.

## Source Of Truth

- `.opencode/AGENTS.md` contains shared agent rules and is provisioned into AO
  as root `AGENTS.md`.
- `.opencode/opencode.json` contains project OpenCode config additions such as
  local provider definitions and is deep-merged into AO's default config.
- `.opencode/agents/*.md` contains role-specific agent instructions.
- Markdown artifacts under `session_data/<session-id>/artifacts/` are the
  handoff source of truth: `design.md`, `spec.md`, `build_plan.md`, `todo.md`,
  `build_log.md`, and `final_report.md` when present.
- `artifact_index.json` is Python/UI metadata only; agents do not maintain it.
- `docs/blender_build_capabilities.md` and
  `docs/blender_assembly_capabilities.md` define the manual capability
  manifests that Builder must obey for geometry creation and placement.

## Runtime Rules

The active runtime does not call a local OpenAI-compatible LLM endpoint directly.
Legacy LLM settings may be parsed for compatibility, but they do not drive
`run_pipeline`. If AO health, provisioning, start, readiness polling, or
`message.send` fails, the run fails fast rather than falling back to a local LLM.
All AO messages are routed to `moderator`; subagents are invoked through the
moderator's Task Tool rather than by Python switching the main session agent.
