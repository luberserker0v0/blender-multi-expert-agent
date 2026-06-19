import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.perception.yolo_provider import (
    BlenderCaptureYoloPerceptionProvider,
    YoloPerceptionProvider,
    YoloProviderConfig,
)
from ai_3d_modeling_agent.services.model_runtime import LocalModelLoader


class FakeLocalModelBackend:
    def __init__(self, model):
        self.model = model
        self.loaded_configs = []

    def load(self, config):
        self.loaded_configs.append(config)
        return self.model


class FakeScalar:
    def __init__(self, value):
        self.value = value

    def item(self):
        return self.value


class FakeArray:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return list(self.values)


class FakeBox:
    def __init__(self, cls_id, conf, xyxy):
        self.cls = FakeScalar(cls_id)
        self.conf = FakeScalar(conf)
        self.xyxy = [FakeArray(xyxy)]


class FakeResult:
    def __init__(self, names, boxes, image_shape):
        self.names = names
        self.boxes = boxes
        self.orig_shape = image_shape


class FakeYoloModel:
    def __init__(self):
        self.calls = []

    def predict(self, source, conf, verbose):
        self.calls.append((source, conf, verbose))
        return [
            FakeResult(
                names={0: "apple_body"},
                boxes=[FakeBox(0, 0.91, [10.0, 20.0, 110.0, 220.0])],
                image_shape=(400, 200),
            )
        ]


class FakeMultiViewYoloModel:
    def __init__(self):
        self.calls = []

    def predict(self, source, conf, verbose):
        self.calls.append((source, conf, verbose))
        source_str = str(source)
        if "front" in source_str:
            return [
                FakeResult(
                    names={0: "apple_body"},
                    boxes=[FakeBox(0, 0.95, [10.0, 20.0, 130.0, 260.0])],
                    image_shape=(400, 200),
                )
            ]
        if "side" in source_str:
            return [
                FakeResult(
                    names={0: "apple_tail"},
                    boxes=[FakeBox(0, 0.87, [50.0, 100.0, 110.0, 180.0])],
                    image_shape=(400, 200),
                )
            ]
        return []


class FakeCaptureObjectOps:
    def __init__(self, capture_dir: Path) -> None:
        self.capture_dir = capture_dir
        self.calls = []

    def capture_view(self, capture_name: str, area_ui_type: str = "VIEW_3D", viewpoint: str = "front") -> str:
        self.calls.append((capture_name, area_ui_type, viewpoint))
        path = self.capture_dir / capture_name
        path.write_bytes(b"fake-image")
        return str(path)


class TestYoloProvider(unittest.TestCase):
    def test_yolo_provider_loads_model_through_shared_loader(self) -> None:
        fake_model = FakeYoloModel()
        backend = FakeLocalModelBackend(fake_model)
        loader = LocalModelLoader(backend)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "detector.pt"
            model_path.write_text("stub", encoding="utf-8")

            provider = YoloPerceptionProvider(
                YoloProviderConfig(model_path=model_path),
                image_source=lambda: Path(tmp_dir) / "capture.png",
                loader=loader,
            )
            provider.load_model()

            self.assertIs(provider.model, fake_model)
            self.assertEqual(backend.loaded_configs[0].runtime, "yolo")

    def test_yolo_provider_observe_parses_detection_result(self) -> None:
        fake_model = FakeYoloModel()
        backend = FakeLocalModelBackend(fake_model)
        loader = LocalModelLoader(backend)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "detector.pt"
            image_path = Path(tmp_dir) / "capture.png"
            model_path.write_text("stub", encoding="utf-8")
            image_path.write_bytes(b"fake-image")

            provider = YoloPerceptionProvider(
                YoloProviderConfig(
                    model_path=model_path,
                    class_name_map={"apple_body": "apple_body"},
                    primary_target_part="apple_body",
                    emit_bbox_metrics=True,
                ),
                image_source=lambda: image_path,
                loader=loader,
            )
            provider.load_model()

            result = provider.observe()

            self.assertEqual(result.detected_parts, ["apple_body"])
            self.assertEqual(result.missing_critical_parts, [])
            self.assertEqual(result.quantitative_metrics[0].part_name, "apple_body")
            self.assertEqual(result.quantitative_metrics[0].confidence, 0.91)
            self.assertEqual(result.quantitative_metrics[0].current_bounding_box_ratio, [0.5, 0.5, 0.5])
            self.assertEqual(result.detections[0].part_name, "apple_body")
            self.assertEqual(result.detections[0].confidence, 0.91)
            self.assertEqual(result.detections[0].bbox_xyxy, [10.0, 20.0, 110.0, 220.0])
            self.assertEqual(result.detections[0].bbox_center_ratio, [0.3, 0.3])
            self.assertEqual(result.detections[0].viewpoint, "front")
            self.assertEqual(fake_model.calls[0][0], str(image_path))
            self.assertEqual(fake_model.calls[0][1], 0.25)
            self.assertFalse(fake_model.calls[0][2])

    def test_yolo_provider_marks_target_missing_when_no_boxes(self) -> None:
        class EmptyModel(FakeYoloModel):
            def predict(self, source, conf, verbose):
                return [FakeResult(names={0: "apple_body"}, boxes=[], image_shape=(400, 200))]

        backend = FakeLocalModelBackend(EmptyModel())
        loader = LocalModelLoader(backend)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "detector.pt"
            image_path = Path(tmp_dir) / "capture.png"
            model_path.write_text("stub", encoding="utf-8")
            image_path.write_bytes(b"fake-image")

            provider = YoloPerceptionProvider(
                YoloProviderConfig(model_path=model_path, primary_target_part="apple_body"),
                image_source=lambda: image_path,
                loader=loader,
            )
            provider.load_model()

            result = provider.observe()

            self.assertEqual(result.detected_parts, [])
            self.assertEqual(result.missing_critical_parts, ["apple_body"])

    def test_blender_capture_provider_aggregates_multiple_viewpoints(self) -> None:
        fake_model = FakeMultiViewYoloModel()
        backend = FakeLocalModelBackend(fake_model)
        loader = LocalModelLoader(backend)

        with tempfile.TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "detector.pt"
            capture_dir = Path(tmp_dir) / "captures"
            capture_dir.mkdir(parents=True, exist_ok=True)
            model_path.write_text("stub", encoding="utf-8")

            provider = BlenderCaptureYoloPerceptionProvider(
                YoloProviderConfig(
                    model_path=model_path,
                    class_name_map={"apple_body": "apple_body", "apple_tail": "apple_tail"},
                    primary_target_part="apple_body",
                    emit_bbox_metrics=True,
                    viewpoints=["front", "side"],
                    capture_name_prefix="multi",
                ),
                object_ops=FakeCaptureObjectOps(capture_dir),
                loader=loader,
            )
            provider.load_model()

            observed_by_viewpoint = provider.observe_views()
            result = provider.observe()

            self.assertEqual(sorted(observed_by_viewpoint.keys()), ["front", "side"])
            self.assertEqual(observed_by_viewpoint["front"].detected_parts, ["apple_body"])
            self.assertEqual(observed_by_viewpoint["side"].detected_parts, ["apple_tail"])
            self.assertEqual(result.detected_parts, ["apple_body", "apple_tail"])
            self.assertEqual(result.missing_critical_parts, [])
            self.assertEqual(len(result.detections), 2)
            self.assertEqual(result.detections[0].viewpoint, "front")
            self.assertEqual(result.detections[1].viewpoint, "side")
            self.assertEqual(result.quantitative_metrics[0].part_name, "apple_body")
            self.assertEqual(result.quantitative_metrics[0].current_bounding_box_ratio, [0.6, 0.6, 0.6])


if __name__ == "__main__":
    unittest.main()
