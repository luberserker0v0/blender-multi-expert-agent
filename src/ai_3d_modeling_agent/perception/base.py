"""Perception abstractions shared by mock and future YOLO providers."""

from dataclasses import dataclass, field
from typing import Dict, List, Protocol


@dataclass
class PerceptionDetection:
    part_name: str
    confidence: float
    bbox_xyxy: List[float] = field(default_factory=list)
    bbox_center_ratio: List[float] = field(default_factory=list)
    viewpoint: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "part_name": self.part_name,
            "confidence": self.confidence,
            "bbox_xyxy": list(self.bbox_xyxy),
            "bbox_center_ratio": list(self.bbox_center_ratio),
            "viewpoint": self.viewpoint,
        }


@dataclass
class PerceptionMetric:
    part_name: str
    confidence: float = 0.0
    current_bounding_box_ratio: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "part_name": self.part_name,
            "confidence": self.confidence,
            "current_bounding_box_ratio": list(self.current_bounding_box_ratio),
        }


@dataclass
class PerceptionResult:
    detected_parts: List[str]
    missing_critical_parts: List[str]
    quantitative_metrics: List[PerceptionMetric]
    detections: List[PerceptionDetection] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "detected_parts": list(self.detected_parts),
            "missing_critical_parts": list(self.missing_critical_parts),
            "quantitative_metrics": [item.to_dict() for item in self.quantitative_metrics],
            "detections": [item.to_dict() for item in self.detections],
        }


class PerceptionProvider(Protocol):
    def observe(self) -> PerceptionResult:
        """Return structured perception output for the current scene."""
