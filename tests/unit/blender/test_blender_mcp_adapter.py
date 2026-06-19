import sys
import unittest
import tempfile
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.blender.mcp_adapter import BlenderMcpAdapter


class FakeMcpClient:
    def __init__(self) -> None:
        self.calls = []

    def call_tool(self, name, arguments=None):
        arguments = arguments or {}
        self.calls.append((name, arguments))
        if name == "get_objects_summary":
            return {
                "structuredContent": {
                    "result": {
                        "status": "ok",
                        "active_object": "apple_body",
                        "object_mode": "OBJECT",
                        "collections": [
                            {
                                "name": "Scene Collection",
                                "objects": [{"name": "apple_body", "active": True, "selected": True}],
                                "children": [],
                            }
                        ],
                    }
                }
            }
        if name == "get_object_detail_summary":
            return {
                "structuredContent": {
                    "result": {
                        "status": "ok",
                        "type": "MESH",
                        "scale": [1.5, 1.5, 1.5],
                        "polygon_count": 256,
                    }
                },
                "isError": False,
            }
        if name == "execute_blender_code":
            code = arguments.get("code", "")
            if "bpy.ops.render.render(write_still=True)" in code:
                match = re.search(r"output_path = '([^']+)'", code)
                if match:
                    Path(match.group(1)).write_bytes(b"fake-render")
                return {
                    "structuredContent": {
                        "result": {
                            "output_path": match.group(1) if match else "",
                            "axis_type": "FRONT",
                        }
                    }
                }
            if "dimensions" in code:
                return {
                    "structuredContent": {
                        "result": {
                            "name": "apple_body",
                            "dimensions": [1.2, 0.8, 2.4],
                        }
                    }
                }
            if "bpy.data.objects.remove" in code:
                return {
                    "structuredContent": {
                        "result": {
                            "deleted": True,
                        }
                    }
                }
            return {
                "structuredContent": {
                    "result": {
                        "name": "apple_body",
                        "scale": [1.0, 1.0, 1.0],
                        "polygon_count": 256,
                    }
                }
            }
        if name == "get_objects_summary_for_cleanup":
            return {}
        raise AssertionError(f"Unexpected tool call: {name}")


class TestBlenderMcpAdapter(unittest.TestCase):
    def test_get_context_maps_summary_to_blender_context(self) -> None:
        adapter = BlenderMcpAdapter(FakeMcpClient(), session_id="chat-window-001")

        context = adapter.get_context()

        self.assertEqual(context.current_mode, "OBJECT")
        self.assertEqual(context.active_object_name, "apple_body")
        self.assertEqual(context.active_element_mode, "NONE")

    def test_create_uv_sphere_uses_execute_blender_code(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        created = adapter.create_uv_sphere("apple_body")

        self.assertEqual(created.name, "apple_body")
        self.assertEqual(created.scale, [1.0, 1.0, 1.0])
        self.assertEqual(client.calls[0][0], "execute_blender_code")
        self.assertIn("primitive_uv_sphere_add", client.calls[0][1]["code"])

    def test_create_primitive_accepts_human_readable_uv_sphere_name(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        created = adapter.create_primitive("UV Sphere", "chair_back")

        self.assertEqual(created.name, "chair_back")
        self.assertEqual(client.calls[0][0], "execute_blender_code")
        self.assertIn("primitive_uv_sphere_add", client.calls[0][1]["code"])

    def test_scale_uniform_uses_active_object_name(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        adapter.scale_uniform(1.5)

        tool_name, arguments = client.calls[-1]
        self.assertEqual(tool_name, "execute_blender_code")
        self.assertIn("bpy.data.objects['apple_body']", arguments["code"])
        self.assertIn("factor = 1.5", arguments["code"])

    def test_set_object_scale_uses_execute_blender_code(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        adapter.set_object_scale("apple_body", [0.8, 1.1, 1.6])

        tool_name, arguments = client.calls[-1]
        self.assertEqual(tool_name, "execute_blender_code")
        self.assertIn("bpy.data.objects['apple_body']", arguments["code"])
        self.assertIn("obj.scale = (0.8, 1.1, 1.6)", arguments["code"])

    def test_get_object_dimensions_uses_execute_blender_code(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        dimensions = adapter.get_object_dimensions("apple_body")

        self.assertEqual(dimensions, [1.2, 0.8, 2.4])
        self.assertEqual(client.calls[-1][0], "execute_blender_code")

    def test_adapter_raises_on_tool_error(self) -> None:
        class ErrorClient(FakeMcpClient):
            def call_tool(self, name, arguments=None):
                if name == "get_objects_summary":
                    return {
                        "isError": True,
                        "content": [{"type": "text", "text": "Cannot connect to Blender."}],
                        "structuredContent": None,
                    }
                return super().call_tool(name, arguments)

        adapter = BlenderMcpAdapter(ErrorClient(), session_id="chat-window-001")

        with self.assertRaises(RuntimeError):
            adapter.get_context()

    def test_capture_view_writes_image_file(self) -> None:
        client = FakeMcpClient()
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = BlenderMcpAdapter(
                client,
                session_id="chat-window-001",
                capture_output_dir=Path(tmp_dir),
            )

            capture_path = adapter.capture_view("capture.png", viewpoint="top")

            self.assertTrue(Path(capture_path).exists())
            self.assertEqual(Path(capture_path).read_bytes(), b"fake-render")
            call_names = [name for name, _ in client.calls]
            self.assertEqual(
                call_names,
                [
                    "get_objects_summary",
                    "execute_blender_code",
                ],
            )
            self.assertIn("axis_type = 'TOP'", client.calls[1][1]["code"])
            self.assertIn("camera.data.type = 'ORTHO'", client.calls[1][1]["code"])
            self.assertIn("bpy.ops.render.render(write_still=True)", client.calls[1][1]["code"])

    def test_capture_view_rejects_unknown_viewpoint(self) -> None:
        adapter = BlenderMcpAdapter(FakeMcpClient(), session_id="chat-window-001")

        with self.assertRaises(ValueError):
            adapter.capture_view("capture.png", viewpoint="diagonal")

    def test_capture_view_accepts_human_readable_front_orthographic_view(self) -> None:
        client = FakeMcpClient()
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = BlenderMcpAdapter(
                client,
                session_id="chat-window-001",
                capture_output_dir=Path(tmp_dir),
            )

            capture_path = adapter.capture_view("capture.png", viewpoint="Front/Orthographic View")

            self.assertTrue(Path(capture_path).exists())
            self.assertIn("axis_type = 'FRONT'", client.calls[-1][1]["code"])

    def test_capture_view_uses_render_code_path(self) -> None:
        client = FakeMcpClient()
        with tempfile.TemporaryDirectory() as tmp_dir:
            adapter = BlenderMcpAdapter(
                client,
                session_id="chat-window-001",
                capture_output_dir=Path(tmp_dir),
            )

            capture_path = adapter.capture_view("camera_capture.png", viewpoint="front")

            self.assertEqual(capture_path, str(Path(tmp_dir) / "camera_capture.png"))
            self.assertEqual(client.calls[-2][0], "get_objects_summary")
            self.assertEqual(client.calls[-1][0], "execute_blender_code")
            self.assertIn("bpy.ops.render.render(write_still=True)", client.calls[-1][1]["code"])
            self.assertIn("axis_type = 'FRONT'", client.calls[-1][1]["code"])

    def test_list_object_names_reads_collection_tree(self) -> None:
        adapter = BlenderMcpAdapter(FakeMcpClient(), session_id="chat-window-001")

        names = adapter.list_object_names()

        self.assertEqual(names, ["apple_body"])

    def test_delete_object_uses_execute_blender_code(self) -> None:
        client = FakeMcpClient()
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        deleted = adapter.delete_object("apple_body")

        self.assertTrue(deleted)
        self.assertEqual(client.calls[-1][0], "execute_blender_code")
        self.assertIn("bpy.data.objects.remove", client.calls[-1][1]["code"])

    def test_get_object_parent_returns_parent_name(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "parent_name" in code:
                    return {
                        "structuredContent": {
                            "result": {"parent": "robot_torso"}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        parent = adapter.get_object_parent("robot_arm")

        self.assertEqual(parent, "robot_torso")

    def test_get_object_parent_returns_none_for_root(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "parent_name" in code:
                    return {
                        "structuredContent": {
                            "result": {"parent": None}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        parent = adapter.get_object_parent("robot_torso")

        self.assertIsNone(parent)

    def test_get_object_children_returns_child_names(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "children" in code and "obj.children" in code:
                    return {
                        "structuredContent": {
                            "result": {"children": ["robot_arm_01", "robot_leg_01"]}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        children = adapter.get_object_children("robot_torso")

        self.assertEqual(children, ["robot_arm_01", "robot_leg_01"])

    def test_get_object_location_returns_xyz(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "obj.location" in code and "rotation" not in code and "scale" not in code:
                    return {
                        "structuredContent": {
                            "result": {"location": [0.5, 0.3, 0.1]}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        loc = adapter.get_object_location("robot_arm_01")

        self.assertEqual(loc, [0.5, 0.3, 0.1])

    def test_get_object_rotation_returns_degrees(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "rotation_degrees" in code:
                    return {
                        "structuredContent": {
                            "result": {"rotation_degrees": [0.0, 90.0, 0.0]}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        rot = adapter.get_object_rotation("robot_arm_01")

        self.assertEqual(rot, [0.0, 90.0, 0.0])

    def test_get_object_scale_returns_xyz(self) -> None:
        client = FakeMcpClient()
        original_call_tool = client.call_tool

        def mock_call_tool(name, arguments=None):
            arguments = arguments or {}
            if name == "execute_blender_code":
                code = arguments.get("code", "")
                if "'scale'" in code and "dimensions" not in code:
                    return {
                        "structuredContent": {
                            "result": {"scale": [1.5, 2.0, 0.5]}
                        }
                    }
            return original_call_tool(name, arguments)

        client.call_tool = mock_call_tool
        adapter = BlenderMcpAdapter(client, session_id="chat-window-001")

        scale = adapter.get_object_scale("robot_arm_01")

        self.assertEqual(scale, [1.5, 2.0, 0.5])


if __name__ == "__main__":
    unittest.main()
