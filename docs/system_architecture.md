# System Architecture

The active runtime is a single Agent Orchestrator-backed `multi_expert`
pipeline. Python is the coordinator and execution authority; Agent Orchestrator
hosts the meeting agents.

## Runtime Ownership

- Agent Orchestrator owns agent sessions, moderator/subagent execution, and
  model calls.
- Python owns phase sequencing, AO provisioning, Markdown artifacts, todo and
  coverage state, checkpoint/session persistence, Blender/MCP execution, and
  validation.
- React UI owns user interaction, settings, session navigation, activity
  rendering, runtime log, and inspector panels.

## Main Flow

1. User starts a task from CLI or React UI.
2. Python creates or reuses a session runtime directory.
3. Python provisions AO config, root `AGENTS.md`, agent markdown files, and
   active skills.
4. Python starts AO and waits for the conversation to become ready.
5. Python runs Design, Spec, Plan, Build, Builder placement execution, and
   Validate phases.
6. Meeting phases produce Markdown handoff documents.
7. Python maintains a thin `artifact_index.json`, todo state, and progress
   snapshot for UI/bridge consumption.
8. Builder returns one-step Markdown operations. Python maps these to allowed
   Blender actions, executes through ObjectOps/MCP, and validates scene state.

## AO Agent Model

- `moderator` is the only main-session AO route.
- `designer`, `specifier`, `planner`, `reviewer`, `builder`, and `inspector`
  are subagents invoked by the moderator through Task Tool delegation.
- Subagent internal context should remain in child sessions; main session stores
  only the final meeting utterance or builder operation.

## Artifacts

Runtime artifacts live under:

```text
data/runtime/session_data/<session-id>/artifacts/
```

Core files:

- `design.md`
- `spec.md`
- `build_plan.md`
- `todo.md`
- `build_log.md`
- `final_report.md`
- `artifact_index.json`

Markdown is the agent/human source of truth. JSON exists only for Python/UI
metadata, validation, and executable action handoff.

## Blender Execution

The system has two execution modes:

- `SimulatedBlenderObjectOps` for tests and local non-Blender checks.
- Blender MCP-backed object operations for live Blender runs.

Builder does not directly control Blender. It writes a single Markdown
operation for the current todo; Python parses, validates, executes, and records
the result.

## UI And Progress

The UI keeps the existing `MultiStageProgressSnapshot` wire name for
compatibility. `workflow_type` remains `multi_stage_modeling`, and
`multi_expert_mode` is always `true`.

Progress and activity are exposed through the GUI bridge REST/WebSocket API.
Conversation Surface shows short summaries by default and keeps full AO
responses in expandable detail.

## Deprecated Paths

Removed pipeline variants and local expert prompting notes are not active
runtime paths. Related docs are archived under [`archive/`](archive/index.md).
