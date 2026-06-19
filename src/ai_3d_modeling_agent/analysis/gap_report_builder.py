"""Gap report builder for the MVP pipeline."""

import time

from ai_3d_modeling_agent.schemas.gap_report import (
    DetectionItem,
    GapReport,
    OptimizationHistoryNote,
    QuantitativeMetric,
    YoloVisionFeedback,
)
from ai_3d_modeling_agent.perception.base import PerceptionResult
from ai_3d_modeling_agent.schemas.target_part_checklist import TargetPartChecklist


class GapReportBuilder:
    def build(
        self,
        checklist: TargetPartChecklist,
        blender_context,
        perception_result: PerceptionResult,
        previous_action_failed: bool,
        last_successful_macro_id: str,
    ) -> GapReport:
        target_ratio = checklist.global_metrics.expected_bounding_box_ratio
        metrics = []

        for item in perception_result.quantitative_metrics:
            current_ratio = list(item.current_bounding_box_ratio)
            status = "OK"
            action_suggestion = "NONE"
            axis = "uniform"

            if current_ratio:
                if self._all_below(current_ratio, target_ratio, 0.9):
                    status = "UNDER_SIZED"
                    action_suggestion = "SCALE_UNIFORM_UP"
                elif self._all_above(current_ratio, target_ratio, 1.1):
                    status = "OVER_SIZED"
                    action_suggestion = "SCALE_UNIFORM_DOWN"
                else:
                    axis_index = self._find_distorted_axis(current_ratio, target_ratio, checklist)
                    if axis_index is not None:
                        status = "DISTORTED"
                        axis = ["x", "y", "z"][axis_index]
                        action_suggestion = f"SCALE_AXIS_{axis.upper()}"

            metrics.append(
                QuantitativeMetric(
                    part_name=str(item.part_name),
                    status=status,
                    current_ratio_to_body=1.0,
                    target_ratio_to_body=1.0,
                    action_suggestion=action_suggestion,
                    axis=axis,
                    current_bounding_box_ratio=current_ratio,
                    target_bounding_box_ratio=list(target_ratio),
                )
            )

        feedback = YoloVisionFeedback(
            detected_parts=list(perception_result.detected_parts),
            missing_critical_parts=list(perception_result.missing_critical_parts),
            quantitative_metrics=metrics,
            detections=[
                DetectionItem(
                    part_name=item.part_name,
                    confidence=float(item.confidence),
                    bbox_xyxy=list(item.bbox_xyxy),
                    bbox_center_ratio=list(item.bbox_center_ratio),
                    viewpoint=str(item.viewpoint),
                )
                for item in perception_result.detections
            ],
        )

        return GapReport(
            timestamp=int(time.time()),
            blender_context=blender_context,
            yolo_vision_feedback=feedback,
            optimization_history_note=OptimizationHistoryNote(
                previous_action_failed=previous_action_failed,
                last_successful_macro_id=last_successful_macro_id,
            ),
        )

    @staticmethod
    def _all_below(current_ratio, target_ratio, threshold: float) -> bool:
        return all(current < target * threshold for current, target in zip(current_ratio, target_ratio))

    @staticmethod
    def _all_above(current_ratio, target_ratio, threshold: float) -> bool:
        return all(current > target * threshold for current, target in zip(current_ratio, target_ratio))

    @staticmethod
    def _find_distorted_axis(current_ratio, target_ratio, checklist) -> int:
        acceptable_tolerance = 0.1
        for index, (current, target) in enumerate(zip(current_ratio, target_ratio)):
            if abs(current - target) > acceptable_tolerance:
                return index
        return None
