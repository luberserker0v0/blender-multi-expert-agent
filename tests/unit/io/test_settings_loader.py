"""Unit tests for settings_loader."""

import json
import tempfile
from pathlib import Path

import pytest

from ai_3d_modeling_agent.io.settings_loader import DEFAULTS, load_settings, settings_to_run_pipeline_kwargs


class TestLoadSettings:
    def test_load_without_file(self):
        settings = load_settings()
        assert settings == DEFAULTS

    def test_load_from_nested_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "llm": {
                            "endpoint_url": "http://custom:9090",
                            "model": "my-model",
                            "api_key": "secret",
                        },
                        "mcpServers": {
                            "blender": {
                                "command": "uv",
                                "args": ["run", "blender-mcp"],
                                "cwd": "C:\\blender_mcp\\mcp",
                                "env": {"BLENDER_USER_CONFIG": "D:\\blender\\config"},
                            }
                        },
                        "pipeline": {
                            "use_" + "multi_expert": False,
                            "max_part_refinement_rounds": 4,
                            "max_assembly_rounds": 2,
                        },
                        "yolo": {
                            "enabled": True,
                            "model_path": "D:\\models\\detector.pt",
                            "viewpoints": ["front", "side"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(path)

            assert settings["llm_endpoint_url"] == "http://custom:9090"
            assert settings["llm_model"] == "my-model"
            assert settings["llm_api_key"] == "secret"
            assert settings["use_blender_mcp"] is True
            assert settings["blender_mcp_command"] == "uv"
            assert settings["blender_mcp_args"] == ["run", "blender-mcp"]
            assert settings["blender_mcp_cwd"] == "C:\\blender_mcp\\mcp"
            assert settings["blender_mcp_env"] == {"BLENDER_USER_CONFIG": "D:\\blender\\config"}
            assert settings["blender_mcp_server_name"] == "blender"
            assert "use_" + "multi_expert" not in settings
            assert settings["max_part_refinement_rounds"] == 4
            assert settings["max_assembly_rounds"] == 2
            assert settings["use_yolo_perception"] is True
            assert settings["yolo_model_path"] == "D:\\models\\detector.pt"
            assert settings["yolo_viewpoints"] == ["front", "side"]

    def test_nested_mcp_takes_precedence_over_flat_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "blender_mcp_command": "python",
                        "blender_mcp_args": ["-m", "old_server"],
                        "blender_mcp_cwd": "D:\\old",
                        "mcpServers": {
                            "blender": {
                                "command": "uv",
                                "args": ["run", "blender-mcp"],
                                "cwd": "C:\\blender_mcp\\mcp",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(path)

            assert settings["blender_mcp_command"] == "uv"
            assert settings["blender_mcp_args"] == ["run", "blender-mcp"]
            assert settings["blender_mcp_cwd"] == "C:\\blender_mcp\\mcp"

    def test_flat_mcp_fallback_still_supported(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "llm_endpoint_url": "http://file:9090",
                        "llm_model": "file-model",
                        "blender_mcp_command": "python",
                        "blender_mcp_args": ["-m", "blender_mcp_server"],
                        "blender_mcp_cwd": "D:\\legacy\\mcp",
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(path)

            assert settings["llm_endpoint_url"] == "http://file:9090"
            assert settings["llm_model"] == "file-model"
            assert settings["blender_mcp_command"] == "python"
            assert settings["blender_mcp_args"] == ["-m", "blender_mcp_server"]
            assert settings["blender_mcp_cwd"] == "D:\\legacy\\mcp"

    def test_overrides_win_over_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "llm": {"endpoint_url": "http://file:9090", "model": "file-model"},
                    }
                ),
                encoding="utf-8",
            )

            settings = load_settings(path, overrides={"llm_model": "override-model"})

            assert settings["llm_endpoint_url"] == "http://file:9090"
            assert settings["llm_model"] == "override-model"

    def test_none_overrides_ignored(self):
        settings = load_settings(overrides={"llm_model": None})
        assert settings["llm_model"] == DEFAULTS["llm_model"]

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_settings("/nonexistent/settings.json")

    def test_invalid_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bad.json"
            path.write_text("not json", encoding="utf-8")

            with pytest.raises(ValueError):
                load_settings(path)

    def test_non_dict_json_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "array.json"
            path.write_text("[1, 2, 3]", encoding="utf-8")

            with pytest.raises(ValueError):
                load_settings(path)

    def test_nested_mcp_requires_command(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "blender": {
                                "args": ["run", "blender-mcp"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with pytest.raises(ValueError, match="mcpServers.blender.command"):
                load_settings(path)

    def test_nested_mcp_requires_args_list(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "mcpServers": {
                            "blender": {
                                "command": "uv",
                                "args": "--directory C:\\blender_mcp\\mcp",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with pytest.raises(ValueError, match="mcpServers.blender.args must be a list"):
                load_settings(path)


class TestSettingsToRunPipelineKwargs:
    def test_valid_keys_passed(self):
        settings = {
            "task": "build a chair",
            "session_id": "test-001",
            "llm_endpoint_url": "http://localhost:8080",
            "llm_model": "gpt-4",
            "agent_orchestrator_base_url": "http://localhost:4111",
            "agent_orchestrator_model": "ao-model",
            "use_blender_mcp": True,
            "blender_mcp_env": {"FOO": "bar"},
            "unknown_key": "ignored",
        }
        kwargs = settings_to_run_pipeline_kwargs(settings)

        assert kwargs["task"] == "build a chair"
        assert kwargs["session_id"] == "test-001"
        assert "llm_endpoint_url" not in kwargs
        assert "llm_model" not in kwargs
        assert kwargs["agent_orchestrator_base_url"] == "http://localhost:4111"
        assert kwargs["agent_orchestrator_model"] == "ao-model"
        assert kwargs["use_blender_mcp"] is True
        assert kwargs["blender_mcp_env"] == {"FOO": "bar"}
        assert "unknown_key" not in kwargs

    def test_empty_settings(self):
        kwargs = settings_to_run_pipeline_kwargs({})
        assert kwargs == {}
