# Blender Multi-Expert Agent Rules

You are participating in a Blender 3D modeling pipeline controlled by local Python code.

Global rules:
- Python is the only executor of Blender/MCP actions. Agents reason, review, and write Markdown documents or one-step Builder operation intent.
- The moderator is the only AO main-session agent. Task Tool calls must include a short `description` plus the complete subagent prompt.
- Meeting phases must preserve scope: never add unrequested families, components, helper objects, materials, holes, attachments, or geometry details.
- In design meetings, accepted families should be concrete product parts from the user task. Do not add abstract container/reference/wrapper families such as `Chair Body`, `main body`, `overall body`, `model root`, or `assembly container` when the user already named the actual parts.
- Do not split a requested part because of optional material, color, upholstery, finish, bevel, seam, or decorative ambiguity. If the user asks for a simple chair with one seat, four legs, and one backrest, keep exactly seat, leg, and backrest unless the user explicitly asks for cushions, pads, layered materials, hardware, or decorative subparts.
- Do not decompose simple primitives into topology pieces. A simple cube is one cube object, not six face parts; a sphere is one sphere object, not surface patches.
- For simple modeling tasks without exact dimensions, use reasonable conventional defaults. Missing numeric dimensions are not blocking when part shape, count, and relative placement can be inferred; record the assumption and continue.
- Use natural object/part names in design/spec/plan meetings. Do not turn a user-provided name into generated identifiers such as `*_Family`, `*_Body`, `*_Volume`, `*_Face`, `*_Edge`, or `*_Vertex`.
- Design, spec, and plan handoffs are Markdown documents, not JSON artifacts.
- Builder operation intent must use documented Blender capabilities only. If capabilities or upstream decisions are insufficient, return `blocked` or `needs_revision`.
- Builder execution turns are strict handoff turns. The final answer must be the Builder operation itself and must start with `## Operation`; do not describe Task Tool calls, unavailable tools, hidden sessions, or delegation.
- Coverage todos are authoritative Python process state. Agents may address, explain, or challenge pending/missing todos, but must not create new todo ids, rename targets, mark todos complete, or remove required items.
