# Perception And YOLO

## Current Status

The project currently treats perception as optional validation support:

- mock perception for tests and local non-vision checks
- YOLO-backed perception for live screenshot or image validation experiments

YOLO is not required for the AO-backed multi-expert pipeline.

## Current YOLO Runtime Path

The current YOLO design is:

1. Blender capture produces an image
2. `YoloPerceptionProvider` loads a local model
3. the provider runs inference on the captured image
4. the provider converts raw model output into structured `PerceptionResult`

## Capture Runtime Constraint

The current live Blender capture path is still constrained by the Blender MCP screenshot tool.

Current confirmed behavior:

- a usable `VIEW_3D` area must exist
- Blender must remain non-minimized while the capture is taken
- if the Blender window is minimized, the image given to YOLO may become a black image

This should be treated as a capture-path limitation rather than a YOLO inference failure.

## Capture Framing Risk

The current capture path can also fail semantically even when it produces a non-black image.

If the target object is too large, off-center, too close to the viewport, or only partially inside the visible frame, the captured image may only contain a local crop of the object.

That can lead to:

- false missing-part judgments
- distorted bounding-box ratios
- misleading gap reports
- decision mistakes caused by framing rather than modeling state

This should be treated as a viewport-framing problem, not as a YOLO-model problem.

## Planned Framing Step

Before live capture becomes the default perception path, the runtime should add an explicit target-framing step.

The expected direction is:

1. identify the target object for the current task
2. switch to a usable `VIEW_3D`
3. use `execute_blender_code` to adjust the viewpoint and frame the target object inside the viewport
4. use Blender-side viewport operators such as `bpy.ops.view3d.view_selected(...)`
5. capture the image
6. run YOLO on the framed image

Current design preference:

- do not rely on `jump_to_view3d_object_by_name` as the framing strategy
- treat viewpoint control itself as part of the `execute_blender_code` path
- use Blender operators such as `bpy.ops.view3d.view_selected(...)` to fit the selected target into view

## Current Structured Outputs

The current `PerceptionResult` can now carry:

- `detected_parts`
- `missing_critical_parts`
- `quantitative_metrics`
- `detections`

Each detection currently includes:

- `part_name`
- `confidence`
- `bbox_xyxy`
- `bbox_center_ratio`

## What This Supports

With the current detection structure, the system can support:

- coarse local-part existence checks
- confidence-based filtering
- coarse relative-position reasoning between detected parts

Examples:

- whether `cat_ear` is above `cat_body`
- whether `cat_tail` is offset from `cat_body`
- whether the body is detected but a required tail part is missing

## What This Does Not Yet Fully Support

The current detection structure is not enough for fine-grained pose reasoning such as:

- ear orientation
- tail curvature
- precise articulated pose

Those cases are better served by:

- pose keypoints
- segmentation masks

## Important Constraint

The system can only reason about `cat_ear`, `cat_tail`, `cat_body`, or similar local parts if the YOLO model has actually been trained to output those part classes.

If a model only predicts `cat`, then the system will only receive whole-object detections, not local-part detections.
