# Blender MCP Integration

## Current Integration Shape

The current live Blender path is:

1. Agent code creates `SdkMCPClient`
2. `SdkMCPClient` launches the Blender MCP server over `stdio`
3. the Blender MCP server exposes tools
4. those tools talk to the Blender add-on runtime
5. the add-on executes Blender operations against the live scene

## Current Transport Decision

The current implementation intentionally supports only `stdio` for MCP.

This matches the installed Blender MCP setup and keeps the first integration path simple.

## Current Tool Usage

The Agent currently relies on these real MCP tools:

- `get_objects_summary`
- `get_object_detail_summary`
- `execute_blender_code`
- `get_screenshot_of_area_as_image`

## Capture Constraint

The current `capture_view` path depends on Blender UI screenshot capture through `get_screenshot_of_area_as_image`.

Observed runtime behavior:

- Blender must have an available `VIEW_3D` area
- the Blender window must not be minimized
- if the Blender window is minimized, the captured image may become a black frame

This means the current capture path should be treated as a foreground UI-dependent capture path, not as a background-safe or headless-safe render path.

For future capture framing, the current preferred path is:

- keep using `VIEW_3D` as the capture area
- adjust the viewpoint through `execute_blender_code` before capture
- use `execute_blender_code` for viewport-fit operators such as `bpy.ops.view3d.view_selected(...)`
- do not rely on `jump_to_view3d_object_by_name` as the primary framing mechanism

## Why There Is An Adapter

The live MCP tool surface is generic, while the Agent needs task-oriented operations such as:

- read current context
- create a sphere
- scale the active object
- capture a view
- delete unrelated objects

`BlenderMcpAdapter` is the layer that maps Agent operations onto the generic MCP tools.

## Current Launcher Defaults

- command: `uv`
- cwd: `C:\blender_mcp\mcp`
- args: `--directory C:\blender_mcp\mcp run blender-mcp`

## Related Files

- `src/ai_3d_modeling_agent/services/mcp_client.py`
- `src/ai_3d_modeling_agent/blender/mcp_adapter.py`
- `scripts/run_pipeline.py`
- `scripts/smoke_test_blender_mcp_adapter.py`
