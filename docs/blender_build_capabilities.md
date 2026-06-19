# Blender Build Capabilities

This document is the maintained source of truth for builder agent capabilities.

Supported build action types:
- `create_primitive`: parameters `primitive_type`, `name`.
- `create_uv_sphere`: parameters `name`.
- `set_object_scale`: parameters `name`, `scale` as `[x, y, z]`.
- `duplicate_object`: parameters `name`, `new_name`.
- `delete_object`: parameters `name`.
- `hide_object`: parameters `name`.
- `show_object`: parameters `name`.
- `move_object`: parameters `name`, `location` as `[x, y, z]`.
- `rotate_object`: parameters `name`, `rotation_degrees` as `[x, y, z]`.
- `mirror_object`: parameters `name`, `axis`.

Rules:
- Do not invent action types.
- Use stable object names.
- Create source objects before duplicating them.
- Reference only objects created earlier in the action list or known from prior build artifacts.
- If a needed operation is missing, return `blocked`.

