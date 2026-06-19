import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.gui.prototype import (
    build_round_inspector_sections,
    GuiLaunchConfig,
    GuiSavedSettings,
    build_multi_stage_command,
    extract_assembly_round_rows,
    extract_part_round_rows,
    extract_part_task_rows,
    find_assembly_round_detail,
    find_part_round_detail,
    format_history_detail,
    format_round_detail,
    generate_session_id,
    gui_settings_path,
    load_gui_settings,
    save_gui_settings,
    session_progress_path,
    summarize_progress,
)


class TestGuiPrototypeHelpers(unittest.TestCase):
    def test_build_multi_stage_command_targets_multi_expert_cli(self) -> None:
        config = GuiLaunchConfig(
            task="build a chair",
            session_id="gui/session:1",
            agent_orchestrator_base_url="http://127.0.0.1:4111",
            agent_orchestrator_model="qwen-local",
            reference_texts=["simple chair", "wood"],
            reference_images=["D:\\refs\\chair.png"],
            max_part_refinement_rounds=4,
            max_assembly_rounds=2,
            use_blender_mcp=True,
            use_yolo_perception=True,
            yolo_model_path="D:\\models\\detector.pt",
            yolo_viewpoints=["front", "side"],
            blender_mcp_command="uv",
            blender_mcp_cwd="C:\\blender_mcp\\mcp",
            blender_mcp_args=["--directory", "C:\\blender_mcp\\mcp", "run", "blender-mcp"],
        )

        command = build_multi_stage_command(REPO_ROOT, config)

        self.assertIn(str(REPO_ROOT / "scripts" / "run_pipeline.py"), command)
        self.assertNotIn("--workflow", command)
        self.assertNotIn("--reference-text", command)
        self.assertNotIn("--reference-image", command)
        self.assertIn("--agent-orchestrator-url", command)
        self.assertIn("http://127.0.0.1:4111", command)
        self.assertIn("--agent-orchestrator-model", command)
        self.assertIn("--use-blender-mcp", command)
        self.assertIn("--use-yolo-perception", command)
        self.assertIn("D:\\models\\detector.pt", command)
        self.assertIn("--blender-mcp-arg=--directory", command)

    def test_session_progress_path_sanitizes_session_id(self) -> None:
        path = session_progress_path(REPO_ROOT / "data" / "runtime", "gui/session:1")

        # progress.json in a session_data/<sanitized-id>/ directory
        self.assertEqual(path.name, "progress.json")
        self.assertEqual(path.parent.name, "gui_session_1")

    def test_generate_session_id_uses_prefix_and_safe_format(self) -> None:
        session_id = generate_session_id("gui")

        self.assertTrue(session_id.startswith("gui-"))
        self.assertNotIn("/", session_id)
        self.assertNotIn(":", session_id)

    def test_gui_settings_can_be_saved_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runtime_root = Path(tmp_dir)
            settings = GuiSavedSettings(
                agent_orchestrator_base_url="http://127.0.0.1:4111",
                agent_orchestrator_model="saved-model",
                max_part_refinement_rounds=4,
                max_assembly_rounds=2,
                use_yolo_perception=True,
                yolo_model_path="D:\\models\\saved.pt",
                yolo_viewpoints=["front", "side"],
            )

            path = save_gui_settings(runtime_root, settings)
            loaded = load_gui_settings(runtime_root)

            self.assertEqual(path, gui_settings_path(runtime_root))
            self.assertEqual(loaded.agent_orchestrator_base_url, "http://127.0.0.1:4111")
            self.assertEqual(loaded.agent_orchestrator_model, "saved-model")
            self.assertEqual(loaded.max_part_refinement_rounds, 4)
            self.assertEqual(loaded.max_assembly_rounds, 2)
            self.assertTrue(loaded.use_yolo_perception)
            self.assertEqual(loaded.yolo_model_path, "D:\\models\\saved.pt")
            self.assertEqual(loaded.yolo_viewpoints, ["front", "side"])

    def test_summarize_progress_prefers_active_task_round(self) -> None:
        summary = summarize_progress(
            {
                "status": "running",
                "stage": "part_refinement",
                "stage_status": "running",
                "active_task_id": "chair_back",
                "completed_task_ids": ["chair_leg"],
                "part_tasks": [
                    {
                        "task_id": "chair_back",
                        "rounds": [
                            {
                                "feedback_summary": "Backrest is too short.",
                                "capture_path": "D:\\captures\\back.png",
                            }
                        ],
                    }
                ],
                "final_validation": {
                    "capture_path": "D:\\captures\\final.png",
                    "detected_parts": ["chair_back", "chair_seat"],
                },
            }
        )

        self.assertEqual(summary["active_task_id"], "chair_back")
        self.assertEqual(summary["completed_task_ids"], "chair_leg")
        self.assertEqual(summary["latest_feedback"], "Backrest is too short.")
        self.assertEqual(summary["latest_capture_path"], "D:\\captures\\back.png")
        self.assertEqual(summary["final_detected_parts"], "chair_back, chair_seat")

    def test_extract_part_task_rows_returns_task_history(self) -> None:
        rows = extract_part_task_rows(
            {
                "part_tasks": [
                    {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "status": "approved",
                        "current_round": 2,
                        "approved": True,
                    }
                ]
            }
        )

        self.assertEqual(
            rows,
            [
                {
                    "task_id": "chair_back",
                    "title": "Chair Back",
                    "status": "approved",
                    "current_round": "2",
                    "approved": "yes",
                }
            ],
        )

    def test_extract_part_round_rows_returns_selected_task_rounds(self) -> None:
        rows = extract_part_round_rows(
            {
                "part_tasks": [
                    {
                        "task_id": "chair_back",
                        "rounds": [
                            {
                                "round_index": 1,
                                "approved": False,
                                "viewpoint": "front",
                                "capture_path": "D:\\captures\\back_1.png",
                                "feedback_summary": "Too short",
                                "requested_action": {"action_type": "scale_axis_z"},
                            }
                        ],
                    }
                ]
            },
            "chair_back",
        )

        self.assertEqual(rows[0]["round_index"], "1")
        self.assertEqual(rows[0]["action_type"], "scale_axis_z")
        self.assertEqual(rows[0]["feedback_summary"], "Too short")

    def test_extract_assembly_round_rows_returns_history(self) -> None:
        rows = extract_assembly_round_rows(
            {
                "assembly": {
                    "rounds": [
                        {
                            "round_index": 1,
                            "approved": False,
                            "capture_path": "D:\\captures\\assembly_1.png",
                            "feedback_summary": "Seat needs adjustment",
                            "requested_actions": [{"action_type": "move_object"}],
                        }
                    ]
                }
            }
        )

        self.assertEqual(rows[0]["round_index"], "1")
        self.assertEqual(rows[0]["action_count"], "1")
        self.assertEqual(rows[0]["first_action_type"], "move_object")

    def test_format_history_detail_formats_readable_text(self) -> None:
        text = format_history_detail("Part Round", {"round_index": "1", "approved": "no"}, ["extra: note"])

        self.assertIn("Part Round", text)
        self.assertIn("round_index: 1", text)
        self.assertIn("extra: note", text)

    def test_find_part_round_detail_returns_raw_round_detail(self) -> None:
        detail = find_part_round_detail(
            {
                "part_tasks": [
                    {
                        "task_id": "chair_back",
                        "rounds": [
                            {
                                "round_index": 2,
                                "context": {"active_object_name": "chair_back"},
                                "requested_action": {"action_type": "scale_axis_z"},
                            }
                        ],
                    }
                ]
            },
            "chair_back",
            "2",
        )

        self.assertEqual(detail["context"]["active_object_name"], "chair_back")
        self.assertEqual(detail["requested_action"]["action_type"], "scale_axis_z")

    def test_find_assembly_round_detail_returns_raw_round_detail(self) -> None:
        detail = find_assembly_round_detail(
            {
                "assembly": {
                    "rounds": [
                        {
                            "round_index": 1,
                            "requested_actions": [{"action_type": "move_object"}],
                        }
                    ]
                }
            },
            "1",
        )

        self.assertEqual(detail["requested_actions"][0]["action_type"], "move_object")

    def test_format_round_detail_includes_action_parameters_and_context(self) -> None:
        text = format_round_detail(
            "Part Round",
            {
                "round_index": 1,
                "approved": False,
                "capture_path": "D:\\captures\\part.png",
                "viewpoint": "front",
                "feedback_summary": "Too short",
                "context": {
                    "current_mode": "OBJECT",
                    "active_object_name": "chair_back",
                    "active_element_mode": "NONE",
                },
                "requested_action": {
                    "action_type": "scale_axis_z",
                    "execution_status": "executed",
                    "reason": "Stretch upward",
                    "parameters": {"factor": 1.5},
                },
            },
        )

        self.assertIn("current_mode: OBJECT", text)
        self.assertIn("active_object_name: chair_back", text)
        self.assertIn("action_type: scale_axis_z", text)
        self.assertIn("factor: 1.5", text)

    def test_build_round_inspector_sections_groups_summary_context_and_parameters(self) -> None:
        sections = build_round_inspector_sections(
            "Part Round",
            {
                "round_index": 1,
                "approved": False,
                "capture_path": "D:\\captures\\part.png",
                "viewpoint": "front",
                "feedback_summary": "Too short",
                "context": {
                    "current_mode": "OBJECT",
                    "active_object_name": "chair_back",
                    "active_element_mode": "NONE",
                },
                "requested_action": {
                    "action_type": "scale_axis_z",
                    "execution_status": "executed",
                    "reason": "Stretch upward",
                    "parameters": {"factor": 1.5},
                },
            },
        )

        self.assertEqual(sections[0]["title"], "Part Round")
        self.assertEqual(sections[1]["title"], "Context")
        self.assertEqual(sections[2]["title"], "Requested Action")
        self.assertEqual(sections[3]["title"], "Requested Action Parameters")
        self.assertEqual(sections[3]["items"][0]["label"], "factor")
        self.assertEqual(sections[3]["items"][0]["value"], 1.5)

    def test_format_round_detail_supports_multi_action_assembly_rounds(self) -> None:
        text = format_round_detail(
            "Assembly Round",
            {
                "round_index": 1,
                "approved": False,
                "capture_path": "D:\\captures\\assembly.png",
                "feedback_summary": "Adjust seat",
                "context": {"current_mode": "OBJECT"},
                "requested_actions": [
                    {
                        "action_type": "move_object",
                        "execution_status": "executed",
                        "reason": "Move seat",
                        "parameters": {"name": "chair_seat", "location": [0.0, 0.2, 0.4]},
                    }
                ],
            },
            multi_action=True,
        )

        self.assertIn("Requested Action 1", text)
        self.assertIn("action_type: move_object", text)
        self.assertIn("location: [0.0, 0.2, 0.4]", text)


if __name__ == "__main__":
    unittest.main()
