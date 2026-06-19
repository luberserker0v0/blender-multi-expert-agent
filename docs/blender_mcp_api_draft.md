# Blender MCP API Draft

This draft defines the first MCP function surface exposed by Blender.

## Architecture

- Blender hosts the MCP server.
- The Agent acts as the MCP client.
- The Agent calls MCP functions exposed from inside Blender.
- Blender owns `bpy` access, scene state, and low-level execution details.

## Current MCP Setup

The current environment already has a Blender MCP add-on / server installed externally.

Known runtime details:
- current integration path uses `stdio`

Known launcher example:

```json
{
  "mcpServers": {
    "blender": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\blender_mcp\\mcp",
        "run",
        "blender-mcp"
      ]
    }
  }
}
```

This draft assumes the Agent will connect to that Blender-hosted MCP capability surface.

## Design Goals

- Keep the first function set small.
- Expose only the minimum capabilities needed to replace the current simulated MVP loop.
- Return structured JSON that can be consumed by the Agent without Blender-specific parsing logic.

## Session Model

- The Agent owns the top-level `session-id`.
- The same chat window should reuse the same `session-id`.
- Each MCP call should carry the `session_id`.
- Blender may use `session_id` to map calls to scene-local state, task-local metadata, or future recovery logic.

## First Function Set

The first implementation should focus on these four functions:

1. `get_context`
2. `create_primitive`
3. `transform_object`
4. `capture_view`

These are enough to begin replacing the in-memory simulated loop with real Blender-backed operations.

---

## 1. `get_context`

Return the current Blender context in a structured format.

### Request

```json
{
  "session_id": "chat-window-001"
}
```

### Response

```json
{
  "current_mode": "OBJECT",
  "active_object_name": "apple_body",
  "selected_object_names": ["apple_body"],
  "active_element_mode": "NONE",
  "objects": [
    {
      "name": "apple_body",
      "type": "MESH",
      "location": [0.0, 0.0, 0.0],
      "rotation": [0.0, 0.0, 0.0],
      "scale": [1.5, 1.5, 1.5],
      "polygon_count": 256
    }
  ]
}
```

### Notes

- This function is the main replacement for the current simulated context reader.
- It should stay read-only.

### Likely Blender-side `bpy` mapping

- `bpy.context.mode`
  - read current mode such as `OBJECT`, `EDIT_MESH`
- `bpy.context.active_object`
  - read active object name and object type
- `bpy.context.selected_objects`
  - collect selected object names
- `bpy.context.tool_settings.mesh_select_mode`
  - infer active element mode when in edit mode
- `bpy.data.objects`
  - iterate scene objects for summary output
- `obj.location`, `obj.rotation_euler`, `obj.scale`
  - read transform values
- `len(obj.data.polygons)`
  - read polygon count for mesh objects

### Suggested implementation notes

- normalize Blender mode values before returning them to the Agent
- return only scene fields the Agent actually consumes
- avoid exposing raw Blender objects directly in MCP responses

---

## 2. `create_primitive`

Create a basic object in the current scene.

### Request

```json
{
  "session_id": "chat-window-001",
  "primitive_type": "uv_sphere",
  "object_name": "apple_body",
  "location": [0.0, 0.0, 0.0],
  "scale": [1.0, 1.0, 1.0]
}
```

### Response

```json
{
  "success": true,
  "object_name": "apple_body"
}
```

### Supported initial values

- `primitive_type`: `uv_sphere`, `cube`, `cylinder`

### Notes

- The first version should fail clearly if the object name already exists.

### Likely Blender-side `bpy` mapping

- `bpy.ops.mesh.primitive_uv_sphere_add(...)`
  - for `primitive_type = uv_sphere`
- `bpy.ops.mesh.primitive_cube_add(...)`
  - for `primitive_type = cube`
- `bpy.ops.mesh.primitive_cylinder_add(...)`
  - for `primitive_type = cylinder`
- `bpy.context.active_object`
  - rename the newly created object
- `obj.name = object_name`
  - assign stable object name
- `obj.location = (...)`
  - set initial position
- `obj.scale = (...)`
  - set initial scale

### Suggested implementation notes

- force Blender into `OBJECT` mode before primitive creation if needed
- validate duplicate names before calling mesh operators
- return the final active object name after creation

---

## 3. `transform_object`

Apply a basic transform to a scene object.

### Request

```json
{
  "session_id": "chat-window-001",
  "object_name": "apple_body",
  "transform_type": "scale_uniform",
  "value": 1.5
}
```

### Alternate request

```json
{
  "session_id": "chat-window-001",
  "object_name": "apple_body",
  "transform_type": "scale_axis",
  "axis": "z",
  "value": 1.1
}
```

### Response

```json
{
  "success": true,
  "object_name": "apple_body",
  "scale": [1.5, 1.5, 1.5]
}
```

### Supported initial values

- `transform_type`: `scale_uniform`, `scale_axis`
- `axis`: `x`, `y`, `z`

### Notes

- The first version should only support transforms needed by the current MVP.
- Rotation and translation can be added later.

### Likely Blender-side `bpy` mapping

- `bpy.data.objects.get(object_name)`
  - resolve target object
- `obj.scale = (s, s, s)`
  - for `scale_uniform`
- `obj.scale[index] = obj.scale[index] * value`
  - for `scale_axis`
- optionally `bpy.context.view_layer.objects.active = obj`
  - set active object before transform for consistency
- optionally `obj.select_set(True)`
  - make selection state predictable

### Suggested implementation notes

- first version should use direct data assignment, not interactive transform operators
- keep transform behavior deterministic and independent of viewport state
- validate object existence before changing scale
- return updated scale in every success response

---

## 4. `capture_view`

Capture an image from the current viewport or a specified orthographic view.

### Request

```json
{
  "session_id": "chat-window-001",
  "view": "front",
  "shading": "solid"
}
```

### Response

```json
{
  "success": true,
  "image_path": "D:/program/Projects/Blender 3DModel Agent/repo/data/runtime/captures/chat-window-001-front.png"
}
```

### Supported initial values

- `view`: `front`, `side`, `top`
- `shading`: `solid`, `wireframe`

### Notes

- This function is the bridge from Blender to future perception / YOLO.
- The file path should be returned in structured form.

### Likely Blender-side `bpy` mapping

- `bpy.context.area` / `bpy.context.screen.areas`
  - find a `VIEW_3D` area
- `bpy.context.space_data.region_3d` or overridden 3D view context
  - manipulate view orientation
- `bpy.ops.view3d.view_axis(...)`
  - switch to `FRONT`, `RIGHT`, `TOP`
- `bpy.ops.view3d.view_persportho()`
  - enforce orthographic mode if needed
- `space.shading.type = 'SOLID'` or `'WIREFRAME'`
  - set shading
- `bpy.ops.screen.screenshot(...)`
  - capture viewport image to file
  - or use `bpy.ops.render.opengl(write_still=True)` if the add-on prefers OpenGL render capture

### Suggested implementation notes

- this function may require a context override targeting a real `VIEW_3D` area
- the capture path should be deterministic and session-aware
- prefer orthographic views for YOLO / geometry measurement consistency
- record which view and shading were used in the response if helpful

---

## Error Contract

All functions should return structured errors in a stable format.

### Example

```json
{
  "success": false,
  "error_code": "OBJECT_NOT_FOUND",
  "message": "Object 'apple_body' was not found."
}
```

## First Implementation Boundary

The first MCP rollout should not include:

- edit mode topology operations
- complex undo / redo orchestration
- task resume from server-side state
- model load / unload control
- YOLO inference inside Blender

## TODO

- Define transport details for Blender-hosted MCP server startup.
- Define whether `capture_view` writes into repo runtime folders directly or through a configurable output root.
- Define how Blender-side scene state should be isolated across reused `session_id` values.
- Verify how the installed Blender MCP add-on exposes tool names and parameter schemas through its `stdio` server.
- Map this draft API onto the actual add-on capability surface before implementing the Agent-side MCP client.
