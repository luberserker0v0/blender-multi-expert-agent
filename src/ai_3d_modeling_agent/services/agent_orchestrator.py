"""Agent Orchestrator client and LLM adapter for multi-expert runs."""

from __future__ import annotations

import base64
import io
import json
import os
import random
import socket
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class AgentOrchestratorError(RuntimeError):
    """Raised when Agent Orchestrator provisioning or messaging fails."""


@dataclass(frozen=True)
class AgentOrchestratorConfig:
    base_url: str
    model: str = ""
    conversation_id: str = ""
    destroy_on_finish: bool = True
    timeout_seconds: int = 120


@dataclass
class AgentOrchestratorSession:
    conversation_id: str
    ws_url: str
    skill_hashes: dict[str, str] = field(default_factory=dict)


ACTIVE_MARKDOWN_EXTRACTION_SKILLS = (
    "blender-build-actions",
    "blender-assembly-actions",
    "summarize-meeting-message",
)


class AgentOrchestratorClient:
    """Small stdlib-only client for Agent Orchestrator REST and WebSocket APIs."""

    def __init__(self, config: AgentOrchestratorConfig) -> None:
        if not str(config.base_url or "").strip():
            raise AgentOrchestratorError("agent_orchestrator_base_url is required")
        self.config = config
        self.base_url = str(config.base_url).rstrip("/")
        self.timeout = max(1, int(config.timeout_seconds or 120))
        self._ws: _JsonRpcWebSocket | None = None
        self._ws_url = ""
        self._conversation_id = ""
        self._rpc_id = 0

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def list_models(self) -> list[dict[str, Any]]:
        if self._conversation_id:
            return self.list_provider_models(self._conversation_id)
        try:
            data = self._request_any("GET", "/api/models")
        except AgentOrchestratorError as exc:
            if "failed with 404" in str(exc):
                return []
            raise
        if not isinstance(data, list):
            raise AgentOrchestratorError("Expected JSON array from /api/models")
        return [item for item in data if isinstance(item, dict)]

    def list_provider_models(self, conversation_id: str) -> list[dict[str, Any]]:
        data = self._request_any(
            "GET",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/providers",
        )
        if isinstance(data, dict) and isinstance(data.get("providers"), list):
            data = data["providers"]
        if not isinstance(data, list):
            raise AgentOrchestratorError("Expected JSON array from /providers")
        models: list[dict[str, Any]] = []
        for provider in data:
            if not isinstance(provider, dict):
                continue
            provider_id = str(provider.get("id", "")).strip()
            provider_name = str(provider.get("name", "")).strip() or provider_id
            provider_models = provider.get("models", [])
            if isinstance(provider_models, dict):
                iterable = provider_models.items()
            elif isinstance(provider_models, list):
                iterable = [(model, {}) for model in provider_models]
            else:
                iterable = []
            for model, model_info in iterable:
                model_id = str(model).strip()
                if not provider_id or not model_id:
                    continue
                model_name = model_id
                if isinstance(model_info, dict):
                    model_name = str(model_info.get("name") or model_info.get("id") or model_id)
                models.append(
                    {
                        "id": f"{provider_id}/{model_id}",
                        "provider": provider_id,
                        "provider_name": provider_name,
                        "model": model_id,
                        "name": model_name,
                    }
                )
        return models

    def create_conversation(self, *, default_agent: str = "moderator") -> AgentOrchestratorSession:
        _ = default_agent
        payload: dict[str, Any] = {}
        if self.config.conversation_id:
            payload["id"] = self.config.conversation_id
        data = self._request_json("POST", "/api/conversations", payload)
        conversation_id = str(data.get("id", "")).strip()
        ws_url = str(data.get("wsUrl", "")).strip()
        if not conversation_id or not ws_url:
            raise AgentOrchestratorError("Agent Orchestrator create_conversation returned no id/wsUrl")
        self._conversation_id = conversation_id
        return AgentOrchestratorSession(conversation_id=conversation_id, ws_url=ws_url)

    def read_config(self, conversation_id: str) -> dict[str, Any]:
        data = self._request_json("GET", f"/api/conversations/{urllib.parse.quote(conversation_id)}/config")
        opencode = data.get("opencode")
        if isinstance(opencode, dict):
            return opencode
        return data

    def write_config(self, conversation_id: str, config: dict[str, Any]) -> None:
        self._request_no_content(
            "POST",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/config",
            config,
        )

    def write_agent(self, conversation_id: str, name: str, content: str) -> None:
        self._request_no_content(
            "PUT",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/agents",
            {"name": name, "content": content},
        )

    def write_agent_config(self, conversation_id: str, content: str) -> None:
        self._request_no_content(
            "PUT",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/agent/config",
            {"content": content},
        )

    def write_file(self, conversation_id: str, path: str, content: str) -> None:
        self._request_no_content(
            "PUT",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/files",
            {"path": path, "content": content},
        )

    def upload_skill(self, conversation_id: str, name: str, directory: Path) -> dict[str, Any]:
        archive = _zip_directory(directory)
        path = f"/api/conversations/{urllib.parse.quote(conversation_id)}/skills/upload?name={urllib.parse.quote(name)}"
        self._request_raw("POST", path, archive, content_type="application/zip")
        return self._request_json(
            "GET",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/skills/{urllib.parse.quote(name)}/info",
        )

    def start(self, conversation_id: str) -> dict[str, Any]:
        return self._request_json("POST", f"/api/conversations/{urllib.parse.quote(conversation_id)}/start", {})

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/api/conversations/{urllib.parse.quote(conversation_id)}")

    def list_sessions(self, conversation_id: str) -> list[dict[str, Any]]:
        data = self._request_any("GET", f"/api/conversations/{urllib.parse.quote(conversation_id)}/sessions")
        if not isinstance(data, list):
            raise AgentOrchestratorError("Expected JSON array from /sessions")
        return [item for item in data if isinstance(item, dict)]

    def list_session_children(self, conversation_id: str, session_id: str) -> list[dict[str, Any]]:
        data = self._request_any(
            "GET",
            f"/api/conversations/{urllib.parse.quote(conversation_id)}/sessions/{urllib.parse.quote(session_id)}/children",
        )
        if not isinstance(data, list):
            raise AgentOrchestratorError("Expected JSON array from /sessions/:sid/children")
        return [item for item in data if isinstance(item, dict)]

    def get_events(self, conversation_id: str) -> list[dict[str, Any]]:
        data = self._request_any("GET", f"/api/conversations/{urllib.parse.quote(conversation_id)}/events")
        if not isinstance(data, list):
            raise AgentOrchestratorError("Expected JSON array from /events")
        return [item for item in data if isinstance(item, dict)]

    def wait_until_ready(self, conversation_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        last_state: dict[str, Any] = {}
        while time.monotonic() <= deadline:
            state = self.get_conversation(conversation_id)
            last_state = state
            session_id = str(state.get("sessionId", "")).strip()
            if state.get("ready") is True and session_id:
                return state
            status = str(state.get("status", "")).strip().lower()
            if status in {"error", "failed", "destroyed", "stopped"}:
                raise AgentOrchestratorError(f"AO conversation {conversation_id} is not ready: {state}")
            time.sleep(0.5)
        raise AgentOrchestratorError(f"AO conversation {conversation_id} did not become ready within {self.timeout}s: {last_state}")

    def stop(self, conversation_id: str) -> None:
        self._request_json("POST", f"/api/conversations/{urllib.parse.quote(conversation_id)}/stop", {})

    def delete(self, conversation_id: str) -> None:
        self._request_no_content("DELETE", f"/api/conversations/{urllib.parse.quote(conversation_id)}")

    def connect(self, ws_url: str) -> None:
        self._ws_url = ws_url
        self._ws = _JsonRpcWebSocket(ws_url, timeout=self.timeout)
        self._ws.connect()

    def send_message(self, *, text: str, agent: str = "", model: str = "") -> dict[str, Any]:
        if self._conversation_id:
            return self._send_message_rest(text=text, agent=agent, model=model)
        return self._send_message_with_retry(text=text, agent=agent, model=model, retries=3)

    def _send_message_rest(self, *, text: str, agent: str = "", model: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"text": text}
        if agent:
            payload["agent"] = agent
        if model or self.config.model:
            payload["model"] = model or self.config.model
        data = self._request_json(
            "POST",
            f"/api/conversations/{urllib.parse.quote(self._conversation_id)}/message",
            payload,
        )
        if not data:
            raise AgentOrchestratorError("AO REST message returned no result")
        return data

    def _send_message_with_retry(self, *, text: str, agent: str = "", model: str = "", retries: int = 1) -> dict[str, Any]:
        last_error: BaseException | None = None
        for attempt in range(retries + 1):
            try:
                return self._send_message_once(text=text, agent=agent, model=model)
            except (AgentOrchestratorError, OSError) as exc:
                last_error = exc
                if attempt >= retries or not _is_retryable_ws_error(exc):
                    raise
                self._reconnect_after_ws_error()
        raise AgentOrchestratorError(f"AO message.send failed after reconnect: {last_error}")

    def _send_message_once(self, *, text: str, agent: str = "", model: str = "") -> dict[str, Any]:
        if self._ws is None:
            raise AgentOrchestratorError("WebSocket is not connected")
        self._rpc_id += 1
        params: dict[str, Any] = {"text": text}
        if agent:
            params["agent"] = agent
        if model or self.config.model:
            params["model"] = model or self.config.model
        response = self._ws.request(self._rpc_id, "message.send", params)
        if "error" in response:
            message = response.get("error", {}).get("message", response["error"])
            raise AgentOrchestratorError(f"AO message.send failed: {message}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise AgentOrchestratorError("AO message.send returned no result")
        return result

    def _reconnect_after_ws_error(self) -> None:
        ws_url = self._ws_url
        if self._conversation_id:
            state = self.wait_until_ready(self._conversation_id)
            ws_url = str(state.get("wsUrl", "") or ws_url).strip()
        if not ws_url:
            raise AgentOrchestratorError("Cannot reconnect AO WebSocket: no wsUrl is known")
        try:
            self.close()
        finally:
            self.connect(ws_url)

    def close(self) -> None:
        if self._ws is not None:
            self._ws.close()
            self._ws = None

    def _request_json(self, method: str, path: str, payload: Any | None = None) -> dict[str, Any]:
        data = self._request_any(method, path, payload)
        if not isinstance(data, dict):
            raise AgentOrchestratorError(f"Expected JSON object from {path}")
        return data

    def _request_any(self, method: str, path: str, payload: Any | None = None) -> Any:
        raw = self._request_raw(method, path, None if payload is None else json.dumps(payload).encode("utf-8"))
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _request_no_content(self, method: str, path: str, payload: Any | None = None) -> None:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        self._request_raw(method, path, body)

    def _request_raw(
        self,
        method: str,
        path: str,
        body: bytes | None,
        *,
        content_type: str = "application/json",
    ) -> bytes:
        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AgentOrchestratorError(f"AO {method} {path} failed with {exc.code}: {detail}") from exc
        except OSError as exc:
            raise AgentOrchestratorError(f"AO {method} {path} failed: {exc}") from exc


class AgentOrchestratorLlmAdapter:
    """Adapter satisfying the multi-expert LlmInterface protocol."""

    supports_agent_orchestrator = True

    def __init__(self, client: AgentOrchestratorClient, *, model: str = "", prompt_observer: Any = None) -> None:
        self.client = client
        self.model = model
        self.prompt_observer = prompt_observer
        self.last_message_id = ""

    def call(
        self,
        system_prompt: str,
        messages: list[Any] | None = None,
        response_model: Any | None = None,
        sampling: Any | None = None,
        *,
        agent: str = "",
        label: str = "",
        skill: str = "",
        context: Any | None = None,
    ) -> str:
        _ = response_model, sampling
        context_agent = _agent_from_context(context)
        delegated_agent = context_agent or (agent if agent and agent != "moderator" else "")
        delegation_mode = _delegation_mode_from_context(context)
        route = "moderator"
        text = _format_prompt(system_prompt, messages or [], skill=skill)
        result = self.client.send_message(text=text, agent=route, model=self.model)
        response_text = str(result.get("text", ""))
        self.last_message_id = str(result.get("messageId", ""))
        if self.prompt_observer is not None:
            self.prompt_observer(
                {
                    "stage": _phase_from_context(context),
                    "label": label or f"ao:{route}",
                    "agent": route,
                    "delegated_agent": delegated_agent or "",
                    "delegation_mode": delegation_mode,
                    "skill": skill,
                    "message_id": self.last_message_id,
                    "prompt_preview": text[:600],
                    "response_preview": response_text[:600],
                }
            )
        return response_text


def provision_agent_orchestrator(
    client: AgentOrchestratorClient,
    *,
    repo_root: Path,
) -> AgentOrchestratorSession:
    client.health()
    session = client.create_conversation(default_agent="moderator")
    opencode_root = repo_root / ".opencode"

    config = dict(client.read_config(session.conversation_id))
    config = _deep_merge_dict(config, _load_project_opencode_config(opencode_root))
    config.pop("agent", None)
    config["default_agent"] = "moderator"
    model = str(getattr(getattr(client, "config", None), "model", "")).strip()
    if model:
        config["model"] = model
    client.write_config(session.conversation_id, config)

    agents_root = opencode_root / "agents"

    shared = opencode_root / "AGENTS.md"
    if shared.exists():
        client.write_agent_config(session.conversation_id, shared.read_text(encoding="utf-8"))

    skill_hashes: dict[str, str] = {}
    skills_root = opencode_root / "skills"
    for skill_name in ACTIVE_MARKDOWN_EXTRACTION_SKILLS:
        skill_dir = skills_root / skill_name
        if not skill_dir.exists():
            raise AgentOrchestratorError(f"Required AO extraction skill is missing: {skill_name}")
        info = client.upload_skill(session.conversation_id, skill_name, skill_dir)
        skill_hash = str(info.get("sha256") or info.get("hash") or "").strip()
        if skill_hash:
            skill_hashes[skill_name] = skill_hash

    for agent_path in sorted(agents_root.glob("*.md")):
        content = _render_agent_markdown_for_model(agent_path.read_text(encoding="utf-8"), model)
        client.write_agent(session.conversation_id, agent_path.stem, content)

    client.start(session.conversation_id)
    client.wait_until_ready(session.conversation_id)
    client.connect(session.ws_url)
    session.skill_hashes = skill_hashes
    return session


def _load_project_opencode_config(opencode_root: Path) -> dict[str, Any]:
    config_path = opencode_root / "opencode.json"
    if not config_path.exists():
        return {}
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentOrchestratorError(f"Invalid .opencode/opencode.json: {exc}") from exc
    if not isinstance(raw, dict):
        raise AgentOrchestratorError(".opencode/opencode.json must contain a JSON object.")
    return raw


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(current, value)
        else:
            merged[key] = value
    return merged


def _render_agent_markdown_for_model(content: str, model: str) -> str:
    if not model or not content.startswith("---\n"):
        return content
    parts = content.split("---", 2)
    if len(parts) != 3:
        return content
    frontmatter = parts[1]
    body = parts[2]
    lines = frontmatter.splitlines()
    replaced = False
    rendered_lines: list[str] = []
    for line in lines:
        if line.strip().startswith("model:"):
            rendered_lines.append(f"model: {model}")
            replaced = True
        else:
            rendered_lines.append(line)
    if not replaced:
        rendered_lines.append(f"model: {model}")
    return "---" + "\n".join(rendered_lines) + "\n---" + body


def _zip_directory(directory: Path) -> bytes:
    if not (directory / "SKILL.md").exists():
        raise AgentOrchestratorError(f"Skill directory missing SKILL.md: {directory}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(directory).as_posix())
    return buffer.getvalue()


def _format_prompt(system_prompt: str, messages: list[Any], *, skill: str = "") -> str:
    if skill:
        input_text = _format_prompt(system_prompt, messages, skill="")
        return f"/{skill} {input_text}".strip()
    parts: list[str] = []
    if system_prompt:
        parts.append(f"System instructions:\n{system_prompt}")
    if not parts and len(messages) == 1 and isinstance(messages[0], dict):
        content = str(messages[0].get("content", "") or "").strip()
        if content:
            return content
    if messages:
        rendered = []
        for message in messages:
            if isinstance(message, dict):
                rendered.append(f"[{message.get('role', 'user')}] {message.get('content', '')}")
            else:
                speaker = getattr(message, "speaker", "user")
                content = getattr(message, "content", str(message))
                rendered.append(f"[{speaker}] {content}")
        parts.append("Conversation/messages:\n" + "\n\n".join(rendered))
    return "\n\n".join(parts).strip()


def _agent_from_context(context: Any | None) -> str:
    if isinstance(context, dict):
        return str(context.get("agent_role") or context.get("ao_agent") or "").strip()
    return ""


def _phase_from_context(context: Any | None) -> str:
    if isinstance(context, dict):
        return str(context.get("phase_name") or "").strip()
    return ""


def _delegation_mode_from_context(context: Any | None) -> str:
    if isinstance(context, dict):
        return str(context.get("agent_orchestrator_delegation_mode") or "").strip()
    return ""


def _is_retryable_ws_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        isinstance(exc, OSError)
        or "websocket connection closed" in text
        or "websocket closed" in text
        or "connection aborted" in text
        or "winerror 10053" in text
    )


class _JsonRpcWebSocket:
    """Minimal client for unfragmented text JSON-RPC frames."""

    def __init__(self, url: str, *, timeout: int) -> None:
        self.url = url
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        parsed = urllib.parse.urlparse(self.url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        if parsed.scheme == "wss":
            raise AgentOrchestratorError("wss is not supported by the stdlib AO client")
        path = parsed.path or "/"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((host, port), timeout=self.timeout)
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise AgentOrchestratorError(f"WebSocket upgrade failed: {response[:200]!r}")
        self.sock = sock

    def request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}).encode("utf-8")
        self._send_text(payload)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            message = self._recv_text()
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue
            if data.get("id") == request_id:
                return data
        raise AgentOrchestratorError(f"Timed out waiting for JSON-RPC response {request_id}")

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _send_text(self, payload: bytes) -> None:
        if self.sock is None:
            raise AgentOrchestratorError("WebSocket is not connected")
        mask = random.randbytes(4) if hasattr(random, "randbytes") else os.urandom(4)
        length = len(payload)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def _recv_text(self) -> str:
        if self.sock is None:
            raise AgentOrchestratorError("WebSocket is not connected")
        first = self._recv_exact(2)
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        masked = bool(first[1] & 0x80)
        mask = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(length)
        if masked:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise AgentOrchestratorError("WebSocket closed")
        if opcode != 0x1:
            return ""
        return payload.decode("utf-8", errors="replace")

    def _recv_exact(self, size: int) -> bytes:
        if self.sock is None:
            raise AgentOrchestratorError("WebSocket is not connected")
        chunks = []
        remaining = size
        while remaining > 0:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise AgentOrchestratorError("WebSocket connection closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
