# ADR 0003: Single Builder Execution Agent

## Status

Accepted.

## Context

Separating builder and assembler made the execution flow harder to coordinate.
For current tasks, geometry creation and placement are better handled as one
todo-driven execution loop.

## Decision

Use a single `builder` subagent for geometry creation, placement, assembly, and
step result reporting.

Python splits the build plan into one verifiable todo at a time. Builder writes
a Markdown operation intent for the current todo. Python parses and validates
the intent against capability documents, executes allowed Blender MCP/ObjectOps
calls, validates the scene, and records the result.

## Consequences

- `assembler` is not an active agent.
- Placement helpers may remain in Python as shared execution utilities.
- Builder does not receive responsibility for long, unbounded Blender control.
- Nested or complex objects should be handled by repeated build/placement loops,
  not by one large assembly phase.
