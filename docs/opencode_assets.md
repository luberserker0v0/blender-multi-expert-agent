# OpenCode / AO Assets

This page documents the repository-owned `.opencode/` assets used by Agent
Orchestrator provisioning.

## Source Of Truth

- Shared rules: [`.opencode/AGENTS.md`](../.opencode/AGENTS.md)
- Local provider config: [`.opencode/opencode.json`](../.opencode/opencode.json)
- Agent definitions: [`.opencode/agents/`](../.opencode/agents/)
- Skill definitions: [`.opencode/skills/`](../.opencode/skills/)

Python provisions these assets into each AO conversation before starting a run.
The AO workspace copy is runtime state; the repo copy is the source of truth.

## Active Agents

- `moderator`
  Primary main-session agent. Owns meeting flow, Task Tool delegation,
  resolution, and concise final responses.
- `designer`
  Subagent for design-phase proposals and revisions.
- `specifier`
  Subagent for turning accepted design decisions into specification detail.
- `planner`
  Subagent for build strategy and ordered todo planning.
- `reviewer`
  Subagent for challenge turns and quality review.
- `builder`
  Subagent for one-step build/placement operation intent.
- `inspector`
  Subagent for validation-oriented review and final inspection.

`assembler` is not an active agent. Geometry creation, placement, and assembly
responsibility are consolidated into `builder`.

## Active Skills

- `summarize-meeting-message`
  UI readability skill. It summarizes a completed meeting turn into a short
  Traditional Chinese conclusion for the Conversation Surface. It does not
  create artifact truth and must not change decisions.

## Deprecated Or Reference Skills

The following skills may remain in the repository as historical or tooling
references, but are not part of the active Markdown-first runtime contract:

- `blender-build-actions`
- `blender-assembly-actions`

These came from the older JSON action extraction flow. Active Builder execution
uses Markdown operation intent plus Python parsing, capability validation, and
MCP/ObjectOps execution.

## Development-Only Skills

- `playwright-mcp-e2e`
  Local testing/development helper for Playwright MCP e2e work. It is not part
  of the Blender modeling runtime.

## Provisioning Rules

- Python sends AO messages only to `moderator`.
- `moderator` invokes subagents through Task Tool.
- Active run provisioning should not upload deprecated JSON extraction/action
  skills unless the runtime explicitly reintroduces them.
- Agents must not execute Blender/MCP directly. Python remains the executor.
- Capability docs under `docs/blender_*_capabilities.md` define what Builder may
  plan against.
