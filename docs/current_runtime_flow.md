# Current Runtime Flow

This page is the short operational map for the active AO-backed multi-expert
runtime.

## Flow

```mermaid
flowchart TD
    User["User in CLI or React UI"] --> Bridge["Bridge / run_pipeline"]
    Bridge --> Python["Python Pipeline Coordinator"]
    Python --> AO["Agent Orchestrator Conversation"]
    AO --> Moderator["moderator primary agent"]
    Moderator --> Designer["designer subagent via Task Tool"]
    Moderator --> Specifier["specifier subagent via Task Tool"]
    Moderator --> Planner["planner subagent via Task Tool"]
    Moderator --> Reviewer["reviewer subagent via Task Tool"]
    Moderator --> Builder["builder subagent via Task Tool"]
    Designer --> Moderator
    Specifier --> Moderator
    Planner --> Moderator
    Reviewer --> Moderator
    Builder --> Moderator
    Moderator --> Python
    Python --> Artifacts["Markdown artifacts and thin index"]
    Python --> Todos["Python-owned todo / coverage checklist"]
    Todos --> BuilderTurn["One builder todo at a time"]
    BuilderTurn --> Python
    Python --> Parser["Intent parser and capability validator"]
    Parser --> MCP["Blender MCP / ObjectOps execution"]
    MCP --> SceneCheck["Scene validation"]
    SceneCheck --> Progress["Progress snapshot / runtime log / UI activity"]
```

## Responsibilities

- React UI and CLI collect task input and start a session.
- Python owns phase sequencing, AO provisioning, artifact persistence, todo
  state, MCP execution, scene validation, and progress snapshots.
- AO owns model calls, moderator behavior, and subagent task delegation.
- `moderator` is the only main-session agent used by Python.
- Subagents think in child sessions through the Task Tool; the main session keeps
  only their returned conclusions.
- Markdown artifacts are the human/agent source of truth.
- `artifact_index.json` is thin Python/UI metadata, not an agent-authored
  artifact.
- Builder never controls Blender directly. It writes one operation intent for
  the current todo; Python maps that intent to allowed MCP/ObjectOps calls.

## Active Session Artifacts

The runtime writes these under the session artifact directory:

- `design.md`
- `spec.md`
- `build_plan.md`
- `todo.md`
- `build_log.md`
- `final_report.md`
- `artifact_index.json`

## Failure Boundary

If AO readiness, message delivery, parsing, capability validation, MCP execution,
or scene validation fails, Python records the failure in session runtime state.
The UI should show that state through the existing progress/activity surfaces.
