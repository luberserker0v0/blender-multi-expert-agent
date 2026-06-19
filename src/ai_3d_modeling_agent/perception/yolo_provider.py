"""YOLO perception provider integration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.perception.base import (
    PerceptionDetection,
    PerceptionMetric,
    PerceptionProvider,
    PerceptionResult,
)
from ai_3d_modeling_agent.services.model_runtime import LocalModelConfig, LocalModelLoader


@dataclass
class YoloProviderConfig:
    model_path: Path
    confidence_threshold: float = 0.25
    class_name_map: Dict[str, str] = field(default_factory=dict)
    primary_target_part: str = "apple_body"
    emit_bbox_metrics: bool = False
    task: Optional[str] = None
    viewpoints: List[str] = field(default_factory=lambda: ["front"])
    capture_name_prefix: str = "yolo_capture"

    def to_local_model_config(self) -> LocalModelConfig:
        return LocalModelConfig(
            model_path=self.model_path,
            runtime="yolo",
            allowed_suffixes=(".pt", ".onnx", ".engine"),
            extra_options={
                "confidence_threshold": self.confidence_threshold,
                "task": self.task,
            },
        )


class YoloPerceptionProvider(PerceptionProvider):
    def __init__(
        self,
        config: YoloProviderConfig,
        image_source: Optional[Callable[[], Union[str, Path]]] = None,
        loader: LocalModelLoader = None,
    ) -> None:
        self.config = config
        self.image_source = image_source
        self.loader = loader
        self.model = None

    def load_model(self) -> None:
        if self.loader is None:
            raise NotImplementedError("Inject a LocalModelLoader to load a YOLO backend.")
        self.model = self.loader.load(self.config.to_local_model_config())

    def observe(self) -> PerceptionResult:
        if self.model is None:
            raise RuntimeError("YOLO model is not loaded. Call load_model() first.")
        if self.image_source is None:
            raise RuntimeError("YOLO image source is not configured.")

        image_path = Path(str(self.image_source()))
        return self.observe_image(image_path, viewpoint="front")

    def observe_image(self, image_path: Union[str, Path], viewpoint: str = "front") -> PerceptionResult:
        return self._observe_image(Path(str(image_path)), viewpoint=viewpoint)

    def _observe_image(self, image_path: Path, viewpoint: str) -> PerceptionResult:
        results = self.model.predict(
            source=str(image_path),
            conf=self.config.confidence_threshold,
            verbose=False,
        )
        if not results:
            return PerceptionResult(
                detected_parts=[],
                missing_critical_parts=[self.config.primary_target_part],
                quantitative_metrics=[],
            )

        result = results[0]
        boxes = list(getattr(result, "boxes", []) or [])
        names = getattr(result, "names", {}) or {}
        detected_parts: List[str] = []
        target_boxes: List[List[float]] = []
        detections: List[PerceptionDetection] = []
        image_height, image_width = getattr(result, "orig_shape", (0, 0))

        for box in boxes:
            class_id = int(box.cls.item())
            label = names[class_id] if isinstance(names, dict) else names[class_id]
            mapped_label = self.config.class_name_map.get(str(label), str(label))
            confidence = round(float(box.conf.item()), 4)
            bbox_xyxy = [float(value) for value in box.xyxy[0].tolist()]
            if mapped_label not in detected_parts:
                detected_parts.append(mapped_label)
            if mapped_label == self.config.primary_target_part:
                target_boxes.append(bbox_xyxy)
            center_ratio = [0.0, 0.0]
            if image_width and image_height:
                center_x = ((bbox_xyxy[0] + bbox_xyxy[2]) / 2.0) / float(image_width)
                center_y = ((bbox_xyxy[1] + bbox_xyxy[3]) / 2.0) / float(image_height)
                center_ratio = [round(center_x, 4), round(center_y, 4)]
            detections.append(
                PerceptionDetection(
                    part_name=mapped_label,
                    confidence=confidence,
                    bbox_xyxy=bbox_xyxy,
                    bbox_center_ratio=center_ratio,
                    viewpoint=viewpoint,
                )
            )

        missing_critical_parts = []
        if self.config.primary_target_part not in detected_parts:
            missing_critical_parts.append(self.config.primary_target_part)

        metrics: List[PerceptionMetric] = []
        if self.config.emit_bbox_metrics and target_boxes:
            best_box = target_boxes[0]
            width_ratio = 0.0
            height_ratio = 0.0
            if image_width and image_height:
                width_ratio = round((best_box[2] - best_box[0]) / float(image_width), 4)
                height_ratio = round((best_box[3] - best_box[1]) / float(image_height), 4)
            depth_ratio = round(max(width_ratio, height_ratio), 4)
            metrics.append(
                PerceptionMetric(
                    part_name=self.config.primary_target_part,
                    confidence=next(
                        (item.confidence for item in detections if item.part_name == self.config.primary_target_part),
                        0.0,
                    ),
                    current_bounding_box_ratio=[width_ratio, height_ratio, depth_ratio],
                )
            )

        return PerceptionResult(
            detected_parts=detected_parts,
            missing_critical_parts=missing_critical_parts,
            quantitative_metrics=metrics,
            detections=detections,
        )


class BlenderCaptureYoloPerceptionProvider(YoloPerceptionProvider):
    def __init__(
        self,
        config: YoloProviderConfig,
        object_ops: BlenderObjectOps,
        loader: LocalModelLoader = None,
    ) -> None:
        super().__init__(config=config, image_source=None, loader=loader)
        self.object_ops = object_ops

    def observe_views(self) -> Dict[str, PerceptionResult]:
        if self.model is None:
            raise RuntimeError("YOLO model is not loaded. Call load_model() first.")

        observed_by_viewpoint: Dict[str, PerceptionResult] = {}

        for viewpoint in self.config.viewpoints:
            capture_name = f"{self.config.capture_name_prefix}_{viewpoint}.png"
            capture_path = Path(self.object_ops.capture_view(capture_name, viewpoint=viewpoint))
            observed = self._observe_image(capture_path, viewpoint=viewpoint)
            observed_by_viewpoint[viewpoint] = observed

        return observed_by_viewpoint

    def observe(self) -> PerceptionResult:
        observed_by_viewpoint = self.observe_views()
        return self.merge_view_results(observed_by_viewpoint)

    def merge_view_results(self, observed_by_viewpoint: Dict[str, PerceptionResult]) -> PerceptionResult:
        merged_detected_parts: List[str] = []
        merged_detections: List[PerceptionDetection] = []
        best_metric: Optional[PerceptionMetric] = None

        for observed in observed_by_viewpoint.values():
            for part_name in observed.detected_parts:
                if part_name not in merged_detected_parts:
                    merged_detected_parts.append(part_name)
            merged_detections.extend(observed.detections)

            for metric in observed.quantitative_metrics:
                if best_metric is None or self._metric_score(metric) > self._metric_score(best_metric):
                    best_metric = metric

        missing_critical_parts = []
        if self.config.primary_target_part not in merged_detected_parts:
            missing_critical_parts.append(self.config.primary_target_part)

        metrics: List[PerceptionMetric] = [best_metric] if best_metric is not None else []
        return PerceptionResult(
            detected_parts=merged_detected_parts,
            missing_critical_parts=missing_critical_parts,
            quantitative_metrics=metrics,
            detections=merged_detections,
        )

    @staticmethod
    def _metric_score(metric: PerceptionMetric) -> float:
        if not metric.current_bounding_box_ratio:
            return metric.confidence
        return max(metric.current_bounding_box_ratio) + metric.confidence
