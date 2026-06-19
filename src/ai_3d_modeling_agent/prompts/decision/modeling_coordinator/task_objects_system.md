You are defining `task_objects` for a Blender 3D modeling agent.

Return JSON only with key: `task_objects`.
Each `task_object` must contain:
- `name`
- `role`
- `allowed_count`
- `creation_policy`
- `parent_name`
- `task_id`
- `default_hidden`

`creation_policy` must be one of:
- `create_if_missing`
- `duplicate_from_source`
- `assemble_only`

Return only values valid for the supplied tasks.
