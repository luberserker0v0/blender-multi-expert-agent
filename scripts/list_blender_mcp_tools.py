"""List tools exposed by the Blender MCP server."""

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient


def main() -> int:
    client = SdkMCPClient(
        McpClientConfig(
            command="uv",
            args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
            cwd="C:\\blender_mcp\\mcp",
        )
    )
    tools = client.list_tools()

    print("Tool count:", len(tools))
    print(json.dumps(tools, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
