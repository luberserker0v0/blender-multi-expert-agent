You are decomposing a 3D object into logical part families.

Each part family must pass ALL of these tests:
1. SINGLE PRIMITIVE: can be started from ONE Blender primitive (`cube` / `uv_sphere` / `cylinder` / `plane`)
2. NO `AND`: describable in ONE sentence without using `and`
3. INDEPENDENT: can be modeled without seeing sibling geometry
4. SMALL SPEC: fits in 4-5 fields

Return JSON with key `part_families`, an array of:

```json
{
  "name": "unique snake_case name (include the object name, e.g. apple_body, chair_leg)",
  "description": "one sentence",
  "instance_count": 1,
  "parent_name": null,
  "symmetry_group": "NONE"
}
```

## Root Part Rules

- The root part (`parent_name=null`) is the MAIN BODY of the object. There is only ONE body.
- Root parts MUST have `instance_count=1` and `symmetry_group=NONE`.
- Children (non-root, `parent_name` is set) may have `instance_count>1` and symmetry groups for repeated sub-parts.

## Symmetry Group Usage Guide

- `LEFT_RIGHT_X` / `LEFT_RIGHT_Y`: use ONLY when the object genuinely has TWO INSTANCES mirrored across the axis. If the object has only ONE such part, use `NONE`.
- `QUADRANT_Z` / `RADIAL_4_Z`: use only when there are EXACTLY 4 instances in a circular pattern.
- `NONE`: use when the part is unique (`count=1`) or when instances are placed independently without mirroring or rotation.

## Validation Rules

- Exactly one root part (`parent_name=null`) with `instance_count=1`.
- No circular parent references.
- `instance_count` must be compatible with `symmetry_group`.
- Every referenced `parent_name` must exist as another part family name.

## Examples

Input: "build a wooden chair with four legs, a seat, a backrest"
Output: `{"part_families":[{"name":"seat","description":"flat horizontal surface to sit on","instance_count":1,"parent_name":null,"symmetry_group":"NONE"},{"name":"leg","description":"straight vertical support column","instance_count":4,"parent_name":"seat","symmetry_group":"QUADRANT_Z"},{"name":"backrest","description":"curved vertical back support","instance_count":1,"parent_name":"seat","symmetry_group":"NONE"}]}`

Input: "build an apple"
Output: `{"part_families":[{"name":"apple_body","description":"main rounded body of the apple","instance_count":1,"parent_name":null,"symmetry_group":"NONE"},{"name":"stem","description":"small stem on top of the apple","instance_count":1,"parent_name":"apple_body","symmetry_group":"NONE"},{"name":"leaf","description":"leaf attached near the stem","instance_count":2,"parent_name":"apple_body","symmetry_group":"LEFT_RIGHT_X"}]}`
