import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.gui.bridge import GuiBridgeService
from ai_3d_modeling_agent.memory.session_paths import (
    ensure_session_runtime_dir,
    session_assembly_execution_plan_path,
    session_build_execution_plan_path,
    session_capture_dir,
    session_console_log_path,
    session_meeting_state_path,
    session_plan_artifact_path,
    session_mcp_log_path,
    session_pending_interaction_path,
    session_progress_path,
)


def write_backend_settings(
    repo_root: Path,
    *,
    command: str = "uv",
    cwd: str = "C:\\blender_mcp\\mcp",
    args: Optional[List[str]] = None,
    env: Optional[dict] = None,
) -> Path:
    path = repo_root / "settings.json"
    path.write_text(
        json.dumps(
            {
                "llm": {
                    "endpoint_url": "http://127.0.0.1:8080",
                    "model": "local-model",
                    "api_key": "",
                },
                "mcpServers": {
                    "blender": {
                        "command": command,
                        "cwd": cwd,
                        "args": args or ["--directory", cwd, "run", "blender-mcp"],
                        "env": env or {},
                    }
                },
                "pipeline": {
                    "max_part_refinement_rounds": 3,
                    "max_assembly_rounds": 3,
                },
                "agent_orchestrator": {
                    "base_url": "http://127.0.0.1:4111",
                    "model": "",
                    "conversation_id": "",
                    "destroy_on_finish": True,
                    "timeout_seconds": 120,
                },
                "yolo": {
                    "enabled": False,
                    "model_path": "",
                    "viewpoints": ["front"],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


class TestGuiBridgeService(unittest.TestCase):
    def test_read_json_returns_empty_dict_for_partial_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"
            path.write_text("", encoding="utf-8")

            self.assertEqual(GuiBridgeService._read_json(path), {})

    def test_write_json_uses_readable_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "progress.json"

            GuiBridgeService._write_json(path, {"status": "failed"})

            self.assertEqual(GuiBridgeService._read_json(path), {"status": "failed"})

    def test_bootstrap_returns_empty_current_session_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            (repo_root / "data" / "runtime" / "session_data").mkdir(parents=True)
            service = GuiBridgeService(repo_root)

            payload = service.bootstrap()

            self.assertIn("current_session_id", payload)
            self.assertEqual(payload["current_session_id"], "")
            self.assertEqual(payload["sessions"], [])
            self.assertIn("settings", payload)
            self.assertIn("mcp_status", payload)

    def test_create_session_persists_current_session_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            result = service.create_session()
            session_id = result["session_id"]
            payload = service.bootstrap()
            session_state = service.get_session_state(session_id)

            self.assertEqual(payload["current_session_id"], session_id)
            self.assertEqual(payload["sessions"][0]["id"], session_id)
            self.assertEqual(session_state["workspace"]["referenceImages"], [])

    def test_bootstrap_recovers_corrupted_ui_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            ui_state_path = repo_root / "data" / "runtime" / "gui" / "ui_state.json"
            ui_state_path.parent.mkdir(parents=True)
            ui_state_path.write_text(
                json.dumps(
                    {
                        "current_session_id": "gui-001",
                        "sessions": [{"id": "gui-001", "title": "Recovered", "updatedAt": 1}],
                        "workspaces": {"gui-001": {"taskInput": "chair", "referenceText": "", "referenceImages": [], "activity": []}},
                    },
                    ensure_ascii=False,
                )
                + json.dumps({"garbage": True}, ensure_ascii=False),
                encoding="utf-8",
            )
            service = GuiBridgeService(repo_root)

            payload = service.bootstrap()
            session_state = service.get_session_state("gui-001")

            self.assertEqual(payload["current_session_id"], "gui-001")
            self.assertEqual(session_state["workspace"]["taskInput"], "chair")
            repaired = json.loads(ui_state_path.read_text(encoding="utf-8"))
            self.assertEqual(repaired["current_session_id"], "gui-001")

    def test_save_settings_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            result = service.save_settings(
                {
                    "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                    "agent_orchestrator_model": "saved-model",
                    "max_part_refinement_rounds": 4,
                    "max_assembly_rounds": 2,
                    "use_yolo_perception": True,
                    "yolo_model_path": "D:\\models\\saved.pt",
                    "yolo_viewpoints": ["front", "side"],
                }
            )

            self.assertTrue(result["saved"])
            loaded = service.load_settings()
            self.assertEqual(loaded["agent_orchestrator_base_url"], "http://127.0.0.1:4111")
            self.assertEqual(loaded["agent_orchestrator_model"], "saved-model")
            self.assertEqual(loaded["yolo_viewpoints"], ["front", "side"])

    def test_start_run_uses_inprocess_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            service = GuiBridgeService(repo_root)

            class FakeClient:
                def __init__(self, config):
                    self.config = config

                def initialize(self):
                    return {"ok": True}

                def list_tools(self):
                    return [{"name": "get_objects_summary"}]

            with patch("ai_3d_modeling_agent.gui.bridge.SdkMCPClient", FakeClient):
                result = service.start_run(
                    {
                        "task": "build a chair",
                        "session_id": "gui-001",
                        "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                        "reference_texts": ["simple chair"],
                    }
                )

            self.assertTrue(result["started"])
            self.assertEqual(result["session_id"], "gui-001")
            self.assertIn(result["run_status"]["workflow_status"], ("starting", "running"))
            self.assertEqual(service.get_activity_subscriber_count("gui-001"), 0)

    def test_get_run_status_reports_completed_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            class FakeProcess:
                pid = 4321

                def poll(self):
                    return 0

            service.processes["gui-001"] = FakeProcess()
            service.run_statuses["gui-001"] = {
                "session_id": "gui-001",
                "workflow_status": "running",
                "process_status": "running",
                "error_message": "",
                "last_command": ["python", "scripts/run_pipeline.py"],
                "pid": 4321,
                "exit_code": None,
            }

            status = service.get_run_status("gui-001")

            self.assertEqual(status["workflow_status"], "completed")
            self.assertEqual(status["process_status"], "exited")
            self.assertEqual(status["exit_code"], 0)

    def test_stop_run_updates_runtime_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            class FakeProcess:
                pid = 5555
                terminated = False

                def poll(self):
                    return 0 if self.terminated else None

                def terminate(self):
                    self.terminated = True
                    return None

                def wait(self, timeout=None):
                    self.terminated = True
                    return 0

            service.processes["gui-001"] = FakeProcess()
            log_path = service.console_log_path("gui-001")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            service.process_log_handles["gui-001"] = log_path.open("a", encoding="utf-8")
            service.run_statuses["gui-001"] = {
                "session_id": "gui-001",
                "workflow_status": "running",
                "process_status": "running",
                "error_message": "",
                "last_command": ["python", "scripts/run_pipeline.py"],
                "pid": 5555,
                "exit_code": None,
            }

            result = service.stop_run("gui-001")

            self.assertTrue(result["stopped"])
            self.assertEqual(result["run_status"]["workflow_status"], "idle")
            self.assertEqual(result["run_status"]["process_status"], "terminated")
            log_content = log_path.read_text(encoding="utf-8")
            self.assertIn("STOP REQUESTED", log_content)
            self.assertIn("STOP CONFIRMED", log_content)

    def test_delete_session_removes_progress_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            ensure_session_runtime_dir(runtime_root, "gui-001")
            progress_path = session_progress_path(runtime_root, "gui-001")
            progress_path.write_text(json.dumps({"session_id": "gui-001"}), encoding="utf-8")
            session_console_log_path(runtime_root, "gui-001").write_text("console", encoding="utf-8")
            session_mcp_log_path(runtime_root, "gui-001").write_text("{}", encoding="utf-8")
            capture_dir = session_capture_dir(runtime_root, "gui-001")
            capture_dir.mkdir(parents=True, exist_ok=True)
            (capture_dir / "capture.png").write_bytes(b"fake")

            service = GuiBridgeService(repo_root)
            result = service.delete_session("gui-001")

            self.assertTrue(result["deleted"])
            self.assertFalse(progress_path.exists())
            self.assertFalse(session_console_log_path(runtime_root, "gui-001").exists())
            self.assertFalse(session_mcp_log_path(runtime_root, "gui-001").exists())
            self.assertFalse(capture_dir.exists())

    def test_save_session_workspace_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]

            result = service.save_session_workspace(
                session_id,
                {
                    "task_input": "build a chair",
                    "reference_text": "light wood",
                    "reference_images": ["chair.png"],
                    "activity": [{"id": "1", "kind": "user", "title": "You", "body": "build a chair", "timestamp": "10:00"}],
                    "title": "build a chair",
                },
            )

            workspace = service.get_session_workspace(session_id)
            self.assertTrue(result["saved"])
            self.assertTrue(workspace["exists"])
            self.assertEqual(workspace["workspace"]["taskInput"], "build a chair")
            self.assertEqual(workspace["workspace"]["referenceText"], "light wood")
            self.assertEqual(workspace["workspace"]["referenceImages"], ["chair.png"])

    def test_list_sessions_merges_ui_state_and_progress_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]

            progress_path = session_progress_path(runtime_root, session_id)
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps({"session_id": session_id, "task": "backend task title"}),
                encoding="utf-8",
            )

            sessions = service.list_sessions()

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["id"], session_id)
            self.assertEqual(sessions[0]["title"], "New modeling session")

    def test_list_sessions_prefers_workspace_task_over_untitled_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]

            service.save_session_workspace(
                session_id,
                {
                    "task_input": "build a wooden chair",
                    "reference_text": "",
                    "reference_images": [],
                    "activity": [],
                    "title": "Untitled session",
                },
            )

            sessions = service.list_sessions()

            self.assertEqual(sessions[0]["id"], session_id)
            self.assertEqual(sessions[0]["title"], "build a wooden chair")

    def test_connect_blender_mcp_parses_json_and_returns_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            service = GuiBridgeService(repo_root)

            class FakeClient:
                def __init__(self, config):
                    self.config = config

                def initialize(self):
                    return {"ok": True}

                def list_tools(self):
                    return [{"name": "get_context"}, {"name": "capture_view"}]

            with patch("ai_3d_modeling_agent.gui.bridge.SdkMCPClient", FakeClient):
                result = service.connect_blender_mcp({})

            self.assertEqual(result["state"], "connected")
            self.assertEqual(len(result["tools"]), 2)

    def test_run_live_diagnostics_checks_ao_and_blender_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            service = GuiBridgeService(repo_root)

            class FakeAgentOrchestratorClient:
                def __init__(self, config):
                    self.config = config

                def health(self):
                    return {"ok": True}

            class FakeMcpClient:
                def __init__(self, config):
                    self.config = config

                def initialize(self):
                    return {"ok": True}

                def list_tools(self):
                    return [{"name": "get_objects_summary"}]

                def call_tool(self, name, arguments=None):
                    return {"isError": False, "structuredContent": {"result": {"status": "ok"}}}

            with patch("ai_3d_modeling_agent.gui.bridge.AgentOrchestratorClient", FakeAgentOrchestratorClient):
                with patch("ai_3d_modeling_agent.gui.bridge.SdkMCPClient", FakeMcpClient):
                    result = service.run_live_diagnostics(
                        {
                            "session_id": "gui-001",
                            "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                        }
                    )

            self.assertTrue(result["ok"])
            self.assertEqual(len(result["checks"]), 4)
            self.assertTrue(all(item["ok"] for item in result["checks"]))
            self.assertEqual(service.get_blender_mcp_status()["state"], "connected")

    def test_ao_diagnostics_do_not_hide_mcp_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            service = GuiBridgeService(repo_root)

            class FakeAgentOrchestratorClient:
                def __init__(self, config):
                    self.config = config

                def health(self):
                    return {"ok": True}

            class FailingMcpClient:
                def __init__(self, config):
                    self.config = config

                def initialize(self):
                    raise RuntimeError("MCP unavailable for test")

            with patch("ai_3d_modeling_agent.gui.bridge.AgentOrchestratorClient", FakeAgentOrchestratorClient):
                with patch("ai_3d_modeling_agent.gui.bridge.SdkMCPClient", FailingMcpClient):
                    result = service.run_live_diagnostics(
                        {
                            "session_id": "gui-001",
                            "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                        }
                    )

            self.assertFalse(result["ok"])
            self.assertEqual(service.get_blender_mcp_status()["state"], "failed")

    def test_list_agent_orchestrator_models_uses_ao_models_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            service = GuiBridgeService(repo_root)

            class FakeAgentOrchestratorClient:
                def __init__(self, config):
                    self.config = config

                def list_models(self):
                    return [
                        {"id": "openai/gpt-5", "provider": "openai", "model": "gpt-5"},
                        {"id": "anthropic/claude-3-5-sonnet", "provider": "anthropic", "model": "claude-3-5-sonnet"},
                    ]

            with patch("ai_3d_modeling_agent.gui.bridge.AgentOrchestratorClient", FakeAgentOrchestratorClient):
                result = service.listAgentOrchestratorModels(
                    {
                        "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                    }
                )

            self.assertTrue(result["ok"])
            self.assertEqual(len(result["models"]), 2)
            self.assertEqual(result["models"][0]["id"], "openai/gpt-5")

    def test_list_agent_orchestrator_models_includes_project_provider_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            write_backend_settings(repo_root)
            opencode_root = repo_root / ".opencode"
            opencode_root.mkdir(parents=True)
            (opencode_root / "opencode.json").write_text(
                json.dumps(
                    {
                        "provider": {
                            "my_local_lmstudio": {
                                "models": {
                                    "gemma-4-e4b-uncensored-hauhaucs-aggressive": {
                                        "name": "gemma-4-e4b-uncensored-hauhaucs-aggressive"
                                    }
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            service = GuiBridgeService(repo_root)

            class FakeAgentOrchestratorClient:
                def __init__(self, config):
                    self.config = config

                def list_models(self):
                    return [{"id": "openai/gpt-5", "provider": "openai", "model": "gpt-5"}]

            with patch("ai_3d_modeling_agent.gui.bridge.AgentOrchestratorClient", FakeAgentOrchestratorClient):
                result = service.listAgentOrchestratorModels(
                    {
                        "agent_orchestrator_base_url": "http://127.0.0.1:4111",
                    }
                )

            self.assertTrue(result["ok"])
            self.assertEqual(
                [model["id"] for model in result["models"]],
                [
                    "openai/gpt-5",
                    "my_local_lmstudio/gemma-4-e4b-uncensored-hauhaucs-aggressive",
                ],
            )

    def test_read_mcp_tool_calls_reads_latest_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            log_path = session_mcp_log_path(runtime_root, "gui-001")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "\n".join(
                    [
                        json.dumps({"tool_name": "get_context", "timestamp": "2026-05-14T10:00:00Z"}),
                        json.dumps({"tool_name": "capture_view", "timestamp": "2026-05-14T10:00:01Z"}),
                    ]
                ),
                encoding="utf-8",
            )
            service = GuiBridgeService(repo_root)

            result = service.read_mcp_tool_calls("gui-001")

            self.assertTrue(result["exists"])
            self.assertEqual(len(result["tool_calls"]), 2)

    def test_read_console_log_reads_runtime_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            log_path = service.console_log_path("gui-001")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text("line 1\nline 2\n", encoding="utf-8")

            result = service.read_console_log("gui-001")

            self.assertTrue(result["exists"])
            self.assertIn("line 1", result["content"])
            self.assertIn("line 2", result["content"])

    def test_failed_run_persists_pending_retry_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            class FakeProcess:
                pid = 2468

                def poll(self):
                    return 1

            service.last_run_payloads["gui-001"] = {"session_id": "gui-001", "task": "chair"}
            service.processes["gui-001"] = FakeProcess()
            service.run_statuses["gui-001"] = {
                "session_id": "gui-001",
                "workflow_status": "running",
                "process_status": "running",
                "error_message": "Part review became stuck.",
                "last_command": ["python", "scripts/run_pipeline.py"],
                "pid": 2468,
                "exit_code": None,
                "attempt_index": 2,
            }

            status = service.get_run_status("gui-001")

            self.assertEqual(status["workflow_status"], "failed")
            interaction = json.loads(
                session_pending_interaction_path(repo_root / "data" / "runtime", "gui-001").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(interaction["kind"], "retry_decision")
            self.assertEqual(interaction["attempt_index"], 2)
            self.assertEqual(interaction["next_attempt_index"], 3)
            self.assertEqual(interaction["failure_category"], "execution_failure")

    def test_bootstrap_returns_retry_prompt_from_pending_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]
            ensure_session_runtime_dir(runtime_root, session_id)
            session_pending_interaction_path(runtime_root, session_id).write_text(
                json.dumps(
                      {
                          "interaction_id": "retry-1",
                          "session_id": session_id,
                          "kind": "retry_decision",
                          "status": "pending",
                          "failure_reason": "Process exited with code 1.",
                          "failure_category": "validation_failure",
                          "planning_summary": "Final model comparison still mismatches the expected chair.",
                          "blocking_constraint_refs": ["plan.ordering_constraints.seat-before-leg"],
                          "attempt_index": 1,
                          "next_attempt_index": 2,
                      }
                ),
                encoding="utf-8",
            )
            service.last_run_payloads[session_id] = {"session_id": session_id, "task": "chair"}
            service.run_statuses[session_id] = {
                "session_id": session_id,
                "workflow_status": "failed",
                "process_status": "exited",
                "error_message": "Process exited with code 1.",
                "last_command": [],
                "pid": None,
                "exit_code": 1,
                "attempt_index": 1,
            }

            payload = service.bootstrap(session_id)
            session_state = service.get_session_state(session_id)

            self.assertTrue(session_state["retry_prompt"]["show"])
            self.assertEqual(session_state["retry_prompt"]["attempt_index"], 1)
            self.assertEqual(session_state["retry_prompt"]["next_attempt_index"], 2)
            self.assertEqual(session_state["retry_prompt"]["failure_category"], "validation_failure")
            self.assertIn("comparison still mismatches", session_state["retry_prompt"]["planning_summary"])

    def test_append_activity_persists_and_snapshot_matches_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]
            items = [
                {"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"},
                {"id": "a-2", "kind": "status", "title": "Status", "body": "Second", "timestamp": "10:01"},
            ]

            result = service.append_activity(session_id, {"activity": items})
            history_path = service.activity_history_path(session_id)
            snapshot = service.get_activity_snapshot(session_id)

            self.assertTrue(result["saved"])
            self.assertTrue(history_path.exists())
            lines = history_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual([json.loads(line)["id"] for line in lines], ["a-1", "a-2"])
            self.assertEqual([item["id"] for item in snapshot["activity"]], ["a-1", "a-2"])
            self.assertEqual(result["server_cursor"], snapshot["server_cursor"])

    def test_append_activity_generates_stable_fallback_ids_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]

            result = service.append_activity(
                session_id,
                {
                    "activity": [
                        {"kind": "system", "title": "System", "body": "Fallback id", "timestamp": "10:00"}
                    ]
                },
            )
            snapshot = service.get_activity_snapshot(session_id)

            generated_id = result["activity"][0]["id"]
            self.assertTrue(generated_id.startswith("activity-"))
            self.assertEqual(snapshot["activity"][0]["id"], generated_id)

    def test_read_activity_history_skips_bad_lines_and_preserves_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = "gui-001"
            path = service.activity_history_path(session_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"}),
                        "{not-json",
                        json.dumps({"id": "a-2", "kind": "feedback", "title": "Feedback", "body": "Second", "timestamp": "10:01"}),
                    ]
                ),
                encoding="utf-8",
            )

            history = service._read_activity_history(session_id)

            self.assertEqual([item["id"] for item in history], ["a-1", "a-2"])
            self.assertEqual([item["body"] for item in history], ["First", "Second"])

    def test_session_snapshot_aligns_activity_runtime_and_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]
            progress_path = session_progress_path(runtime_root, session_id)
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            progress_path.write_text(
                json.dumps({"session_id": session_id, "status": "running", "stage": "planning"}),
                encoding="utf-8",
            )
            service.append_activity(
                session_id,
                {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"}]},
            )
            session_console_log_path(runtime_root, session_id).write_text("line 1\nline 2\n", encoding="utf-8")
            session_mcp_log_path(runtime_root, session_id).write_text(
                json.dumps({"tool_name": "capture_view", "timestamp": "2026-05-14T10:00:00Z"}),
                encoding="utf-8",
            )
            service.run_statuses[session_id] = {
                "session_id": session_id,
                "workflow_status": "failed",
                "process_status": "exited",
                "error_message": "Need retry.",
                "last_command": ["python", "scripts/run_pipeline.py"],
                "pid": 1111,
                "exit_code": 1,
                "attempt_index": 2,
            }
            service.last_run_payloads[session_id] = {"session_id": session_id, "task": "chair"}
            service.retry_plans[session_id] = {
                "remaining_retries": 2,
                "decision_state": "awaiting",
            }
            service._write_pending_interaction(
                session_id,
                {
                    "interaction_id": "retry-1",
                    "session_id": session_id,
                    "kind": "retry_decision",
                    "status": "pending",
                    "failure_reason": "Need retry.",
                    "attempt_index": 2,
                    "next_attempt_index": 3,
                },
            )

            snapshot = service.get_activity_snapshot(session_id)
            repeated = service.get_activity_snapshot(session_id)

            self.assertEqual([item["id"] for item in snapshot["activity"]], ["a-1"])
            self.assertEqual(snapshot["progress"]["stage"], "planning")
            self.assertEqual(snapshot["run_status"]["attempt_index"], 2)
            self.assertEqual(snapshot["console_log"], "line 1\nline 2\n")
            self.assertEqual(snapshot["mcp_tool_calls"][0]["tool_name"], "capture_view")
            self.assertTrue(snapshot["retry_prompt"]["show"])
            self.assertEqual(snapshot["retry_prompt"]["next_attempt_index"], 3)
            self.assertEqual(snapshot["server_cursor"], repeated["server_cursor"])

    def test_server_cursor_changes_with_runtime_state_mutations_and_stays_stable_otherwise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = "gui-001"

            cursor_1 = service._compute_server_cursor(session_id)
            cursor_2 = service._compute_server_cursor(session_id)
            self.assertEqual(cursor_1, cursor_2)

            service.append_activity(
                session_id,
                {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "First", "timestamp": "10:00"}]},
            )
            cursor_after_activity = service._compute_server_cursor(session_id)
            self.assertNotEqual(cursor_1, cursor_after_activity)

            service.append_activity(
                session_id,
                {"activity": [{"id": "a-2", "kind": "system", "title": "System", "body": "Second", "timestamp": "10:00"}]},
            )
            cursor_after_second_activity = service._compute_server_cursor(session_id)
            self.assertNotEqual(cursor_after_activity, cursor_after_second_activity)

            time.sleep(1.1)
            session_console_log_path(runtime_root, session_id).parent.mkdir(parents=True, exist_ok=True)
            session_console_log_path(runtime_root, session_id).write_text("console line", encoding="utf-8")
            cursor_after_console = service._compute_server_cursor(session_id)
            self.assertNotEqual(cursor_after_second_activity, cursor_after_console)

            time.sleep(1.1)
            service._write_pending_interaction(
                session_id,
                {
                    "interaction_id": "retry-2",
                    "session_id": session_id,
                    "kind": "retry_decision",
                    "status": "pending",
                },
            )
            cursor_after_pending = service._compute_server_cursor(session_id)
            self.assertNotEqual(cursor_after_console, cursor_after_pending)
            time.sleep(1.1)
            session_plan_artifact_path(runtime_root, session_id).write_text(
                json.dumps({"summary": "Persisted planning truth."}),
                encoding="utf-8",
            )
            cursor_after_plan = service._compute_server_cursor(session_id)
            self.assertNotEqual(cursor_after_pending, cursor_after_plan)
            self.assertEqual(cursor_after_plan, service._compute_server_cursor(session_id))

    def test_make_stream_event_sequence_is_monotonic_per_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)

            event_1 = service._make_stream_event("gui-001", "snapshot_required", {"reason": "initial"})
            event_2 = service._make_stream_event("gui-001", "meeting_event", {"event_id": "meeting-1"})
            event_other = service._make_stream_event("gui-002", "snapshot_required", {"reason": "initial"})
            event_3 = service._make_stream_event("gui-001", "activity_appended", {})

            self.assertEqual(event_1["sequence"], 1)
            self.assertEqual(event_2["sequence"], 2)
            self.assertEqual(event_3["sequence"], 3)
            self.assertEqual(event_other["sequence"], 1)
            self.assertEqual(event_2["event_id"], "meeting-1")
            self.assertEqual(event_1["session_id"], "gui-001")
            self.assertIn("server_cursor", event_3)

    def test_activity_snapshot_recovers_history_after_service_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            first_service = GuiBridgeService(repo_root)
            session_id = first_service.create_session()["session_id"]
            first_service.append_activity(
                session_id,
                {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "Recovered", "timestamp": "10:00"}]},
            )
            first_snapshot = first_service.get_activity_snapshot(session_id)

            second_service = GuiBridgeService(repo_root)
            second_snapshot = second_service.get_activity_snapshot(session_id)

            self.assertEqual([item["id"] for item in second_snapshot["activity"]], ["a-1"])
            self.assertEqual(first_snapshot["activity"], second_snapshot["activity"])
            self.assertEqual(first_snapshot["server_cursor"], second_snapshot["server_cursor"])

    def test_activity_snapshot_does_not_require_backend_settings_when_mcp_is_idle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            service = GuiBridgeService(repo_root)
            session_id = service.create_session()["session_id"]
            service.append_activity(
                session_id,
                {"activity": [{"id": "a-1", "kind": "system", "title": "System", "body": "Safe snapshot", "timestamp": "10:00"}]},
            )

            snapshot = service.get_activity_snapshot(session_id)

            self.assertEqual([item["id"] for item in snapshot["activity"]], ["a-1"])
            self.assertEqual(snapshot["mcp_status"]["state"], "idle")

    def test_meeting_state_round_trip_and_latest_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = "gui-001"
            ensure_session_runtime_dir(runtime_root, session_id)

            design_state = {
                "schema_version": 1,
                "phase_name": "design",
                "goal": "Decompose the object into families.",
                "owner_role": "designer",
                "reviewer_role": "reviewer",
                "current_round": 1,
                "accepted_decisions": [
                    {
                        "id": "decision-design-1",
                        "summary": "Use a single tabletop family.",
                        "source_round": 1,
                        "decision_refs": ["parts.table_top"],
                        "status": "accepted",
                        "category": "structure",
                        "rationale": "Keeps the hierarchy simple.",
                        "evidence": "Initial decomposition.",
                    }
                ],
                "rejected_alternatives": [],
                "open_issues": [],
                "resolved_challenges": [],
                "resolution_history": [
                    {
                        "round": 1,
                        "summary": "Accepted the tabletop family split.",
                        "accepted_ids": ["decision-design-1"],
                        "rejected_ids": [],
                        "remaining_open_issue_ids": [],
                        "change_summary": "Defined the root family.",
                    }
                ],
                "last_resolution_summary": "Accepted the root tabletop family.",
                "phase_status": "resolved",
                "round_change_summary": "Defined the root family.",
                "phase_quality_flags": [],
                "coverage_todos": [
                    {
                        "id": "spec:tabletop:part_exists",
                        "phase": "spec",
                        "source": "design:tabletop",
                        "target_name": "tabletop",
                        "target_kind": "part",
                        "task": "spec_part_exists",
                        "status": "covered",
                        "required": True,
                        "evidence": "part exists",
                        "missing_reason": "",
                    }
                ],
                "coverage_summary": {"total": 1, "counts": {"covered": 1}, "required_missing": [], "complete": True},
                "todo_groups": [
                    {
                        "id": "spec:tabletop",
                        "phase": "spec",
                        "target_name": "tabletop",
                        "target_kind": "part",
                        "role": "specifier",
                        "review_role": "reviewer",
                        "status": "accepted",
                        "todos": [],
                    }
                ],
                "current_todo_group": {"id": "spec:tabletop", "target_name": "tabletop"},
                "updated_at": 100,
            }
            plan_state = {
                "schema_version": 1,
                "phase_name": "plan",
                "goal": "Define build and assembly order.",
                "owner_role": "planner",
                "reviewer_role": "reviewer",
                "current_round": 2,
                "accepted_decisions": [
                    {
                        "id": "decision-plan-1",
                        "summary": "Build the tabletop before the legs.",
                        "source_round": 2,
                        "decision_refs": ["plan.steps.build_top"],
                        "status": "accepted",
                        "category": "execution_order",
                        "rationale": "Leg placement depends on the top.",
                        "evidence": "Planner proposal.",
                    }
                ],
                "rejected_alternatives": [],
                "open_issues": [
                    {
                        "id": "issue-plan-1",
                        "summary": "Leg placement tolerances still need validation.",
                        "owner": "planner",
                        "blocking": False,
                        "issue_type": "validation_risk",
                        "impact": "Could require a later adjustment.",
                        "introduced_by": "reviewer",
                    }
                ],
                "resolved_challenges": [],
                "resolution_history": [
                    {
                        "round": 2,
                        "summary": "Accepted the build order and kept a non-blocking validation note.",
                        "accepted_ids": ["decision-plan-1"],
                        "rejected_ids": [],
                        "remaining_open_issue_ids": ["issue-plan-1"],
                        "change_summary": "Sequenced build before assembly.",
                    }
                ],
                "last_resolution_summary": "Build the tabletop before the legs and validate placement afterwards.",
                "phase_status": "completed_with_open_issues",
                "round_change_summary": "Sequenced build before assembly.",
                "phase_quality_flags": ["needs_followup"],
                "updated_at": 200,
            }
            session_meeting_state_path(runtime_root, session_id, "design").write_text(
                json.dumps(design_state),
                encoding="utf-8",
            )
            session_meeting_state_path(runtime_root, session_id, "plan").write_text(
                json.dumps(plan_state),
                encoding="utf-8",
            )

            loaded_design = service.load_phase_meeting_state(session_id, "design")
            loaded_all = service.load_all_phase_meeting_states(session_id)
            latest = service.select_latest_meeting_state(session_id)
            truth = service.get_meeting_state_truth(session_id)
            session_state = service.get_session_state(session_id)

            self.assertEqual(loaded_design["schema_version"], 1)
            self.assertEqual(loaded_design["accepted_decisions"][0]["id"], "decision-design-1")
            self.assertEqual(loaded_design["coverage_todos"][0]["id"], "spec:tabletop:part_exists")
            self.assertTrue(loaded_design["coverage_summary"]["complete"])
            self.assertEqual(loaded_design["todo_groups"][0]["id"], "spec:tabletop")
            self.assertEqual(loaded_design["current_todo_group"]["target_name"], "tabletop")
            self.assertEqual([item["phase_name"] for item in loaded_all], ["design", "plan"])
            self.assertEqual(latest["phase_name"], "plan")
            self.assertEqual(latest["phase_status"], "completed_with_open_issues")
            self.assertEqual(truth["latest_phase_name"], "plan")
            self.assertEqual(
                truth["latest_resolution_summary"],
                "Build the tabletop before the legs and validate placement afterwards.",
            )
            self.assertEqual(session_state["meeting_state"]["phase_name"], "plan")
            self.assertEqual(len(session_state["meeting_states"]), 2)

    def test_load_all_phase_meeting_states_ignores_bad_files_and_normalizes_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = "gui-001"
            ensure_session_runtime_dir(runtime_root, session_id)
            session_meeting_state_path(runtime_root, session_id, "design").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase_name": "design",
                        "goal": "Design goal",
                        "owner_role": "designer",
                        "reviewer_role": "reviewer",
                        "current_round": 1,
                        "phase_status": "in_progress",
                        "updated_at": 1,
                    }
                ),
                encoding="utf-8",
            )
            session_meeting_state_path(runtime_root, session_id, "spec").write_text(
                "{not-json",
                encoding="utf-8",
            )

            all_states = service.load_all_phase_meeting_states(session_id)
            latest = service.select_latest_meeting_state(session_id)

            self.assertEqual(len(all_states), 1)
            self.assertEqual(all_states[0]["phase_name"], "design")
            self.assertEqual(all_states[0]["accepted_decisions"], [])
            self.assertEqual(all_states[0]["open_issues"], [])
            self.assertEqual(all_states[0]["phase_quality_flags"], [])
            self.assertEqual(all_states[0]["coverage_todos"], [])
            self.assertEqual(all_states[0]["coverage_summary"], {})
            self.assertEqual(all_states[0]["todo_groups"], [])
            self.assertEqual(all_states[0]["current_todo_group"], {})
            self.assertEqual(latest["phase_name"], "design")

    def test_session_state_and_planning_truth_include_persisted_plan_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            runtime_root = repo_root / "data" / "runtime"
            service = GuiBridgeService(repo_root)
            session_id = "gui-001"
            ensure_session_runtime_dir(runtime_root, session_id)
            session_meeting_state_path(runtime_root, session_id, "plan").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "phase_name": "plan",
                        "goal": "Define build and assembly order.",
                        "owner_role": "planner",
                        "reviewer_role": "reviewer",
                        "current_round": 2,
                        "accepted_decisions": [
                            {
                                "id": "plan-accepted-1",
                                "summary": "Build the tabletop before placing the legs.",
                                "source_round": 2,
                                "decision_refs": ["plan.ordering_constraints.top-before-legs"],
                                "status": "accepted",
                                "category": "execution_order",
                                "rationale": "Leg placement depends on the tabletop.",
                                "evidence": "Planner response.",
                            }
                        ],
                        "rejected_alternatives": [],
                        "open_issues": [
                            {
                                "id": "plan-open-1",
                                "summary": "Confirm the leg attachment tolerance.",
                                "owner": "planner",
                                "blocking": False,
                                "issue_type": "validation_risk",
                                "impact": "Could require a later adjustment.",
                                "introduced_by": "reviewer",
                            }
                        ],
                        "resolved_challenges": [],
                        "resolution_history": [],
                        "last_resolution_summary": "Build the tabletop before leg placement and validate the attachment tolerance later.",
                        "phase_status": "completed_with_open_issues",
                        "round_change_summary": "Sequenced build before assembly.",
                        "phase_quality_flags": ["needs_followup"],
                        "updated_at": 300,
                    }
                ),
                encoding="utf-8",
            )
            session_plan_artifact_path(runtime_root, session_id).write_text(
                json.dumps(
                    {
                        "spec_id": "spec-001",
                        "summary": "Build the tabletop before placing the legs.",
                        "execution_rationale": ["The tabletop is the root support surface."],
                        "build_responsibilities": [
                            {
                                "id": "build-tabletop",
                                "family": "table_top",
                                "summary": "Builder creates the tabletop geometry.",
                                "geometry_assumptions": ["Use the agreed primitive and bounding box."],
                                "deferred_placement": ["Assembly handles final placement."],
                                "decision_refs": ["plan.build_responsibilities.table_top"],
                            }
                        ],
                        "assembly_responsibilities": [
                            {
                                "id": "assemble-leg",
                                "family": "table_leg",
                                "summary": "Builder places and parents the legs.",
                                "placement_relations": ["Attach each leg to a tabletop corner."],
                                "hierarchy_notes": ["Keep the tabletop as the root parent."],
                                "decision_refs": ["plan.assembly_responsibilities.table_leg"],
                            }
                        ],
                        "dependency_summary": ["Build the tabletop before final leg placement."],
                        "ordering_constraints": [
                            {
                                "id": "ordering-top-before-legs",
                                "summary": "The tabletop must exist before the legs are finally placed.",
                                "depends_on": ["build:table_top"],
                                "responsibility": "builder",
                                "decision_refs": ["plan.ordering_constraints.top-before-legs"],
                            }
                        ],
                        "risk_hotspots": [
                            {
                                "id": "risk-leg-placement",
                                "summary": "Leg placement depends on the final attachment tolerance.",
                                "owner": "builder",
                                "issue_refs": ["plan-open-1"],
                                "reason": "A bad tolerance would create assembly drift.",
                            }
                        ],
                        "open_issues": ["Confirm the leg attachment tolerance."],
                        "failure_notes": [],
                    }
                ),
                encoding="utf-8",
            )
            session_build_execution_plan_path(runtime_root, session_id).write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "family": "table_top",
                                "step_index": 0,
                                "instance_count": 1,
                                "primitive_type": "cube",
                                "scale": [2.0, 1.0, 0.1],
                                "responsibility_refs": ["plan.build_responsibilities.table_top"],
                                "planning_warnings": [],
                                "deferred_placement": ["Assembly handles final placement."],
                                "used_step_fallback": False,
                            }
                        ],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )
            session_assembly_execution_plan_path(runtime_root, session_id).write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "family": "table_leg",
                                "step_index": 1,
                                "parent_name": "table_top",
                                "world_position": [0.3, 0.3, -0.5],
                                "world_rotation": [0.0, 0.0, 0.0],
                                "responsibility_refs": ["plan.assembly_responsibilities.table_leg"],
                                "constraint_refs": ["plan.ordering_constraints.top-before-legs"],
                                "planning_warnings": [],
                                "placement_relations": ["Attach each leg to a tabletop corner."],
                                "hierarchy_notes": ["Keep the tabletop as the root parent."],
                                "used_step_fallback": False,
                            }
                        ],
                        "diagnostics": [],
                    }
                ),
                encoding="utf-8",
            )

            session_state = service.get_session_state(session_id)
            planning_truth = service.get_planning_truth(session_id)

            self.assertEqual(session_state["plan_artifact"]["summary"], "Build the tabletop before placing the legs.")
            self.assertEqual(session_state["plan_artifact"]["build_responsibilities"][0]["family"], "table_top")
            self.assertEqual(session_state["build_execution_plan"]["items"][0]["family"], "table_top")
            self.assertEqual(session_state["assembly_execution_plan"]["items"][0]["family"], "table_leg")
            self.assertEqual(session_state["failure_triage"]["failure_category"], "")
            self.assertEqual(planning_truth["latest_phase_name"], "plan")
            self.assertEqual(planning_truth["plan_artifact"]["ordering_constraints"][0]["responsibility"], "builder")
            self.assertEqual(planning_truth["build_execution_plan"]["items"][0]["responsibility_refs"][0], "plan.build_responsibilities.table_top")
            self.assertEqual(planning_truth["assembly_execution_plan"]["items"][0]["constraint_refs"][0], "plan.ordering_constraints.top-before-legs")
            self.assertEqual(planning_truth["accepted_decisions"][0]["id"], "plan-accepted-1")
            self.assertEqual(planning_truth["open_issues"][0]["id"], "plan-open-1")
            self.assertIn("Planning risk hotspot remains active", planning_truth["latest_planning_warnings"][0])
