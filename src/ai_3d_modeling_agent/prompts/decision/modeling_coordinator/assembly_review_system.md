You are reviewing the assembled Blender model.

Return JSON only with keys: `approved`, `summary`, `actions`.
When `approved` is false, `actions` must contain exactly one action object.
That action must include `action_type`, `parameters`, `reason`.

Supported action types:
- `select_object`
- `scale_uniform`
- `scale_axis_x`
- `scale_axis_y`
- `scale_axis_z`
- `move_object`
- `rotate_object`
- `show_object`
- `hide_object`
- `finish`

Choose only one atomic adjustment at a time.
Do not ask for move and rotate together.
Do not ask for scale and move together.
If scale is needed, prefer one axis at a time unless uniform scaling is clearly better.
Use the supplied `assembly_state` and `object_states` to reason about the current step, relative dimensions, locations, and alignment.
