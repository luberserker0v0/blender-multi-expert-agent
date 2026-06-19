# ADR 0004: Python-Owned Todo And Coverage State

## Status

Accepted.

## Context

The project needs divide-and-conquer behavior without asking agents to solve the
whole object at once. Meeting output should become concrete follow-up work, and
missing parts should be detected by the process rather than by hope.

## Decision

Python owns todo and coverage state. It derives checklists from accepted
Markdown artifacts, persists them in runtime state, and passes focused subsets
to AO for the next turn.

Agents may discuss todo items and propose work, but Python is the authority for
todo status, coverage gaps, retry decisions, and whether a build step has passed
scene validation.

## Consequences

- Design parts can become spec coverage todos.
- Spec parts can become plan/build todos.
- Builder receives one current todo, not the entire unresolved object.
- Missing required coverage becomes an open issue or failure note instead of
  silently passing.
