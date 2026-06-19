"""Unit tests for Agent Orchestrator provisioning and routing."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ai_3d_modeling_agent.services.agent_orchestrator import (
    AgentOrchestratorClient,
    AgentOrchestratorConfig,
    AgentOrchestratorLlmAdapter,
    AgentOrchestratorError,
    AgentOrchestratorSession,
    provision_agent_orchestrator,
)


def _write_active_skill(opencode: Path) -> None:
    for skill_name in ("blender-build-actions", "blender-assembly-actions", "summarize-meeting-message"):
        skill = opencode / "skills" / skill_name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(f"# {skill_name}\n", encoding="utf-8")


class _FakeAoClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.sent_messages: list[dict] = []

    def health(self) -> dict:
        self.calls.append(("health",))
        return {"ok": True}

    def create_conversation(self, *, default_agent: str = "moderator") -> AgentOrchestratorSession:
        self.calls.append(("create_conversation", default_agent))
        return AgentOrchestratorSession(conversation_id="conv-1", ws_url="ws://ao/ws")

    def read_config(self, conversation_id: str) -> dict:
        self.calls.append(("read_config", conversation_id))
        return {
            "$schema": "https://opencode.ai/config.json",
            "permission": {"bash": {"*": "deny"}},
        }

    def write_config(self, conversation_id: str, config: dict) -> None:
        self.calls.append(("write_config", conversation_id, config))

    def upload_skill(self, conversation_id: str, name: str, directory: Path) -> dict:
        self.calls.append(("upload_skill", conversation_id, name, (directory / "SKILL.md").exists()))
        return {"sha256": f"sha-{name}"}

    def write_agent_config(self, conversation_id: str, content: str) -> None:
        self.calls.append(("write_agent_config", conversation_id, content.strip()))

    def write_agent(self, conversation_id: str, name: str, content: str) -> None:
        self.calls.append(("write_agent", conversation_id, name, content.strip()))

    def start(self, conversation_id: str) -> dict:
        self.calls.append(("start", conversation_id))
        return {"status": "running"}

    def wait_until_ready(self, conversation_id: str) -> dict:
        self.calls.append(("wait_until_ready", conversation_id))
        return {"id": conversation_id, "status": "running", "ready": True, "sessionId": "ses_1"}

    def connect(self, ws_url: str) -> None:
        self.calls.append(("connect", ws_url))

    def send_message(self, *, text: str, agent: str = "", model: str = "") -> dict:
        self.sent_messages.append({"text": text, "agent": agent, "model": model})
        return {"text": f"reply from {agent}", "messageId": f"msg-{agent}"}


def test_provision_agent_orchestrator_sequence_and_hashes(tmp_path: Path) -> None:
    opencode = tmp_path / ".opencode"
    agents = opencode / "agents"
    (agents).mkdir(parents=True)
    _write_active_skill(opencode)
    (agents / "moderator.md").write_text("moderator agent", encoding="utf-8")
    (agents / "builder.md").write_text("builder agent", encoding="utf-8")
    (opencode / "AGENTS.md").write_text("shared rules", encoding="utf-8")
    client = _FakeAoClient()

    session = provision_agent_orchestrator(client, repo_root=tmp_path)  # type: ignore[arg-type]

    assert session.conversation_id == "conv-1"
    assert session.skill_hashes == {
        "blender-build-actions": "sha-blender-build-actions",
        "blender-assembly-actions": "sha-blender-assembly-actions",
        "summarize-meeting-message": "sha-summarize-meeting-message",
    }
    assert client.calls[0] == ("health",)
    assert client.calls[1] == ("create_conversation", "moderator")
    assert client.calls[2] == ("read_config", "conv-1")
    assert client.calls[3] == (
        "write_config",
        "conv-1",
        {
            "$schema": "https://opencode.ai/config.json",
            "permission": {"bash": {"*": "deny"}},
            "default_agent": "moderator",
        },
    )
    assert client.calls[4] == ("write_agent_config", "conv-1", "shared rules")
    assert ("upload_skill", "conv-1", "blender-build-actions", True) in client.calls
    assert ("upload_skill", "conv-1", "blender-assembly-actions", True) in client.calls
    assert ("upload_skill", "conv-1", "summarize-meeting-message", True) in client.calls
    assert ("write_agent", "conv-1", "builder", "builder agent") in client.calls
    assert ("write_agent", "conv-1", "moderator", "moderator agent") in client.calls
    assert client.calls[-3:] == [
        ("start", "conv-1"),
        ("wait_until_ready", "conv-1"),
        ("connect", "ws://ao/ws"),
    ]


def test_provision_agent_orchestrator_merges_configured_model(tmp_path: Path) -> None:
    opencode = tmp_path / ".opencode"
    (opencode / "agents").mkdir(parents=True)
    _write_active_skill(opencode)
    client = _FakeAoClient()
    client.config = AgentOrchestratorConfig(base_url="http://ao", model="openai/gpt-5")  # type: ignore[attr-defined]

    provision_agent_orchestrator(client, repo_root=tmp_path)  # type: ignore[arg-type]

    assert client.calls[3] == (
        "write_config",
        "conv-1",
        {
            "$schema": "https://opencode.ai/config.json",
            "permission": {"bash": {"*": "deny"}},
            "default_agent": "moderator",
            "model": "openai/gpt-5",
        },
    )


def test_provision_agent_orchestrator_merges_project_provider_and_overrides_agent_models(tmp_path: Path) -> None:
    opencode = tmp_path / ".opencode"
    agents = opencode / "agents"
    agents.mkdir(parents=True)
    _write_active_skill(opencode)
    (opencode / "opencode.json").write_text(
        json.dumps(
            {
                "permission": {
                    "read": {
                        "docs/blender_build_capabilities.md": "allow",
                    }
                },
                "provider": {
                    "my_local_lmstudio": {
                        "name": "my local lmstudio",
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {"baseURL": "http://127.0.0.1:25555/v1"},
                        "models": {"gemma": {"name": "gemma"}},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (agents / "builder.md").write_text(
        """---
description: Builder
mode: subagent
model: anthropic/claude-sonnet-4-20250514
temperature: 0.1
tools:
  write: false
  edit: false
  bash: false
---

Build action JSON only.
""",
        encoding="utf-8",
    )
    client = _FakeAoClient()
    client.config = AgentOrchestratorConfig(
        base_url="http://ao",
        model="my_local_lmstudio/gemma",
    )  # type: ignore[attr-defined]

    provision_agent_orchestrator(client, repo_root=tmp_path)  # type: ignore[arg-type]

    written_config = client.calls[3][2]
    assert written_config["permission"] == {
        "bash": {"*": "deny"},
        "read": {"docs/blender_build_capabilities.md": "allow"},
    }
    assert "agent" not in written_config
    assert written_config["default_agent"] == "moderator"
    assert written_config["model"] == "my_local_lmstudio/gemma"
    assert written_config["provider"]["my_local_lmstudio"]["npm"] == "@ai-sdk/openai-compatible"
    assert written_config["provider"]["my_local_lmstudio"]["models"]["gemma"]["name"] == "gemma"
    assert (
        "write_agent",
        "conv-1",
        "builder",
        """---
description: Builder
mode: subagent
model: my_local_lmstudio/gemma
temperature: 0.1
tools:
  write: false
  edit: false
  bash: false
---

Build action JSON only.""",
    ) in client.calls


def test_agent_orchestrator_client_uses_config_and_agent_config_endpoints() -> None:
    class RecordingClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(
                AgentOrchestratorConfig(
                    base_url="http://ao",
                    model="openai/gpt-5",
                    conversation_id="conv-custom",
                )
            )
            self.json_requests: list[tuple[str, str, Any | None]] = []
            self.no_content_requests: list[tuple[str, str, Any | None]] = []

        def _request_json(self, method: str, path: str, payload: Any | None = None) -> dict[str, Any]:
            self.json_requests.append((method, path, payload))
            if path == "/api/conversations":
                return {"id": "conv-custom", "wsUrl": "ws://ao/ws"}
            if path == "/api/conversations/conv-custom":
                return {"id": "conv-custom", "status": "running", "ready": True, "sessionId": "ses_1"}
            if path.endswith("/config"):
                return {"permission": {"bash": {"*": "deny"}}}
            return {}

        def _request_no_content(self, method: str, path: str, payload: Any | None = None) -> None:
            self.no_content_requests.append((method, path, payload))

    client = RecordingClient()

    session = client.create_conversation(default_agent="moderator")
    config = client.read_config(session.conversation_id)
    client.write_config(session.conversation_id, {"default_agent": "moderator", **config})
    client.write_agent_config(session.conversation_id, "shared rules")
    ready = client.wait_until_ready(session.conversation_id)

    assert client.json_requests[0] == ("POST", "/api/conversations", {"id": "conv-custom"})
    assert ("agent" not in client.json_requests[0][2]) and ("model" not in client.json_requests[0][2])
    assert client.json_requests[1] == ("GET", "/api/conversations/conv-custom/config", None)
    assert client.json_requests[2] == ("GET", "/api/conversations/conv-custom", None)
    assert ready["ready"] is True
    assert client.no_content_requests == [
        (
            "POST",
            "/api/conversations/conv-custom/config",
            {"default_agent": "moderator", "permission": {"bash": {"*": "deny"}}},
        ),
        ("PUT", "/api/conversations/conv-custom/agent/config", {"content": "shared rules"}),
    ]


def test_agent_orchestrator_client_unwraps_opencode_config_response() -> None:
    class WrappedConfigClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao"))

        def _request_json(self, method: str, path: str, payload: Any | None = None) -> dict[str, Any]:
            assert method == "GET"
            assert path == "/api/conversations/conv-1/config"
            return {
                "opencode": {
                    "permission": {"bash": {"*": "deny"}},
                    "model": "provider/model",
                }
            }

    client = WrappedConfigClient()

    assert client.read_config("conv-1") == {
        "permission": {"bash": {"*": "deny"}},
        "model": "provider/model",
    }


def test_agent_orchestrator_client_lists_provider_models_from_conversation() -> None:
    class ProviderClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao"))

        def _request_any(self, method: str, path: str, payload: Any | None = None) -> Any:
            assert method == "GET"
            assert path == "/api/conversations/conv-1/providers"
            return {
                "providers": [
                    {"id": "my_provider", "name": "My Provider", "models": ["alpha", "beta"]},
                    {"id": "dict_provider", "models": {"gamma": {"name": "Gamma"}}},
                ],
                "default": {"my_provider": "alpha"},
            }

    client = ProviderClient()

    assert client.list_provider_models("conv-1") == [
        {
            "id": "my_provider/alpha",
            "provider": "my_provider",
            "provider_name": "My Provider",
            "model": "alpha",
            "name": "alpha",
        },
        {
            "id": "my_provider/beta",
            "provider": "my_provider",
            "provider_name": "My Provider",
            "model": "beta",
            "name": "beta",
        },
        {
            "id": "dict_provider/gamma",
            "provider": "dict_provider",
            "provider_name": "dict_provider",
            "model": "gamma",
            "name": "Gamma",
        },
    ]


def test_agent_orchestrator_client_wait_until_ready_polls_until_ready() -> None:
    class PollingClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao", timeout_seconds=3))
            self.states = [
                {"id": "conv-1", "status": "running", "ready": False},
                {"id": "conv-1", "status": "running", "ready": True},
                {"id": "conv-1", "status": "running", "ready": True, "sessionId": "ses_1"},
            ]

        def get_conversation(self, conversation_id: str) -> dict[str, Any]:
            assert conversation_id == "conv-1"
            return self.states.pop(0)

    client = PollingClient()

    started = time.monotonic()
    state = client.wait_until_ready("conv-1")

    assert state["ready"] is True
    assert time.monotonic() - started < 2


def test_agent_orchestrator_client_wait_until_ready_fails_on_error_state() -> None:
    class ErrorClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao", timeout_seconds=3))

        def get_conversation(self, conversation_id: str) -> dict[str, Any]:
            return {"id": conversation_id, "status": "error", "ready": False, "error": "boom"}

    client = ErrorClient()

    try:
        client.wait_until_ready("conv-err")
    except Exception as exc:
        assert "not ready" in str(exc)
        assert "boom" in str(exc)
    else:
        raise AssertionError("wait_until_ready should fail on AO error status")


def test_agent_orchestrator_client_reconnects_once_when_message_send_ws_closes() -> None:
    class FlakyWebSocket:
        def __init__(self, url: str, *, timeout: int) -> None:
            self.url = url
            self.timeout = timeout

        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

        def request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
            raise AgentOrchestratorError("WebSocket connection closed")

    class HealthyWebSocket:
        def __init__(self, url: str, *, timeout: int) -> None:
            self.url = url
            self.timeout = timeout

        def connect(self) -> None:
            return None

        def close(self) -> None:
            return None

        def request(self, request_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"messageId": "msg-ok", "text": f"{method}:{params['agent']}:{params['model']}"},
            }

    class ReconnectingClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao", model="model-a"))
            self.reconnects = 0
            self._ws_url = "ws://ao/ws/conv-1"
            self._ws = FlakyWebSocket(self._ws_url, timeout=120)  # type: ignore[assignment]

        def _reconnect_after_ws_error(self) -> None:
            self.reconnects += 1
            self._ws = HealthyWebSocket(self._ws_url, timeout=120)  # type: ignore[assignment]

    client = ReconnectingClient()

    result = client.send_message(text="hello", agent="moderator")

    assert client.reconnects == 1
    assert result == {"messageId": "msg-ok", "text": "message.send:moderator:model-a"}


def test_agent_orchestrator_client_prefers_rest_message_when_conversation_id_is_known() -> None:
    class RestMessageClient(AgentOrchestratorClient):
        def __init__(self) -> None:
            super().__init__(AgentOrchestratorConfig(base_url="http://ao", model="model-a"))
            self.requests: list[tuple[str, str, Any | None]] = []

        def _request_json(self, method: str, path: str, payload: Any | None = None) -> dict[str, Any]:
            self.requests.append((method, path, payload))
            if path == "/api/conversations":
                return {"id": "conv-1", "wsUrl": "ws://ao/ws/conv-1"}
            if path == "/api/conversations/conv-1/message":
                return {"messageId": "msg-rest", "text": "ok"}
            return {}

    client = RestMessageClient()
    client.create_conversation()

    result = client.send_message(text="hello", agent="moderator")

    assert result == {"messageId": "msg-rest", "text": "ok"}
    assert client.requests[-1] == (
        "POST",
        "/api/conversations/conv-1/message",
        {"text": "hello", "agent": "moderator", "model": "model-a"},
    )


def test_agent_orchestrator_llm_adapter_routes_agent_and_skill() -> None:
    client = _FakeAoClient()
    adapter = AgentOrchestratorLlmAdapter(client, model="gpt-test")

    reply = adapter.call(
        system_prompt="system",
        messages=[{"role": "user", "content": "make JSON"}],
        agent="moderator",
        skill="extract-design-artifact",
        label="design.extraction",
        context={"phase_name": "design"},
    )

    assert reply == "reply from moderator"
    assert adapter.last_message_id == "msg-moderator"
    assert client.sent_messages[0]["agent"] == "moderator"
    assert client.sent_messages[0]["model"] == "gpt-test"
    assert client.sent_messages[0]["text"].startswith("/extract-design-artifact ")
    assert "loaded skill named" not in client.sent_messages[0]["text"]


def test_agent_orchestrator_llm_adapter_always_routes_to_moderator() -> None:
    client = _FakeAoClient()
    adapter = AgentOrchestratorLlmAdapter(client)

    adapter.call(
        system_prompt="system",
        messages=[],
        context={"agent_role": "builder", "phase_name": "build"},
    )

    assert client.sent_messages[0]["agent"] == "moderator"


def test_agent_orchestrator_llm_adapter_keeps_focused_subagent_context_on_moderator_route() -> None:
    client = _FakeAoClient()
    adapter = AgentOrchestratorLlmAdapter(client)

    adapter.call(
        system_prompt="",
        messages=[{"role": "user", "content": "focused task"}],
        context={
            "agent_role": "specifier",
            "phase_name": "spec",
            "current_todo_group": {"target_name": "leg"},
        },
    )

    assert client.sent_messages[0]["agent"] == "moderator"
    assert client.sent_messages[0]["text"] == "focused task"


def test_agent_orchestrator_llm_adapter_observes_delegated_agent() -> None:
    client = _FakeAoClient()
    observed: list[dict] = []
    adapter = AgentOrchestratorLlmAdapter(client, prompt_observer=observed.append)

    adapter.call(
        system_prompt="system",
        messages=[],
        agent="moderator",
        label="build.action_plan",
        context={"agent_role": "builder", "phase_name": "build"},
    )

    assert client.sent_messages[0]["agent"] == "moderator"
    assert observed[0]["agent"] == "moderator"
    assert observed[0]["delegated_agent"] == "builder"
