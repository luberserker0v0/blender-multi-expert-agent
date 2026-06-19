import sys
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient


class FakeTool:
    def __init__(self, name, description, input_schema):
        self.name = name
        self.description = description
        self.inputSchema = input_schema

    def model_dump(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema,
        }


class FakeListToolsResult:
    def __init__(self, tools):
        self.tools = tools


class FakeSession:
    def __init__(self, read_stream, write_stream):
        self.read_stream = read_stream
        self.write_stream = write_stream
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def initialize(self):
        self.calls.append(("initialize",))
        return {"protocolVersion": "2025-06-18"}

    async def send_ping(self):
        self.calls.append(("send_ping",))
        return {"ok": True}

    async def list_tools(self):
        self.calls.append(("list_tools",))
        return [
            FakeTool(
                "get_context",
                "Return scene context",
                {
                    "type": "object",
                    "properties": {"session_id": {"type": "string"}},
                    "required": ["session_id"],
                },
            )
        ]

    async def call_tool(self, name, arguments=None):
        self.calls.append(("call_tool", name, arguments or {}))
        return {
            "content": [{"type": "text", "text": "ok"}],
            "isError": False,
            "structuredContent": {"name": name, "arguments": arguments or {}},
        }


class FakeTransport:
    async def __aenter__(self):
        return ("read", "write", None)

    async def __aexit__(self, exc_type, exc, tb):
        return False


def fake_transport_factory():
    return FakeTransport()


class FakeStdioParams:
    def __init__(self, command, args, env, cwd):
        self.command = command
        self.args = args
        self.env = env
        self.cwd = cwd


class TestSdkMcpClient(unittest.TestCase):
    def test_initialize_uses_sdk_session(self) -> None:
        client = SdkMCPClient(
            McpClientConfig(
                command="uv",
                args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
                cwd="C:\\blender_mcp\\mcp",
            ),
            transport_factory=fake_transport_factory,
            session_factory=FakeSession,
        )

        result = client.initialize()

        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_list_tools_returns_tool_schema(self) -> None:
        client = SdkMCPClient(
            McpClientConfig(
                command="uv",
                args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
                cwd="C:\\blender_mcp\\mcp",
            ),
            transport_factory=fake_transport_factory,
            session_factory=FakeSession,
        )

        tools = client.list_tools()

        self.assertEqual(tools[0]["name"], "get_context")
        self.assertEqual(tools[0]["inputSchema"]["required"], ["session_id"])

    def test_call_tool_returns_normalized_result(self) -> None:
        client = SdkMCPClient(
            McpClientConfig(
                command="uv",
                args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
                cwd="C:\\blender_mcp\\mcp",
            ),
            transport_factory=fake_transport_factory,
            session_factory=FakeSession,
        )

        result = client.call_tool("get_context", {"session_id": "chat-window-001"})

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["name"], "get_context")

    def test_stdio_mode_accepts_command_configuration(self) -> None:
        client = SdkMCPClient(
            McpClientConfig(
                command="uv",
                args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
                cwd="C:\\blender_mcp\\mcp",
            ),
            transport_factory=fake_transport_factory,
            session_factory=FakeSession,
        )

        result = client.initialize()
        self.assertEqual(result["protocolVersion"], "2025-06-18")

    def test_requires_stdio_command_configuration(self) -> None:
        client = SdkMCPClient(McpClientConfig())

        with self.assertRaises(ValueError):
            client.initialize()

    def test_call_tool_writes_runtime_log_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = Path(tmp_dir) / "tool_calls.jsonl"
            client = SdkMCPClient(
                McpClientConfig(
                    command="uv",
                    args=["run", "blender-mcp"],
                    session_id="chat-window-001",
                    tool_call_log_path=str(log_path),
                ),
                transport_factory=fake_transport_factory,
                session_factory=FakeSession,
            )

            client.call_tool("get_context", {"session_id": "chat-window-001"})

            payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(payload["tool_name"], "get_context")
            self.assertEqual(payload["session_id"], "chat-window-001")


if __name__ == "__main__":
    unittest.main()
