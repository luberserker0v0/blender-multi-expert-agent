"""Gap report schema models for the MVP."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DetectionItem:
    part_name: str
    confidence: float
    bbox_xyxy: List[float] = field(default_factory=list)
    bbox_center_ratio: List[float] = field(default_factory=list)
    viewpoint: str = ""


@dataclass
class BlenderContext:
    current_mode: str
    active_object_name: str
    active_element_mode: str


@dataclass
class QuantitativeMetric:
    part_name: str
    status: str
    current_ratio_to_body: float
    target_ratio_to_body: float
    action_suggestion: str
    axis: str = "uniform"
    current_bounding_box_ratio: List[float] = field(default_factory=list)
    target_bounding_box_ratio: List[float] = field(default_factory=list)


@dataclass
class YoloVisionFeedback:
    detected_parts: List[str]
    missing_critical_parts: List[str]
    quantitative_metrics: List[QuantitativeMetric]
    detections: List[DetectionItem] = field(default_factory=list)


@dataclass
class OptimizationHistoryNote:
    previous_action_failed: bool
    last_successful_macro_id: str


@dataclass
class GapReport:
    timestamp: int
    blender_context: BlenderContext
    yolo_vision_feedback: YoloVisionFeedback
    optimization_history_note: OptimizationHistoryNote

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "blender_context": {
                "current_mode": self.blender_context.current_mode,
                "active_object_name": self.blender_context.active_object_name,
                "active_element_mode": self.blender_context.active_element_mode,
            },
            "yolo_vision_feedback": {
                "detected_parts": list(self.yolo_vision_feedback.detected_parts),
                "missing_critical_parts": list(self.yolo_vision_feedback.missing_critical_parts),
                "quantitative_metrics": [
                    {
                        "part_name": item.part_name,
                        "status": item.status,
                        "current_ratio_to_body": item.current_ratio_to_body,
                        "target_ratio_to_body": item.target_ratio_to_body,
                        "action_suggestion": item.action_suggestion,
                        "axis": item.axis,
                        "current_bounding_box_ratio": list(item.current_bounding_box_ratio),
                        "target_bounding_box_ratio": list(item.target_bounding_box_ratio),
                    }
                    for item in self.yolo_vision_feedback.quantitative_metrics
                ],
                "detections": [
                    {
                        "part_name": item.part_name,
                        "confidence": item.confidence,
                        "bbox_xyxy": list(item.bbox_xyxy),
                        "bbox_center_ratio": list(item.bbox_center_ratio),
                        "viewpoint": item.viewpoint,
                    }
                    for item in self.yolo_vision_feedback.detections
                ],
            },
            "optimization_history_note": {
                "previous_action_failed": self.optimization_history_note.previous_action_failed,
                "last_successful_macro_id": self.optimization_history_note.last_successful_macro_id,
            },
        }
