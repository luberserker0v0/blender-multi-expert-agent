# ADR 0001: AO Moderator-Only Routing

## Status

Accepted.

## Context

Directly sending AO messages with different `agent` values made each expert
appear in the same main session. That mixed expert-specific reasoning and
meeting state in a way that made long sessions harder to inspect and reason
about.

## Decision

Python sends AO `message.send` calls only to `agent: "moderator"`.

The moderator is the primary main-session agent. It uses the OpenCode Task Tool
to invoke subagents such as designer, specifier, planner, reviewer, and builder.
Subagents work in child sessions and return concise conclusions to the moderator.

## Consequences

- Python no longer switches the main session agent per expert turn.
- Main-session history is cleaner and mostly contains requests, returned
  conclusions, resolutions, and artifact text.
- Moderator prompt quality matters more because it owns delegation discipline.
- Tests should assert that AO route remains `moderator`, even when logical
  payloads refer to a delegated role.
