"""Mock perception provider for the MVP pipeline."""

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.perception.base import (
    PerceptionDetection,
    PerceptionMetric,
    PerceptionProvider,
    PerceptionResult,
)


class MockPerceptionProvider(PerceptionProvider):
    def __init__(
        self,
        object_ops: BlenderObjectOps,
        target_object_class: str = "apple",
    ) -> None:
        self.object_ops = object_ops
        self.target_object_class = target_object_class
        self._target_body = f"{target_object_class}_body"

    def observe(self) -> PerceptionResult:
        active_object = self.object_ops.get_active_object()
        if active_object is None:
            return PerceptionResult(
                detected_parts=[],
                missing_critical_parts=[self._target_body],
                quantitative_metrics=[],
                detections=[],
            )

        return PerceptionResult(
            detected_parts=[self._target_body],
            missing_critical_parts=[],
            quantitative_metrics=[
                PerceptionMetric(
                    part_name=self._target_body,
                    confidence=1.0,
                    current_bounding_box_ratio=list(active_object.scale),
                )
            ],
            detections=[
                PerceptionDetection(
                    part_name=self._target_body,
                    confidence=1.0,
                    bbox_xyxy=[0.0, 0.0, active_object.scale[0], active_object.scale[1]],
                    bbox_center_ratio=[0.5, 0.5],
                    viewpoint="front",
                )
            ],
        )
