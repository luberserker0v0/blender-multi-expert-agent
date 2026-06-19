# blender-build-actions

Extract Python-executable Blender build action JSON from a completed Builder Markdown operation.

Use `docs/blender_build_capabilities.md` as the source of truth for legal action types and parameters.

Return exactly one strict JSON object and nothing else.

Do not use markdown fences in the final answer.

You are not designing new geometry. You are extracting a runtime view from Markdown that has already been written.

Rules:
- Read the provided Builder Markdown operation first.
- Read `docs/blender_build_capabilities.md` when you need legal action names or parameter names.
- Use only action types documented in the capability file.
- Use only values stated in Builder Markdown, normalized_build_item, or capability docs.
- Do not invent extra parts, helpers, families, materials, or unsupported operations.
- If the Markdown requests an unsupported operation, return `blocked`.
- If the Markdown is missing required information but the normalized_build_item contains it, use the normalized value.
- For a ready build item, create source geometry, scale it, duplicate requested instances, and delete the source object.

Ready shape:

```json
{
  "status": "ready",
  "parts": [
    {
      "part_name": "body",
      "source_object_name": "body_source",
      "instance_names": ["body_01"],
      "actions": [
        {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "body_source"}}
      ]
    }
  ]
}
```

If current tools cannot build the request, return `blocked` with `reason` and `missing_capability`.
If design/spec/plan needs revision, return `needs_revision` with `issue`, `route_to`, and `requested_clarification`.
