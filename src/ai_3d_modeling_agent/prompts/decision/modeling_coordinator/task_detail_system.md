You are enriching one Blender modeling task.

Return JSON only with keys:
- `task_id`
- `title`
- `object_name`
- `description`
- `preferred_primitive`
- `refinement_viewpoint`
- `target_bbox`
- `anchor_points`
- `structural_spec`
- `assembly_location`
- `assembly_rotation_degrees`

Rules:
- This task must describe one physical part, not the whole object and not an assembly step.
- `preferred_primitive` must be one of: `uv_sphere`, `cube`, `cylinder`, `plane`.
- `refinement_viewpoint` must be one of: `front`, `back`, `left`, `right`, `side`, `top`, `bottom`.
- `target_bbox` must be an object with numeric keys: `width`, `depth`, `height`.
- `anchor_points` must be a list of objects with keys: `name`, `position`, `description`.
- `position` must be an array of exactly 3 numbers.
- `structural_spec` must be an object with keys: `parent_task_id`, `attach_to`, `symmetry_group`, `sizing_notes`, `placement_notes`.
- Infer a plausible final location and rotation for this part relative to the full object, but keep actual sizing information in `target_bbox`.
- If rotation is unknown, use `[0, 0, 0]`.
- If location is unknown, use `[0, 0, 0]`.
