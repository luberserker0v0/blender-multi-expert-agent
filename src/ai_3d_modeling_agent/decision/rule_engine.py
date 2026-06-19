"""Rule-based decision engine for the MVP pipeline."""

from ai_3d_modeling_agent.decision.base import DecisionEngine
from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.gap_report import GapReport


class RuleDecisionEngine(DecisionEngine):
    def decide(self, gap_report: GapReport) -> Action:
        if not gap_report.blender_context.active_object_name:
            return Action("create_uv_sphere", {"name": "apple_body"}, "No active object found.")

        if gap_report.optimization_history_note.previous_action_failed:
            return Action("finish", {}, "Previous action failed.")

        feedback = gap_report.yolo_vision_feedback
        if feedback.missing_critical_parts:
            return Action("create_uv_sphere", {"name": "apple_body"}, "Critical part missing.")

        if not feedback.quantitative_metrics:
            return Action("finish", {}, "No quantitative metrics available.")

        metric = feedback.quantitative_metrics[0]
        if metric.status == "UNDER_SIZED":
            return Action("scale_uniform", {"factor": 1.5}, metric.action_suggestion)
        if metric.status == "OVER_SIZED":
            return Action("scale_uniform", {"factor": 0.8}, metric.action_suggestion)
        if metric.status == "DISTORTED":
            return Action(
                f"scale_axis_{metric.axis}",
                {"factor": 1.1 if self._needs_scale_up(metric) else 0.9},
                metric.action_suggestion,
            )
        return Action("finish", {}, "Target reached.")

    @staticmethod
    def _needs_scale_up(metric) -> bool:
        axis_map = {"x": 0, "y": 1, "z": 2}
        idx = axis_map[metric.axis]
        return metric.current_bounding_box_ratio[idx] < metric.target_bounding_box_ratio[idx]
