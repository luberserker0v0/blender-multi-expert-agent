"""Agent-side Blender adapter backed by MCP tools."""

import base64
from dataclasses import dataclass
from math import radians
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps, SimulatedObject
from ai_3d_modeling_agent.schemas.gap_report import BlenderContext
from ai_3d_modeling_agent.services.mcp_client import MCPClient


@dataclass
class BlenderMcpAdapter(BlenderObjectOps):
    client: MCPClient
    session_id: str
    object_name_fallback: str = "default_body"
    capture_output_dir: Optional[Path] = None

    def list_object_names(self) -> List[str]:
        result = self._call_tool_checked("get_objects_summary", {})
        structured = self._extract_structured_content(result)
        objects = self._flatten_objects(structured.get("collections") or [])
        return sorted(str(item.get("name", "")) for item in objects if item.get("name"))

    def get_context(self) -> BlenderContext:
        result = self._call_tool_checked("get_objects_summary", {})
        structured = self._extract_structured_content(result)
        objects = self._flatten_objects(structured.get("collections") or [])
        active_object_name = str(structured.get("active_object") or "")

        if not active_object_name:
            for item in objects:
                if item.get("selected") or item.get("active"):
                    active_object_name = str(item.get("name", ""))
                    break
        if not active_object_name and objects:
            active_object_name = str(objects[0].get("name", ""))

        return BlenderContext(
            current_mode=str(structured.get("object_mode", "OBJECT") or "OBJECT"),
            active_object_name=active_object_name,
            active_element_mode="NONE",
        )

    def object_exists(self, name: str) -> bool:
        result = self.client.call_tool("get_object_detail_summary", {"name": name})
        if result.get("isError"):
            return False
        data = self._extract_structured_content(result)
        return str(data.get("status", "")) == "ok"

    def create_uv_sphere(self, name: str) -> SimulatedObject:
        return self.create_primitive("uv_sphere", name)

    def create_primitive(self, primitive_type: str, name: str) -> SimulatedObject:
        primitive_statement = self._primitive_statement(primitive_type)
        code = "\n".join(
            [
                "import bpy",
                "if bpy.context.mode != 'OBJECT':",
                "    bpy.ops.object.mode_set(mode='OBJECT')",
                f"existing = bpy.data.objects.get({name!r})",
                "if existing is not None:",
                "    bpy.data.objects.remove(existing, do_unlink=True)",
                primitive_statement,
                f"bpy.context.active_object.name = {name!r}",
                "obj = bpy.context.active_object",
                "result = {",
                "    'name': obj.name,",
                "    'scale': list(obj.scale),",
                "    'location': list(obj.location),",
                "    'polygon_count': len(obj.data.polygons),",
                "}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return SimulatedObject(
            name=str(data.get("name", name)),
            primitive_type=str(primitive_type).upper(),
            scale=self._extract_scale(data.get("scale")),
            location=self._extract_xyz(data.get("location"), default=[0.0, 0.0, 0.0]),
            polygon_count=int(data.get("polygon_count", 256)),
        )

    def get_active_object(self) -> Optional[SimulatedObject]:
        context = self.get_context()
        if not context.active_object_name:
            return None
        result = self._call_tool_checked(
            "get_object_detail_summary",
            {"name": context.active_object_name},
        )
        data = self._extract_structured_content(result)
        if str(data.get("status", "")) != "ok":
            return None
        return SimulatedObject(
            name=context.active_object_name,
            primitive_type=str(data.get("type", "MESH")),
            scale=self._extract_scale(data.get("scale")),
            location=self._extract_xyz(data.get("location"), default=[0.0, 0.0, 0.0]),
            rotation_degrees=self._extract_xyz(data.get("rotation_degrees"), default=[0.0, 0.0, 0.0]),
            polygon_count=int(data.get("polygon_count", 256)),
            hidden=bool(data.get("hidden", False)),
        )

    def set_active_object(self, name: str) -> None:
        if not self.object_exists(name):
            raise RuntimeError(f"Object does not exist: {name}")
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "bpy.context.view_layer.objects.active = obj",
                "obj.select_set(True)",
                "result = {'active_object_name': obj.name}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def scale_uniform(self, factor: float) -> None:
        active_name = self._require_active_object_name()
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{active_name!r}]",
                f"factor = {float(factor)!r}",
                "obj.scale = [round(axis * factor, 4) for axis in obj.scale]",
                "result = {'name': obj.name, 'scale': list(obj.scale)}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def scale_axis(self, axis: str, factor: float) -> None:
        active_name = self._require_active_object_name()
        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{active_name!r}]",
                f"factor = {float(factor)!r}",
                f"obj.scale[{axis_index}] = round(obj.scale[{axis_index}] * factor, 4)",
                "result = {'name': obj.name, 'scale': list(obj.scale)}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def move_object(self, name: str, location: List[float]) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                f"obj.location = ({float(location[0])!r}, {float(location[1])!r}, {float(location[2])!r})",
                "result = {'name': obj.name, 'location': list(obj.location)}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def get_object_dimensions(self, name: str) -> List[float]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "result = {'name': obj.name, 'dimensions': list(obj.dimensions)}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return self._extract_xyz(data.get("dimensions"), default=[0.0, 0.0, 0.0])

    def set_object_scale(self, name: str, scale: List[float]) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                f"obj.scale = ({float(scale[0])!r}, {float(scale[1])!r}, {float(scale[2])!r})",
                "result = {'name': obj.name, 'scale': list(obj.scale)}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def rotate_object(self, name: str, rotation_degrees: List[float]) -> None:
        radians_xyz = [radians(float(value)) for value in rotation_degrees]
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "obj.rotation_mode = 'XYZ'",
                f"obj.rotation_euler = ({radians_xyz[0]!r}, {radians_xyz[1]!r}, {radians_xyz[2]!r})",
                "result = {'name': obj.name, 'rotation_euler': list(obj.rotation_euler)}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def set_object_hidden(self, name: str, hidden: bool) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                f"obj.hide_viewport = {bool(hidden)!r}",
                f"obj.hide_render = {bool(hidden)!r}",
                "result = {'name': obj.name, 'hidden': obj.hide_viewport}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def capture_view(
        self,
        capture_name: str,
        viewpoint: str = "front",
        object_name: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        if output_dir:
            out = Path(output_dir)
        else:
            out = self.capture_output_dir or (Path.cwd() / "data" / "runtime" / "captures")
        out.mkdir(parents=True, exist_ok=True)
        output_path = out / capture_name
        self._render_camera_view(output_path, viewpoint=viewpoint, object_name=object_name)
        return str(output_path)

    def delete_object(self, name: str) -> bool:
        if not self.object_exists(name):
            return False
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects.get({name!r})",
                "if obj is None:",
                "    result = {'deleted': False}",
                "else:",
                "    bpy.data.objects.remove(obj, do_unlink=True)",
                "    result = {'deleted': True}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return bool(data.get("deleted"))

    def duplicate_object(self, name: str, new_name: str) -> SimulatedObject:
        code = "\n".join(
            [
                "import bpy",
                f"existing = bpy.data.objects.get({new_name!r})",
                "if existing is not None:",
                "    bpy.data.objects.remove(existing, do_unlink=True)",
                "bpy.ops.object.select_all(action='DESELECT')",
                f"bpy.data.objects[{name!r}].select_set(True)",
                f"bpy.context.view_layer.objects.active = bpy.data.objects[{name!r}]",
                "bpy.ops.object.duplicate()",
                f"bpy.context.active_object.name = {new_name!r}",
                "obj = bpy.context.active_object",
                "result = {",
                "    'name': obj.name,",
                "    'scale': list(obj.scale),",
                "    'location': list(obj.location),",
                "    'polygon_count': len(obj.data.polygons),",
                "    'type': obj.type,",
                "}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return SimulatedObject(
            name=str(data.get("name", new_name)),
            primitive_type=str(data.get("type", "MESH")),
            scale=self._extract_scale(data.get("scale")),
            location=self._extract_xyz(data.get("location"), default=[0.0, 0.0, 0.0]),
            polygon_count=int(data.get("polygon_count", 0)),
        )

    def mirror_object(self, name: str, axis: str) -> SimulatedObject:
        axis_lower = axis.strip().lower()
        axis_attrs = {"x": "use_axis_x", "y": "use_axis_y", "z": "use_axis_z"}
        if axis_lower not in axis_attrs:
            raise ValueError(f"Unsupported axis: {axis!r}. Use 'x', 'y', or 'z'.")
        axis_attr = axis_attrs[axis_lower]
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "bpy.context.view_layer.objects.active = obj",
                "mod = obj.modifiers.new(name='Mirror_DnC', type='MIRROR')",
                f"mod.{axis_attr} = True",
                "bpy.ops.object.modifier_apply(modifier=mod.name)",
                "result = {",
                "    'name': obj.name,",
                "    'scale': list(obj.scale),",
                "    'location': list(obj.location),",
                "    'polygon_count': len(obj.data.polygons),",
                "    'type': obj.type,",
                "}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return SimulatedObject(
            name=str(data.get("name", name)),
            primitive_type=str(data.get("type", "MESH")),
            scale=self._extract_scale(data.get("scale")),
            location=self._extract_xyz(data.get("location"), default=[0.0, 0.0, 0.0]),
            polygon_count=int(data.get("polygon_count", 0)),
        )

    def get_bbox_corners(self, name: str) -> List[List[float]]:
        code = "\n".join(
            [
                "import bpy",
                "from mathutils import Vector",
                f"obj = bpy.data.objects[{name!r}]",
                "corners = [list(obj.matrix_world @ Vector(corner)) for corner in obj.bound_box]",
                "result = {'corners': corners}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        corners = data.get("corners")
        if isinstance(corners, list):
            return [[float(v) for v in corner] for corner in corners]
        return []

    def set_parent(self, child_name: str, parent_name: str) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"child = bpy.data.objects[{child_name!r}]",
                f"parent = bpy.data.objects[{parent_name!r}]",
                "child.parent = parent",
                "result = {'child': child.name, 'parent': parent.name}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def get_object_parent(self, name: str) -> Optional[str]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "parent_name = obj.parent.name if obj.parent else None",
                "result = {'parent': parent_name}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return data.get("parent")

    def get_object_children(self, name: str) -> List[str]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "children = [c.name for c in obj.children]",
                "result = {'children': children}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        children = data.get("children", [])
        return [str(c) for c in children] if isinstance(children, list) else []

    def get_object_location(self, name: str) -> List[float]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "result = {'location': list(obj.location)}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return self._extract_xyz(data.get("location"), default=[0.0, 0.0, 0.0])

    def get_object_rotation(self, name: str) -> List[float]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "import math",
                "rot = [math.degrees(r) for r in obj.rotation_euler]",
                "result = {'rotation_degrees': rot}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return self._extract_xyz(data.get("rotation_degrees"), default=[0.0, 0.0, 0.0])

    def get_object_scale(self, name: str) -> List[float]:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{name!r}]",
                "result = {'scale': list(obj.scale)}",
            ]
        )
        result = self._call_tool_checked("execute_blender_code", {"code": code})
        data = self._extract_structured_content(result)
        return self._extract_scale(data.get("scale"))

    def create_collection(self, name: str) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"new_coll = bpy.data.collections.new({name!r})",
                "bpy.context.scene.collection.children.link(new_coll)",
                "result = {'collection': new_coll.name}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def move_to_collection(self, object_name: str, collection_name: str) -> None:
        code = "\n".join(
            [
                "import bpy",
                f"obj = bpy.data.objects[{object_name!r}]",
                f"coll = bpy.data.collections.get({collection_name!r})",
                "if coll is None:",
                f"    coll = bpy.data.collections.new({collection_name!r})",
                "    bpy.context.scene.collection.children.link(coll)",
                "for col in obj.users_collection:",
                "    col.objects.unlink(obj)",
                "coll.objects.link(obj)",
                "result = {'object': obj.name, 'collection': coll.name}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    def _require_active_object_name(self) -> str:
        context = self.get_context()
        if context.active_object_name:
            return context.active_object_name
        if self.object_name_fallback:
            return self.object_name_fallback
        raise RuntimeError("No active object available for MCP-backed Blender operation.")

    def _call_tool_checked(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = self.client.call_tool(name, arguments)
        if result.get("isError"):
            raise RuntimeError(self._extract_error_message(result, name))
        return result

    def _render_camera_view(
        self,
        output_path: Path,
        viewpoint: str = "front",
        object_name: Optional[str] = None,
    ) -> None:
        active_name = object_name or self._require_active_object_name()
        axis_type = self._resolve_view_axis(viewpoint)
        code = "\n".join(
            [
                "import bpy",
                "from mathutils import Vector",
                f"target_name = {active_name!r}",
                f"axis_type = {axis_type!r}",
                f"output_path = {str(output_path)!r}",
                "target = bpy.data.objects.get(target_name)",
                "if target is None:",
                "    raise RuntimeError(f'Target object not found: {target_name}')",
                "scene = bpy.context.scene",
                "camera = scene.camera",
                "if camera is None or camera.type != 'CAMERA':",
                "    camera_data = bpy.data.cameras.new(name='AgentCaptureCamera')",
                "    camera = bpy.data.objects.new('AgentCaptureCamera', camera_data)",
                "    bpy.context.scene.collection.objects.link(camera)",
                "    scene.camera = camera",
                "camera.data.type = 'ORTHO'",
                "bbox_world = [target.matrix_world @ Vector(corner) for corner in target.bound_box]",
                "min_x = min(item.x for item in bbox_world)",
                "max_x = max(item.x for item in bbox_world)",
                "min_y = min(item.y for item in bbox_world)",
                "max_y = max(item.y for item in bbox_world)",
                "min_z = min(item.z for item in bbox_world)",
                "max_z = max(item.z for item in bbox_world)",
                "center = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))",
                "size_x = max_x - min_x",
                "size_y = max_y - min_y",
                "size_z = max_z - min_z",
                "max_dim = max(size_x, size_y, size_z, 0.001)",
                "padding = 1.35",
                "camera.data.ortho_scale = max_dim * padding * 2.0",
                "if axis_type == 'FRONT':",
                "    location = Vector((center.x, center.y - max_dim * 3.0, center.z))",
                "    rotation = (1.5708, 0.0, 0.0)",
                "elif axis_type == 'BACK':",
                "    location = Vector((center.x, center.y + max_dim * 3.0, center.z))",
                "    rotation = (1.5708, 0.0, 3.14159)",
                "elif axis_type == 'LEFT':",
                "    location = Vector((center.x - max_dim * 3.0, center.y, center.z))",
                "    rotation = (1.5708, 0.0, -1.5708)",
                "elif axis_type == 'RIGHT':",
                "    location = Vector((center.x + max_dim * 3.0, center.y, center.z))",
                "    rotation = (1.5708, 0.0, 1.5708)",
                "elif axis_type == 'TOP':",
                "    location = Vector((center.x, center.y, center.z + max_dim * 3.0))",
                "    rotation = (0.0, 0.0, 0.0)",
                "elif axis_type == 'BOTTOM':",
                "    location = Vector((center.x, center.y, center.z - max_dim * 3.0))",
                "    rotation = (3.14159, 0.0, 0.0)",
                "else:",
                "    raise RuntimeError(f'Unsupported camera axis type: {axis_type}')",
                "camera.location = location",
                "camera.rotation_euler = rotation",
                "render = scene.render",
                "original_filepath = render.filepath",
                "original_engine = render.engine",
                "original_image_settings = render.image_settings.file_format",
                "original_film_transparent = render.film_transparent",
                "render.engine = 'BLENDER_WORKBENCH'",
                "render.image_settings.file_format = 'PNG'",
                "render.film_transparent = False",
                "render.filepath = output_path",
                "bpy.ops.render.render(write_still=True)",
                "render.filepath = original_filepath",
                "render.engine = original_engine",
                "render.image_settings.file_format = original_image_settings",
                "render.film_transparent = original_film_transparent",
                "result = {'output_path': output_path, 'axis_type': axis_type}",
            ]
        )
        self._call_tool_checked("execute_blender_code", {"code": code})

    @staticmethod
    def _resolve_view_axis(viewpoint: str) -> str:
        normalized = str(viewpoint or "front").strip().lower()
        normalized = normalized.replace("\\", "/").replace("-", " ").replace("_", " ")
        if "/" in normalized:
            normalized = normalized.split("/", 1)[0].strip()
        normalized = " ".join(normalized.split())
        axis_map = {
            "front": "FRONT",
            "front orthographic view": "FRONT",
            "back": "BACK",
            "back orthographic view": "BACK",
            "left": "LEFT",
            "left orthographic view": "LEFT",
            "right": "RIGHT",
            "right orthographic view": "RIGHT",
            "side": "RIGHT",
            "top": "TOP",
            "top orthographic view": "TOP",
            "bottom": "BOTTOM",
            "bottom orthographic view": "BOTTOM",
        }
        try:
            return axis_map[normalized]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported viewpoint: {viewpoint!r}. "
                "Use one of: front, back, left, right, side, top, bottom."
            ) from exc

    @staticmethod
    def _extract_error_message(result: Dict[str, Any], tool_name: str) -> str:
        content = result.get("content") or []
        messages: List[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                messages.append(item["text"])
        if messages:
            return f"{tool_name} failed: {' '.join(messages)}"
        return f"{tool_name} failed."

    @staticmethod
    def _flatten_objects(collections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        objects: List[Dict[str, Any]] = []
        for collection in collections:
            objects.extend(collection.get("objects") or [])
            objects.extend(BlenderMcpAdapter._flatten_objects(collection.get("children") or []))
        return objects

    @staticmethod
    def _extract_structured_content(result: Dict[str, Any]) -> Dict[str, Any]:
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            if isinstance(structured.get("result"), dict):
                return structured["result"]
            return structured
        content = result.get("content") or []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("json"), dict):
                return item["json"]
        return {}

    @staticmethod
    def _extract_image_bytes(result: Dict[str, Any]) -> bytes:
        content = result.get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("data"), str):
                return base64.b64decode(item["data"])
        return b""

    @staticmethod
    def _extract_scale(value: Any) -> List[float]:
        if isinstance(value, list) and len(value) == 3:
            return [float(item) for item in value]
        return [1.0, 1.0, 1.0]

    @staticmethod
    def _extract_xyz(value: Any, default: List[float]) -> List[float]:
        if isinstance(value, list) and len(value) == 3:
            return [float(item) for item in value]
        return list(default)

    @staticmethod
    def _primitive_statement(primitive_type: str) -> str:
        normalized = str(primitive_type or "uv_sphere").strip().lower()
        normalized = normalized.replace("-", "_").replace(" ", "_")
        primitive_map = {
            "uv_sphere": "bpy.ops.mesh.primitive_uv_sphere_add(location=(0.0, 0.0, 0.0))",
            "cube": "bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.0))",
            "cylinder": "bpy.ops.mesh.primitive_cylinder_add(location=(0.0, 0.0, 0.0))",
            "plane": "bpy.ops.mesh.primitive_plane_add(location=(0.0, 0.0, 0.0))",
        }
        try:
            return primitive_map[normalized]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported primitive type: {primitive_type!r}. "
                "Use one of: uv_sphere, cube, cylinder, plane."
            ) from exc
