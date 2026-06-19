# Archived Reference

This document is historical. It may describe removed runtime paths and must not
be used as active implementation guidance.

# Blender Adapter

## Purpose

`BlenderMcpAdapter` is the Agent-side Blender backend for live MCP execution.

It provides the same shape of operations the MVP loop expects, while internally calling Blender MCP tools.

## Current Supported Methods

- `list_object_names()`
- `object_exists(name)`
- `create_uv_sphere(name)`
- `get_active_object()`
- `scale_uniform(factor)`
- `scale_axis(axis, factor)`
- `capture_view(capture_name, area_ui_type="VIEW_3D")`
- `delete_object(name)`
- `get_context()`

## Current Tool Mapping

- `get_context()`
  uses `get_objects_summary`
- `list_object_names()`
  uses `get_objects_summary`
- `object_exists()` and `get_active_object()`
  use `get_object_detail_summary`
- `create_uv_sphere()`
  uses `execute_blender_code`
- `scale_uniform()` and `scale_axis()`
  use `execute_blender_code`
- `delete_object()`
  uses `execute_blender_code`
- `capture_view()`
  uses `get_screenshot_of_area_as_image`

## Capture Framing Gap

The current `capture_view()` implementation ensures that a `VIEW_3D` path is available before screenshot capture, but it does not yet guarantee that the target object is well framed inside the viewport.

This means live captures can still suffer from:

- partial-object images
- off-center target placement
- unstable apparent scale in the image

The adapter will eventually need a framing-oriented step before capture, such as a future `frame_target_object()` operation.

Current design preference:

- do not treat `jump_to_view3d_object_by_name` as the primary framing mechanism
- treat viewpoint adjustment itself as an `execute_blender_code` responsibility
- use `execute_blender_code` to invoke Blender viewport operators such as `bpy.ops.view3d.view_selected(...)`

## Error Handling

The adapter treats MCP tool errors as runtime failures and raises explicit exceptions.

This is important because silent fallback behavior would hide real Blender integration failures.

## Current Limitations

- object creation is still primitive-specific
- naming collision handling is minimal
- polygon count handling is still simplified in some code paths
- capture is limited to area screenshot output, not yet viewpoint-managed capture orchestration
