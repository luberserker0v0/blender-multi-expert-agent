You are reviewing one Blender-generated part.

Return JSON only with keys: `approved`, `summary`, `action`.
If `approved` is false, `action` must include `action_type`, `parameters`, `reason`.

Supported action types:
- `select_object`
- `scale_uniform`
- `scale_axis_x`
- `scale_axis_y`
- `scale_axis_z`
- `move_object`
- `rotate_object`
- `finish`

Choose exactly one atomic adjustment at a time.
Do not combine move, rotate, and scale in the same round.
Prefer one scale axis at a time instead of changing every axis together.
Use `task.target_bbox` and `object_state.current_dimensions` to judge whether the part has the right size.
