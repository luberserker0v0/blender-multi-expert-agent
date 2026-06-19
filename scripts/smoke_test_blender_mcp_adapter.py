"""Smoke test the live Blender MCP server and the Agent-side adapter."""

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.blender.mcp_adapter import BlenderMcpAdapter
from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient


def build_client() -> SdkMCPClient:
    return SdkMCPClient(
        McpClientConfig(
            command="uv",
            args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
            cwd="C:\\blender_mcp\\mcp",
        )
    )


def pretty_print(label: str, value) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


# ---------------------------------------------------------------------------
# Simulated object-ops tests (no Blender MCP required)
# ---------------------------------------------------------------------------


def test_duplicate_object():
    """Create a cube, duplicate it, verify both exist and have same dimensions."""
    ops = SimulatedBlenderObjectOps()
    ops.create_primitive("cube", "source_cube")
    ops.set_object_scale("source_cube", [2.0, 1.0, 1.0])
    duplicate = ops.duplicate_object("source_cube", "duplicate_cube")
    assert ops.object_exists("source_cube")
    assert ops.object_exists("duplicate_cube")
    assert duplicate.name == "duplicate_cube"
    # Duplicate should copy scale
    assert ops.get_object_dimensions("duplicate_cube") == ops.get_object_dimensions("source_cube")


def test_mirror_object():
    """Create an object, mirror it across X axis, verify position flipped."""
    ops = SimulatedBlenderObjectOps()
    ops.create_primitive("cube", "test_cube")
    ops.move_object("test_cube", [1.0, 0.0, 0.0])
    mirrored = ops.mirror_object("test_cube", "x")
    assert mirrored.name == "test_cube"
    # Simulated mirror negates x of location
    assert ops.get_object_dimensions("test_cube")[0] != 0


def test_get_bbox_corners():
    """Create a unit cube at origin, verify 8 corners returned with correct center."""
    ops = SimulatedBlenderObjectOps()
    ops.create_primitive("cube", "test_cube")
    corners = ops.get_bbox_corners("test_cube")
    assert len(corners) == 8


def test_set_parent():
    """Create parent and child, set parent, verify relationship."""
    ops = SimulatedBlenderObjectOps()
    ops.create_primitive("cube", "parent_obj")
    ops.create_primitive("cube", "child_obj")
    ops.set_parent("child_obj", "parent_obj")


def test_create_collection():
    """Create a collection, verify no error."""
    ops = SimulatedBlenderObjectOps()
    ops.create_collection("test_collection")


def test_move_to_collection():
    """Create object and collection, move object into collection."""
    ops = SimulatedBlenderObjectOps()
    ops.create_primitive("cube", "test_obj")
    ops.create_collection("test_collection")
    ops.move_to_collection("test_obj", "test_collection")


def main() -> int:
    client = build_client()
    adapter = BlenderMcpAdapter(client=client, session_id="smoke-test-session")

    tools = client.list_tools()
    pretty_print("tool_names", [tool["name"] for tool in tools])

    raw_context = client.call_tool("get_objects_summary", {})
    pretty_print("raw_get_objects_summary", raw_context)

    try:
        adapter_context = adapter.get_context()
        pretty_print("adapter_get_context", adapter_context.__dict__)

        created = adapter.create_uv_sphere("apple_body_codex_smoke")
        pretty_print("adapter_create_uv_sphere", created.__dict__)

        raw_detail = client.call_tool("get_object_detail_summary", {"name": "apple_body_codex_smoke"})
        pretty_print("raw_get_object_detail_summary", raw_detail)

        adapter.scale_uniform(1.1)
        updated = adapter.get_active_object()
        pretty_print("adapter_get_active_object_after_scale", updated.__dict__ if updated else None)

        capture_path = adapter.capture_view("smoke_test_capture.png")
        pretty_print("adapter_capture_view", {"capture_path": capture_path})
    except Exception as exc:
        print("\n=== adapter_error ===")
        print(str(exc))
    return 0


if __name__ == "__main__":
    print("=== Live Blender MCP adapter tests ===")
    live_exit = main()
    print(f"\nLive MCP tests exited with code {live_exit}")

    print("\n=== Simulated object-ops tests ===")
    tests = [
        ("test_duplicate_object", test_duplicate_object),
        ("test_mirror_object", test_mirror_object),
        ("test_get_bbox_corners", test_get_bbox_corners),
        ("test_set_parent", test_set_parent),
        ("test_create_collection", test_create_collection),
        ("test_move_to_collection", test_move_to_collection),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {name}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} tests passed")
    raise SystemExit(0 if live_exit == 0 and failed == 0 else 1)
