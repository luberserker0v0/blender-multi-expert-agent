# Blender Assembly Capabilities

This document is the maintained source of truth for Builder placement capabilities.

Supported placement action types:
- `show_object`: parameters `name`.
- `hide_object`: parameters `name`.
- `move_object`: parameters `name`, `location` as `[x, y, z]`.
- `rotate_object`: parameters `name`, `rotation_degrees` as `[x, y, z]`.
- `set_parent`: parameters `child_name`, `parent_name`.
- `set_object_scale`: parameters `name`, `scale` as `[x, y, z]`.
- `create_collection`: parameters `name`.
- `move_to_collection`: parameters `object_name`, `collection_name`.

Rules:
- Do not invent action types.
- Only reference object names produced by build artifacts or earlier placement actions.
- Parent objects must exist before `set_parent`.
- If an attachment relation is unclear, return `needs_revision`.
- If a geometric operation is unavailable, return `blocked`.
