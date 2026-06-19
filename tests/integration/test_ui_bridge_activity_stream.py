from __future__ import annotations

import base64
import hashlib
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
for candidate in (SRC_ROOT, SCRIPTS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ai_3d_modeling_agent.gui.bridge import GuiBridgeService
from ai_3d_modeling_agent.memory.session_paths import session_console_log_path
from run_ui_bridge import ActivityWebSocketHandler, ThreadingActivityWebSocketServer


def _connect_websocket(port: int, session_id: str) -> socket.socket:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(b"test-key").decode("ascii")
    request = (
        f"GET /ws/activity?session_id={session_id} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode("utf-8"))
    response = sock.recv(4096).decode("utf-8", errors="replace")
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")).digest()
    ).decode("ascii")
    assert "101 Switching Protocols" in response
    assert f"Sec-WebSocket-Accept: {accept}" in response
    sock.settimeout(2)
    return sock


def _read_text_frame(sock: socket.socket, timeout: float = 2.0) -> dict:
    sock.settimeout(timeout)
    first = sock.recv(2)
    if len(first) < 2:
        raise AssertionError("Incomplete websocket frame header")
    payload_length = first[1] & 0x7F
    if payload_length == 126:
        payload_length = int.from_bytes(sock.recv(2), byteorder="big")
    elif payload_length == 127:
        payload_length = int.from_bytes(sock.recv(8), byteorder="big")
    payload = b""
    while len(payload) < payload_length:
        payload += sock.recv(payload_length - len(payload))
    return json.loads(payload.decode("utf-8"))


@pytest.fixture
def websocket_server():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        service = GuiBridgeService(repo_root)
        service.mcp_status = {
            "enabled": True,
            "state": "connected",
            "message": "connected",
            "tools": [],
            "server_name": "blender",
        }
        ActivityWebSocketHandler.service = service
        server = ThreadingActivityWebSocketServer(("127.0.0.1", 0), ActivityWebSocketHandler)
        server.daemon_threads = True
        server.block_on_close = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield service, server.server_address[1], repo_root
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_websocket_emits_snapshot_required_on_connect_and_state_change(websocket_server):
    service, port, _ = websocket_server
    session_id = service.create_session()["session_id"]

    sock = _connect_websocket(port, session_id)
    try:
        first_event = _read_text_frame(sock)
        assert first_event["type"] == "snapshot_required"
        assert first_event["session_id"] == session_id
        assert first_event["sequence"] == 1
        initial_cursor = first_event["server_cursor"]

        service.append_activity(
            session_id,
            {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"}]},
        )

        second_event = _read_text_frame(sock)
        assert second_event["type"] == "snapshot_required"
        assert second_event["session_id"] == session_id
        assert second_event["sequence"] == 2
        assert second_event["server_cursor"] != initial_cursor
    finally:
        sock.close()


def test_websocket_does_not_emit_additional_snapshot_required_without_state_change(websocket_server):
    service, port, _ = websocket_server
    session_id = service.create_session()["session_id"]

    sock = _connect_websocket(port, session_id)
    try:
        first_event = _read_text_frame(sock)
        assert first_event["type"] == "snapshot_required"
        with pytest.raises(socket.timeout):
            _read_text_frame(sock, timeout=0.35)
    finally:
        sock.close()


def test_reconnect_receives_current_cursor_and_subsequent_changes(websocket_server):
    service, port, repo_root = websocket_server
    session_id = service.create_session()["session_id"]

    first_socket = _connect_websocket(port, session_id)
    try:
        first_event = _read_text_frame(first_socket)
        assert first_event["sequence"] == 1
    finally:
        first_socket.close()

    service.append_activity(
        session_id,
        {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "Recovered", "timestamp": "10:00"}]},
    )
    reconnect_socket = _connect_websocket(port, session_id)
    try:
        reconnect_event = _read_text_frame(reconnect_socket)
        assert reconnect_event["type"] == "snapshot_required"
        assert reconnect_event["server_cursor"] == service.get_activity_snapshot(session_id)["server_cursor"]

        time.sleep(1.1)
        console_path = session_console_log_path(repo_root / "data" / "runtime", session_id)
        console_path.parent.mkdir(parents=True, exist_ok=True)
        console_path.write_text("line 1\n", encoding="utf-8")

        changed_event = _read_text_frame(reconnect_socket)
        assert changed_event["type"] == "snapshot_required"
        assert changed_event["server_cursor"] != reconnect_event["server_cursor"]
    finally:
        reconnect_socket.close()


def test_websocket_survives_idle_mcp_without_backend_settings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        service = GuiBridgeService(repo_root)
        ActivityWebSocketHandler.service = service
        server = ThreadingActivityWebSocketServer(("127.0.0.1", 0), ActivityWebSocketHandler)
        server.daemon_threads = True
        server.block_on_close = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            session_id = service.create_session()["session_id"]
            sock = _connect_websocket(server.server_address[1], session_id)
            try:
                event = _read_text_frame(sock)
                assert event["type"] == "snapshot_required"
                assert event["session_id"] == session_id
                assert service.get_activity_snapshot(session_id)["mcp_status"]["state"] == "idle"
            finally:
                sock.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_websocket_emits_new_cursor_for_same_second_multiple_activity_appends(websocket_server):
    service, port, _ = websocket_server
    session_id = service.create_session()["session_id"]

    sock = _connect_websocket(port, session_id)
    try:
        first_event = _read_text_frame(sock)
        assert first_event["type"] == "snapshot_required"

        service.append_activity(
            session_id,
            {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"}]},
        )
        second_event = _read_text_frame(sock)

        service.append_activity(
            session_id,
            {"activity": [{"id": "a-2", "kind": "system", "title": "System", "body": "Second", "timestamp": "10:00"}]},
        )
        third_event = _read_text_frame(sock)

        assert second_event["server_cursor"] != first_event["server_cursor"]
        assert third_event["server_cursor"] != second_event["server_cursor"]
    finally:
        sock.close()


def test_same_session_double_connection_broadcasts_to_both_subscribers(websocket_server):
    service, port, _ = websocket_server
    session_id = service.create_session()["session_id"]

    sock_a = _connect_websocket(port, session_id)
    sock_b = _connect_websocket(port, session_id)
    try:
        first_a = _read_text_frame(sock_a)
        first_b = _read_text_frame(sock_b)
        assert first_a["type"] == "snapshot_required"
        assert first_b["type"] == "snapshot_required"
        assert service.get_activity_subscriber_count(session_id) == 2

        event = service._make_stream_event(
            session_id,
            "meeting_event",
            {
                "event_id": "meeting-double-1",
                "phase": "plan",
                "kind": "proposal",
                "speaker": "Planner",
                "role": "planner",
                "round": 1,
                "summary": "Broadcast test event.",
                "full_content": "Broadcast test event.",
                "timestamp": "10:00",
                "schema_version": 1,
            },
        )
        service.publish_activity_stream_event(session_id, event)

        event_a = _read_text_frame(sock_a)
        event_b = _read_text_frame(sock_b)
        assert event_a["type"] == "meeting_event"
        assert event_b["type"] == "meeting_event"
        assert event_a["event_id"] == event_b["event_id"] == event["event_id"]
    finally:
        sock_a.close()
        sock_b.close()


def test_closed_connection_is_unregistered_and_remaining_subscriber_keeps_receiving_events(websocket_server):
    service, port, _ = websocket_server
    session_id = service.create_session()["session_id"]

    stale_sock = _connect_websocket(port, session_id)
    live_sock = _connect_websocket(port, session_id)
    try:
        _read_text_frame(stale_sock)
        _read_text_frame(live_sock)
        assert service.get_activity_subscriber_count(session_id) == 2

        stale_sock.close()

        first_event = service._make_stream_event(
            session_id,
            "meeting_event",
            {
                "event_id": "meeting-prune-1",
                "phase": "plan",
                "kind": "response",
                "speaker": "Planner",
                "role": "planner",
                "round": 1,
                "summary": "First post-close event.",
                "full_content": "First post-close event.",
                "timestamp": "10:00",
                "schema_version": 1,
            },
        )
        service.publish_activity_stream_event(session_id, first_event)
        received = _read_text_frame(live_sock)
        assert received["event_id"] == first_event["event_id"]

        deadline = time.time() + 2.0
        while time.time() < deadline and service.get_activity_subscriber_count(session_id) != 1:
            time.sleep(0.05)
        assert service.get_activity_subscriber_count(session_id) == 1

        second_event = service._make_stream_event(
            session_id,
            "meeting_event",
            {
                "event_id": "meeting-prune-2",
                "phase": "plan",
                "kind": "resolution",
                "speaker": "Moderator",
                "role": "moderator",
                "round": 1,
                "summary": "Second post-close event.",
                "full_content": "Second post-close event.",
                "timestamp": "10:01",
                "schema_version": 1,
            },
        )
        service.publish_activity_stream_event(session_id, second_event)
        received_again = _read_text_frame(live_sock)
        assert received_again["event_id"] == second_event["event_id"]
    finally:
        try:
            live_sock.close()
        except OSError:
            pass
