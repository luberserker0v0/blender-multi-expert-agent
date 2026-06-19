"""Target checklist schema models for the MVP."""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class GlobalMetrics:
    expected_bounding_box_ratio: List[float]
    max_polygon_count_limit: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalMetrics":
        return cls(
            expected_bounding_box_ratio=list(data["expected_bounding_box_ratio"]),
            max_polygon_count_limit=int(data["max_polygon_count_limit"]),
        )


@dataclass
class MeasurementParameters:
    acceptable_tolerance: float
    from_keypoint: str = ""
    to_keypoint: str = ""
    target_ratio_of_head_height: float = 0.0
    target_aspect_ratio_w_h: List[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MeasurementParameters":
        return cls(
            acceptable_tolerance=float(data["acceptable_tolerance"]),
            from_keypoint=str(data.get("from_keypoint", "")),
            to_keypoint=str(data.get("to_keypoint", "")),
            target_ratio_of_head_height=float(data.get("target_ratio_of_head_height", 0.0)),
            target_aspect_ratio_w_h=list(data.get("target_aspect_ratio_w_h", [])),
        )


@dataclass
class CriticalPartItem:
    part_id: str
    part_name: str
    yolo_label_trigger: str
    observation_view: str
    metric_type: str
    measurement_parameters: MeasurementParameters

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CriticalPartItem":
        return cls(
            part_id=str(data["part_id"]),
            part_name=str(data["part_name"]),
            yolo_label_trigger=str(data["yolo_label_trigger"]),
            observation_view=str(data["observation_view"]),
            metric_type=str(data["metric_type"]),
            measurement_parameters=MeasurementParameters.from_dict(data["measurement_parameters"]),
        )


@dataclass
class TargetPartChecklist:
    target_object_class: str
    global_metrics: GlobalMetrics
    critical_parts_checklist: List[CriticalPartItem]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TargetPartChecklist":
        return cls(
            target_object_class=str(data["target_object_class"]),
            global_metrics=GlobalMetrics.from_dict(data["global_metrics"]),
            critical_parts_checklist=[
                CriticalPartItem.from_dict(item)
                for item in data.get("critical_parts_checklist", [])
            ],
        )
