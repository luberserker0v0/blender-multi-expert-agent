# blender-assembly-actions

Extract Python-executable Blender placement/assembly action JSON from a completed Builder Markdown operation.

Use `docs/blender_assembly_capabilities.md` and `docs/blender_build_capabilities.md` as the source of truth for legal action types and parameters.

Return exactly one strict JSON object and nothing else.

Do not use markdown fences in the final answer.

You are not designing new geometry and you are not changing the build plan. You are extracting a runtime view from Markdown that has already been written.

Rules:
- Read the provided Builder Markdown operation first.
- Read the capability docs when you need legal action names or parameter names.
- Use only action types documented in the capability docs.
- Use only instances, locations, rotations, and parent relationships stated in Builder Markdown, normalized_assembly_item, build_artifact, or capability docs.
- Do not invent extra parts, helpers, families, materials, or unsupported operations.
- If the Markdown requests an unsupported operation, return `blocked`.
- If the Markdown is missing required placement values but normalized_assembly_item contains them, use normalized_assembly_item.
- For every built instance, show it, move it to the resolved world position, rotate it if needed, and set parent only when required.

Ready shape:

```json
{
  "status": "ready",
  "steps": [
    {
      "step_index": 0,
      "placements": [{"part": "body", "instances": ["body_01"]}],
      "actions": [
        {"action_type": "show_object", "parameters": {"name": "body_01"}},
        {"action_type": "move_object", "parameters": {"name": "body_01", "location": [0, 0, 0]}}
      ]
    }
  ]
}
```

If current tools cannot assemble the request, return `blocked` with `reason` and `missing_capability`.
If build/plan/spec needs revision, return `needs_revision` with `issue`, `route_to`, and `requested_clarification`.
