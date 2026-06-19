# ADR 0002: Markdown-First Artifacts

## Status

Accepted.

## Context

Large JSON artifacts were convenient for Python, but fragile for agents. They
encouraged discussion of generated keys and schema details during meetings, and
small formatting errors could fail a run even when the natural-language content
was usable.

## Decision

Design, spec, plan, todo, build log, and final report are Markdown-first
artifacts. Agents primarily read and write Markdown with stable headings.

Python may maintain a thin `artifact_index.json` for runtime metadata and UI
integration. That index is owned by Python, not by agents.

## Consequences

- Meeting quality can focus on object design and build decisions instead of JSON
  key names.
- Python parsing should be narrow and defensive.
- If structured data is needed later, Python may ask AO to extract it from
  Markdown and then validate it in a retry loop.
- Deprecated JSON extraction/action skills should not be part of active
  provisioning unless deliberately reintroduced.
