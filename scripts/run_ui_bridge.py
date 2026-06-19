"""Run a small local API bridge for the React UI."""

import base64
import hashlib
import json
import queue
import socket
import socketserver
import uuid
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.gui.bridge import GuiBridgeService
from ai_3d_modeling_agent.memory.session_paths import session_meetings_log_path


class BridgeHandler(BaseHTTPRequestHandler):
    service = GuiBridgeService(REPO_ROOT)
    
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0] or None
            self._send_json(self.service.bootstrap(session_id=session_id))
            return
        if parsed.path == "/api/session/state":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_session_state(session_id))
            return
        if parsed.path == "/api/progress":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.read_progress(session_id))
            return
        if parsed.path == "/api/activity/snapshot":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            cursor = query.get("cursor", [""])[0] or None
            self._send_json(self.service.get_activity_snapshot(session_id, cursor))
            return
        if parsed.path == "/api/test/activity-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_activity_truth_timeline(session_id))
            return
        if parsed.path == "/api/test/activity-event-trace":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_activity_event_trace(session_id))
            return
        if parsed.path == "/api/test/meeting-state-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_meeting_state_truth(session_id))
            return
        if parsed.path == "/api/test/planning-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_planning_truth(session_id))
            return
        if parsed.path == "/api/test/runtime-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_runtime_truth(session_id))
            return
        if parsed.path == "/api/test/inspector-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_inspector_truth(session_id))
            return
        if parsed.path == "/api/test/retry-truth":
            if not self.service.live_bridge_smoke_mode:
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_retry_truth(session_id))
            return
        if parsed.path == "/api/session/workspace":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_session_workspace(session_id))
            return
        if parsed.path == "/api/mcp/status":
            self._send_json(self.service.get_blender_mcp_status())
            return
        if parsed.path == "/api/run/status":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.get_run_status(session_id))
            return
        if parsed.path == "/api/run/console":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.read_console_log(session_id))
            return
        if parsed.path == "/api/mcp/tool-calls":
            query = parse_qs(parsed.query)
            session_id = query.get("session_id", [""])[0]
            self._send_json(self.service.read_mcp_tool_calls(session_id))
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        payload = self._read_json_body()
        if self.path == "/api/session/new":
            self._send_json(self.service.create_session())
            return
        if self.path == "/api/session/delete":
            self._send_json(self.service.delete_session(str(payload.get("session_id", ""))))
            return
        if self.path == "/api/session/workspace":
            self._send_json(
                self.service.save_session_workspace(
                    str(payload.get("session_id", "")),
                    payload,
                )
            )
            return
        if self.path == "/api/activity/append":
            self._send_json(
                self.service.append_activity(
                    str(payload.get("session_id", "")),
                    payload,
                )
            )
            return
        if self.path == "/api/session/current":
            self._send_json(self.service.set_current_session(str(payload.get("session_id", ""))))
            return
        if self.path == "/api/diagnostics/live":
            self._send_json(self.service.run_live_diagnostics(payload))
            return
        if self.path in {"/api/agent-orchestrator/live", "/api/llm/endpoint/live"}:
            self._send_json(self.service.verifyAgentOrchestratorEndpoint(payload))
            return
        if self.path == "/api/agent-orchestrator/models":
            self._send_json(self.service.listAgentOrchestratorModels(payload))
            return
        if self.path == "/api/mcp/connect":
            self._send_json(self.service.connect_blender_mcp(payload))
            return
        if self.path == "/api/mcp/disconnect":
            self._send_json(self.service.disconnect_blender_mcp())
            return
        if self.path == "/api/settings":
            self._send_json(self.service.save_settings(payload))
            return
        if self.path == "/api/run/start":
            self._send_json(self.service.start_run(payload))
            return
        if self.path == "/api/run/stop":
            self._send_json(self.service.stop_run(str(payload.get("session_id", ""))))
            return
        if self.path == "/api/run/retry":
            self._send_json(
                self.service.retry_run(
                    str(payload.get("session_id", "")),
                    int(payload.get("retry_count", 1)),
                )
            )
            return
        if self.path == "/api/run/retry/stop":
            self._send_json(self.service.clear_retry_prompt(str(payload.get("session_id", ""))))
            return
        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json_body(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _send_json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            pass  # Client disconnected before response was sent


class ActivityWebSocketHandler(socketserver.BaseRequestHandler):
    service = BridgeHandler.service

    def handle(self) -> None:
        session_id = ""
        connection_id = uuid.uuid4().hex
        subscriber_queue: queue.Queue | None = None
        self.request.settimeout(10.0)
        try:
            raw_request = self._read_http_request()
            if not raw_request:
                return
            path, headers = self._parse_request_headers(raw_request)
            if headers.get("upgrade", "").lower() != "websocket":
                return
            websocket_key = headers.get("sec-websocket-key", "")
            if not websocket_key:
                return
            session_id = parse_qs(urlparse(path).query).get("session_id", [""])[0]
            print(f"[WS] Client connected: session_id={session_id}", flush=True)
            self._send_handshake(websocket_key)
            subscriber_queue = self.service.register_activity_subscriber(session_id, connection_id)
            self.request.settimeout(2.0)
            last_cursor = ""
            seen_meeting_event_ids: set[str] = set()
            event_count = 0
            while True:
                if self._client_connection_closed():
                    print(f"[WS] Client closed connection: session_id={session_id}", flush=True)
                    return
                # 1. Real-time meeting events from in-process pipeline
                if subscriber_queue is not None:
                    try:
                        while True:
                            event = subscriber_queue.get_nowait()
                            event_count += 1
                            print(f"[WS] Sending event #{event_count}: {event.get('type', 'unknown')}", flush=True)
                            self._safe_send_frame(session_id, event)
                    except queue.Empty:
                        pass

                # 2. Snapshot sync signal when any session state changes
                try:
                    if self.service.live_bridge_smoke_mode:
                        for meeting_event in self._read_smoke_meeting_events(session_id):
                            event_id = str(meeting_event.get("event_id", "")).strip()
                            if not event_id or event_id in seen_meeting_event_ids:
                                continue
                            seen_meeting_event_ids.add(event_id)
                            meeting_stream_event = self.service._make_stream_event(
                                session_id,
                                "meeting_event",
                                meeting_event,
                            )
                            self.service.record_activity_stream_event(session_id, meeting_stream_event)
                            self._safe_send_frame(session_id, meeting_stream_event)
                    snapshot = self.service.get_activity_snapshot(session_id)
                    cursor = snapshot.get("server_cursor", "")
                    if cursor != last_cursor:
                        snapshot_required_event = self.service._make_stream_event(
                            session_id,
                            "snapshot_required",
                            {"reason": "state_changed"},
                        )
                        self.service.record_activity_stream_event(session_id, snapshot_required_event)
                        self._safe_send_frame(session_id, snapshot_required_event)
                        last_cursor = cursor
                except Exception as exc:
                    if self._is_disconnect_error(exc):
                        print(f"[WS] Connection closed during send: session_id={session_id}", flush=True)
                        return
                    print(f"[WS] Snapshot sync error for session_id={session_id}: {exc}", flush=True)
                time.sleep(0.1)
        except (ConnectionError, OSError, TimeoutError):
            print(f"[WS] Client disconnected: session_id={session_id}", flush=True)
            return
        finally:
            if session_id:
                self.service.unregister_activity_subscriber(session_id, connection_id)

    def _safe_send_frame(self, session_id: str, event: dict[str, object]) -> None:
        try:
            self._send_text_frame(json.dumps(event, ensure_ascii=False))
        except Exception as exc:
            if self._is_disconnect_error(exc):
                raise
            raise

    def _client_connection_closed(self) -> bool:
        try:
            self.request.settimeout(0.0)
            peeked = self.request.recv(1, socket.MSG_PEEK)
            if peeked == b"":
                return True
            if peeked:
                return True
        except (BlockingIOError, socket.timeout):
            return False
        except OSError as exc:
            return self._is_disconnect_error(exc)
        finally:
            self.request.settimeout(2.0)
        return False

    @staticmethod
    def _is_disconnect_error(exc: Exception) -> bool:
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError)):
            return True
        if isinstance(exc, OSError):
            win_error = getattr(exc, "winerror", None)
            if win_error in {10053, 10054}:
                return True
        return False

    def _read_smoke_meeting_events(self, session_id: str) -> list[dict[str, object]]:
        if not session_id:
            return []
        path = session_meetings_log_path(self.service.runtime_root, session_id)
        if not path.exists():
            return []
        events: list[dict[str, object]] = []
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
        return events

    def _read_http_request(self) -> str:
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > 65536:
                break
        return buffer.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_request_headers(raw_request: str) -> tuple[str, dict[str, str]]:
        lines = raw_request.split("\r\n")
        request_line = lines[0] if lines else "GET / HTTP/1.1"
        parts = request_line.split(" ")
        path = parts[1] if len(parts) > 1 else "/"
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return path, headers

    def _send_handshake(self, websocket_key: str) -> None:
        accept = base64.b64encode(
            hashlib.sha1(
                (websocket_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")
            ).digest()
        ).decode("ascii")
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            "\r\n"
        )
        self.request.sendall(response.encode("utf-8"))

    def _send_text_frame(self, payload: str) -> None:
        encoded = payload.encode("utf-8")
        header = bytearray()
        header.append(0x81)
        payload_length = len(encoded)
        if payload_length <= 125:
            header.append(payload_length)
        elif payload_length <= 65535:
            header.append(126)
            header.extend(payload_length.to_bytes(2, byteorder="big"))
        else:
            header.append(127)
            header.extend(payload_length.to_bytes(8, byteorder="big"))
        self.request.sendall(bytes(header) + encoded)


class ThreadingActivityWebSocketServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Suppress ECONNABORTED errors during client disconnect."""
        import sys
        exc_type = sys.exc_info()[0]
        if exc_type in (ConnectionError, OSError):
            # Suppress connection errors during page refresh
            return
        super().handle_error(request, client_address)


def main() -> int:
    http_port = int(__import__("os").environ.get("AI3D_UI_BRIDGE_HTTP_PORT", "8765"))
    ws_port = int(__import__("os").environ.get("AI3D_UI_BRIDGE_WS_PORT", "8766"))
    server = ThreadingHTTPServer(("127.0.0.1", http_port), BridgeHandler)
    websocket_server = ThreadingActivityWebSocketServer(("127.0.0.1", ws_port), ActivityWebSocketHandler)
    websocket_thread = threading.Thread(target=websocket_server.serve_forever, daemon=True)
    websocket_thread.start()
    print(f"UI bridge listening on http://127.0.0.1:{http_port}")
    print(f"Activity websocket listening on ws://127.0.0.1:{ws_port}/ws/activity")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        websocket_server.shutdown()
        websocket_server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
