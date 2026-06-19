import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.analysis.gap_report_builder import GapReportBuilder
from ai_3d_modeling_agent.blender.context_reader import SimulatedBlenderContextReader
from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
from ai_3d_modeling_agent.decision.llm_engine import EndpointLlmDecisionEngine
from ai_3d_modeling_agent.perception.base import PerceptionMetric, PerceptionResult
from ai_3d_modeling_agent.perception.yolo_provider import YoloPerceptionProvider, YoloProviderConfig
from ai_3d_modeling_agent.services.llm_endpoint import (
    OpenAiCompatibleEndpointClient,
    OpenAiCompatibleEndpointConfig,
)
from ai_3d_modeling_agent.services.model_runtime import LocalModelLoader
from ai_3d_modeling_agent.tasks.task_loader import load_checklist


class FakeLocalModelBackend:
    def __init__(self) -> None:
        self.loaded_configs = []

    def load(self, config):
        self.loaded_configs.append(config)
        return {"runtime": config.runtime, "path": str(config.model_path)}


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestEndpointLlmAndModelReuse(unittest.TestCase):
    def test_yolo_provider_uses_shared_local_model_loader(self) -> None:
        backend = FakeLocalModelBackend()
        loader = LocalModelLoader(backend)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "detector.onnx"
            model_path.write_text("stub", encoding="utf-8")

            provider = YoloPerceptionProvider(
                YoloProviderConfig(model_path=model_path, confidence_threshold=0.4),
                loader=loader,
            )
            provider.load_model()

            self.assertEqual(backend.loaded_configs[0].runtime, "yolo")
            self.assertEqual(provider.model["path"], str(model_path))

    def test_endpoint_client_extracts_chat_message(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(base_url="http://127.0.0.1:8080", model="demo")
        )
        payload = {"choices": [{"message": {"content": '{"action_type":"finish","parameters":{},"reason":"done"}'}}]}

        with patch("urllib.request.urlopen", return_value=FakeHttpResponse(payload)):
            text = client.create_chat_completion("system", "user")

        self.assertIn('"action_type":"finish"', text)

    def test_endpoint_client_retries_until_server_is_available(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(
                base_url="http://127.0.0.1:8080",
                model="demo",
                reconnect_attempts=3,
                reconnect_backoff_seconds=0.0,
            )
        )
        payload = {"choices": [{"message": {"content": '{"action_type":"finish","parameters":{},"reason":"done"}'}}]}
        responses = [
            URLError("connection refused"),
            URLError("connection refused"),
            FakeHttpResponse(payload),
        ]

        def fake_urlopen(*args, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            text = client.create_chat_completion("system", "user")

        self.assertIn('"action_type":"finish"', text)

    def test_endpoint_client_sends_multimodal_chat_completion(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(base_url="http://127.0.0.1:8080", model="demo")
        )
        payload = {"choices": [{"message": {"content": '{"approved":true,"summary":"ok","action":null}'}}]}

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "capture.png"
            image_path.write_bytes(b"fake-image")
            captured_request = {}

            def fake_urlopen(req, timeout=None):
                captured_request["data"] = json.loads(req.data.decode("utf-8"))
                return FakeHttpResponse(payload)

            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                text = client.create_multimodal_chat_completion(
                    "system",
                    "review this image",
                    image_inputs=[
                        {"path": str(image_path), "label": "front review", "viewpoint": "front"},
                    ],
                )

        self.assertIn('"approved":true', text)
        user_content = captured_request["data"]["messages"][1]["content"]
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[2]["type"], "image_url")
        self.assertTrue(user_content[2]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_endpoint_client_uses_multimodal_timeout(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(
                base_url="http://127.0.0.1:8080",
                model="demo",
                timeout_seconds=60.0,
                multimodal_timeout_seconds=180.0,
            )
        )
        payload = {"choices": [{"message": {"content": '{"approved":true,"summary":"ok","action":null}'}}]}

        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = Path(tmp_dir) / "capture.png"
            image_path.write_bytes(b"fake-image")
            seen_timeout = {}

            def fake_urlopen(req, timeout=None):
                seen_timeout["value"] = timeout
                return FakeHttpResponse(payload)

            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                client.create_multimodal_chat_completion(
                    "system",
                    "review this image",
                    image_inputs=[{"path": str(image_path), "label": "front", "viewpoint": "front"}],
                )

        self.assertEqual(seen_timeout["value"], 180.0)

    def test_endpoint_client_retries_after_timeout_error(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(
                base_url="http://127.0.0.1:8080",
                model="demo",
                reconnect_attempts=2,
                reconnect_backoff_seconds=0.0,
            )
        )
        payload = {"choices": [{"message": {"content": '{"action_type":"finish","parameters":{},"reason":"done"}'}}]}
        responses = [
            TimeoutError("timed out"),
            FakeHttpResponse(payload),
        ]

        def fake_urlopen(*args, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            text = client.create_chat_completion("system", "user")

        self.assertIn('"action_type":"finish"', text)

    def test_endpoint_client_raises_after_reconnect_exhausted(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(
                base_url="http://127.0.0.1:8080",
                model="demo",
                reconnect_attempts=2,
                reconnect_backoff_seconds=0.0,
            )
        )

        with patch("urllib.request.urlopen", side_effect=URLError("connection refused")):
            with self.assertRaises(RuntimeError):
                client.wait_until_available()

    def test_endpoint_llm_decision_engine_returns_action(self) -> None:
        checklist = load_checklist(
            REPO_ROOT / "data" / "static" / "checklists" / "apple_checklist.json"
        )
        object_ops = SimulatedBlenderObjectOps()
        object_ops.create_uv_sphere("apple_body")
        object_ops.scale_uniform(0.5)
        context = SimulatedBlenderContextReader(object_ops).read()
        perception = PerceptionResult(
            detected_parts=["apple_body"],
            missing_critical_parts=[],
            quantitative_metrics=[
                PerceptionMetric(
                    part_name="apple_body",
                    current_bounding_box_ratio=[0.5, 0.5, 0.5],
                )
            ],
        )
        gap_report = GapReportBuilder().build(
            checklist=checklist,
            blender_context=context,
            perception_result=perception,
            previous_action_failed=False,
            last_successful_macro_id="",
        )
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(base_url="http://127.0.0.1:8080", model="demo")
        )
        payload = {
            "choices": [
                {
                    "message": {
                        "content": '{"action_type":"scale_uniform","parameters":{"factor":1.5},"reason":"under sized"}'
                    }
                }
            ]
        }

        with patch("urllib.request.urlopen", return_value=FakeHttpResponse(payload)):
            action = EndpointLlmDecisionEngine(client).decide(gap_report)

        self.assertEqual(action.action_type, "scale_uniform")
        self.assertEqual(action.parameters["factor"], 1.5)

    def test_endpoint_llm_decision_engine_rejects_invalid_json(self) -> None:
        client = OpenAiCompatibleEndpointClient(
            OpenAiCompatibleEndpointConfig(base_url="http://127.0.0.1:8080", model="demo")
        )
        checklist = load_checklist(
            REPO_ROOT / "data" / "static" / "checklists" / "apple_checklist.json"
        )
        context = SimulatedBlenderContextReader(SimulatedBlenderObjectOps()).read()
        gap_report = GapReportBuilder().build(
            checklist=checklist,
            blender_context=context,
            perception_result=PerceptionResult([], ["apple_body"], []),
            previous_action_failed=False,
            last_successful_macro_id="",
        )
        payload = {"choices": [{"message": {"content": "not json"}}]}

        with patch("urllib.request.urlopen", return_value=FakeHttpResponse(payload)):
            with self.assertRaises(ValueError):
                EndpointLlmDecisionEngine(client).decide(gap_report)
