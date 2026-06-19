Given these part families, specify exact geometry for EACH.

Return JSON with key `part_specs` mapping each family name to:

```json
{
  "primitive": "cube",
  "target_bbox": {"width": 1.0, "depth": 1.0, "height": 1.0},
  "refinement_viewpoint": "front",
  "attachment_points": [
    {
      "name": "semantic anchor (e.g. bottom_center, top_front_left)",
      "local_offset": [0.0, 0.0, 0.0],
      "description": "what this connects to"
    }
  ]
}
```

## Coordinate Convention

- `local_offset [x, y, z]` is the distance in meters from the object's center to the attachment point, in world space.
- The `top` surface is at `[0, 0, +target_bbox.height/2]`.
- The `bottom` surface is at `[0, 0, -target_bbox.height/2]`.
- The `right` surface is at `[+target_bbox.width/2, 0, 0]`.
- The `left` surface is at `[-target_bbox.width/2, 0, 0]`.
- The `front` surface is at `[0, +target_bbox.depth/2, 0]`.
- The `back` surface is at `[0, -target_bbox.depth/2, 0]`.
- Corners use combinations of those half-extents.

## Parent-Child Attachment

- A child part connects to its parent at their attachment points.
- The child attachment point aligns with the parent attachment point.
- The child MUST have an attachment point on the surface that faces the parent.
- Child and parent attachment points MUST point in opposite directions on at least one axis.
- Do not use the same-facing surface on both parts.
- Do not use a tip or edge as the attachment point; always use a surface.

## Symmetry-Specific Attachment Rules

- `LEFT_RIGHT_X`: the attachment point MUST have `|local_offset[0]| > 0`.
- `LEFT_RIGHT_Y`: the attachment point MUST have `|local_offset[1]| > 0`.
- `QUADRANT_Z` / `RADIAL_4_Z`: the attachment point MUST have `|local_offset[2]| > 0`.
- `NONE`: any surface face is fine.

## Rules

- All dimensions must be positive and use consistent units.
- Children must be smaller than parent in at least one dimension.
- Attachment offsets must be within the part's bounding box.
- Include a spec for EVERY part family.

## Recommended Viewpoints

- Tall parts: `front`
- Flat parts: `side`
- Thin parts: `top`
