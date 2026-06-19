"""MCP client interface with an official MCP SDK-based stdio implementation."""

import asyncio
import json
import os
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol


@dataclass
class McpClientConfig:
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    session_id: str = ""
    tool_call_log_path: Optional[str] = None


class MCPClient(Protocol):
    """Agent-facing MCP client interface."""

    def initialize(self) -> Dict[str, Any]:
        """Initialize the client against the target MCP server."""

    def ping(self) -> Dict[str, Any]:
        """Check whether the MCP server is responsive."""

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return tool metadata including names and schemas."""

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call a server tool by name."""


class SdkMCPClient:
    """Official MCP Python SDK-based stdio client implementation."""

    def __init__(
        self,
        config: McpClientConfig,
        transport_factory: Optional[Callable[..., Any]] = None,
        session_factory: Optional[Callable[..., Any]] = None,
        stdio_params_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.config = config
        self._transport_factory = transport_factory
        self._session_factory = session_factory
        self._stdio_params_factory = stdio_params_factory

    def initialize(self) -> Dict[str, Any]:
        return asyncio.run(self._initialize_async())

    def ping(self) -> Dict[str, Any]:
        return asyncio.run(self._ping_async())

    def list_tools(self) -> List[Dict[str, Any]]:
        return asyncio.run(self._list_tools_async())

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        arguments = arguments or {}
        try:
            result = asyncio.run(self._call_tool_async(name, arguments))
        except Exception as exc:
            self._record_tool_call(
                name=name,
                arguments=arguments,
                result={"error": str(exc)},
                is_error=True,
            )
            raise
        self._record_tool_call(
            name=name,
            arguments=arguments,
            result=result,
            is_error=bool(result.get("isError", False)),
        )
        return result

    async def _initialize_async(self) -> Dict[str, Any]:
        async def _op(session):
            result = await session.initialize()
            return self._normalize_result(result)

        return await self._run_with_session(_op)

    async def _ping_async(self) -> Dict[str, Any]:
        async def _op(session):
            await session.initialize()
            result = await session.send_ping()
            return self._normalize_result(result) if result is not None else {"ok": True}

        return await self._run_with_session(_op)

    async def _list_tools_async(self) -> List[Dict[str, Any]]:
        async def _op(session):
            await session.initialize()
            result = await session.list_tools()
            tools = result.tools if hasattr(result, "tools") else result
            return [self._normalize_tool(tool) for tool in tools]

        return await self._run_with_session(_op)

    async def _call_tool_async(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        async def _op(session):
            await session.initialize()
            result = await session.call_tool(name, arguments=arguments)
            return self._normalize_result(result)

        return await self._run_with_session(_op)

    async def _run_with_session(self, operation):
        transport_factory = self._transport_factory or self._default_transport_factory()
        session_factory = self._session_factory or self._default_session_factory()
        transport = transport_factory()
        async with transport as streams:
            read_stream, write_stream, *_ = streams
            async with session_factory(read_stream, write_stream) as session:
                return await operation(session)

    @staticmethod
    def _normalize_result(result: Any) -> Dict[str, Any]:
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        if isinstance(result, dict):
            return dict(result)
        if hasattr(result, "__dict__"):
            return dict(result.__dict__)
        return {"result": str(result)}

    @staticmethod
    def _normalize_tool(tool: Any) -> Dict[str, Any]:
        if hasattr(tool, "model_dump"):
            data = tool.model_dump()
            return dict(data)
        if isinstance(tool, dict):
            return dict(tool)
        if hasattr(tool, "__dict__"):
            return dict(tool.__dict__)
        return {"tool": str(tool)}

    def _default_transport_factory(self):
        try:
            if self.config.command:
                from mcp.client.stdio import stdio_client

                stdio_params_factory = self._stdio_params_factory or self._default_stdio_params_factory()
                server_params = stdio_params_factory(
                    command=self.config.command,
                    args=list(self.config.args),
                    env={**os.environ, **self.config.env},
                    cwd=self.config.cwd,
                )

                def factory():
                    return stdio_client(server_params)

                return factory
        except ImportError as exc:
            raise ImportError(
                "The official MCP Python SDK is required for SdkMCPClient. Install the 'mcp' package."
            ) from exc

        raise ValueError("McpClientConfig requires a stdio command.")

    @staticmethod
    def _default_session_factory():
        try:
            from mcp import ClientSession
        except ImportError as exc:
            raise ImportError(
                "The official MCP Python SDK is required for SdkMCPClient. Install the 'mcp' package."
            ) from exc
        return ClientSession

    @staticmethod
    def _default_stdio_params_factory():
        try:
            from mcp.client.stdio import StdioServerParameters
        except ImportError as exc:
            raise ImportError(
                "The official MCP Python SDK is required for SdkMCPClient. Install the 'mcp' package."
            ) from exc
        return StdioServerParameters

    def _record_tool_call(
        self,
        name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        is_error: bool,
    ) -> None:
        if not self.config.tool_call_log_path:
            return
        path = Path(self.config.tool_call_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "session_id": self.config.session_id,
            "tool_name": name,
            "arguments": dict(arguments),
            "is_error": is_error,
            "result": dict(result),
        }
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
