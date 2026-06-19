"""Structured session progress contracts for GUI-facing workflows."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.perception.base import PerceptionMetric, PerceptionResult
from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.gap_report import BlenderContext
from ai_3d_modeling_agent.schemas.modeling_plan import ModelingPlan, ModelingRequest
from ai_3d_modeling_agent.schemas.task_objects import TaskObjectSpec


@dataclass
class DnCNodeProgress:
    """Tracks the status of a single DAG node in the D&C pipeline."""

    part_name: str
    status: str = "pending"  # "pending" | "building" | "approved" | "failed" | "skipped"
    instance_count: int = 1
    symmetry_group: str = "NONE"
    failure_reason: str = ""
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "status": self.status,
            "instance_count": self.instance_count,
            "symmetry_group": self.symmetry_group,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
        }


@dataclass
class ProgressActionRecord:
    action_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    execution_status: str = "pending"

    @classmethod
    def from_action(cls, action: Action, execution_status: str = "pending") -> "ProgressActionRecord":
        return cls(
            action_type=action.action_type,
            parameters=dict(action.parameters),
            reason=action.reason,
            execution_status=execution_status,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "parameters": dict(self.parameters),
            "reason": self.reason,
            "execution_status": self.execution_status,
        }


@dataclass
class ProgressContextRecord:
    current_mode: str = ""
    active_object_name: str = ""
    active_element_mode: str = ""

    @classmethod
    def from_blender_context(cls, context: BlenderContext) -> "ProgressContextRecord":
        return cls(
            current_mode=context.current_mode,
            active_object_name=context.active_object_name,
            active_element_mode=context.active_element_mode,
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "current_mode": self.current_mode,
            "active_object_name": self.active_object_name,
            "active_element_mode": self.active_element_mode,
        }


@dataclass
class PartRefinementRoundRecord:
    round_index: int
    capture_path: str = ""
    viewpoint: str = ""
    capture_paths: List[str] = field(default_factory=list)
    viewpoints: List[str] = field(default_factory=list)
    llm_prompt_preview: str = ""
    approved: bool = False
    feedback_summary: str = ""
    context: ProgressContextRecord = field(default_factory=ProgressContextRecord)
    requested_action: Optional[ProgressActionRecord] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_index": self.round_index,
            "capture_path": self.capture_path,
            "viewpoint": self.viewpoint,
            "capture_paths": list(self.capture_paths),
            "viewpoints": list(self.viewpoints),
            "llm_prompt_preview": self.llm_prompt_preview,
            "approved": self.approved,
            "feedback_summary": self.feedback_summary,
            "context": self.context.to_dict(),
            "requested_action": None if self.requested_action is None else self.requested_action.to_dict(),
        }


@dataclass
class PartTaskProgress:
    task_id: str
    title: str
    object_name: str
    status: str = "pending"
    current_round: int = 0
    approved: bool = False
    hidden_after_approval: bool = False
    rounds: List[PartRefinementRoundRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "object_name": self.object_name,
            "status": self.status,
            "current_round": self.current_round,
            "approved": self.approved,
            "hidden_after_approval": self.hidden_after_approval,
            "rounds": [item.to_dict() for item in self.rounds],
        }


@dataclass
class AssemblyRoundRecord:
    round_index: int
    task_id: str = ""
    task_title: str = ""
    assembly_step_index: int = 0
    capture_path: str = ""
    capture_paths: List[str] = field(default_factory=list)
    viewpoints: List[str] = field(default_factory=list)
    llm_prompt_preview: str = ""
    approved: bool = False
    feedback_summary: str = ""
    context: ProgressContextRecord = field(default_factory=ProgressContextRecord)
    requested_actions: List[ProgressActionRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_index": self.round_index,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "assembly_step_index": self.assembly_step_index,
            "capture_path": self.capture_path,
            "capture_paths": list(self.capture_paths),
            "viewpoints": list(self.viewpoints),
            "llm_prompt_preview": self.llm_prompt_preview,
            "approved": self.approved,
            "feedback_summary": self.feedback_summary,
            "context": self.context.to_dict(),
            "requested_actions": [item.to_dict() for item in self.requested_actions],
        }


@dataclass
class AssemblyProgress:
    status: str = "pending"
    current_round: int = 0
    approved: bool = False
    all_parts_visible: bool = False
    initial_placement_applied: bool = False
    rounds: List[AssemblyRoundRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_round": self.current_round,
            "approved": self.approved,
            "all_parts_visible": self.all_parts_visible,
            "initial_placement_applied": self.initial_placement_applied,
            "rounds": [item.to_dict() for item in self.rounds],
        }


@dataclass
class FinalValidationSummary:
    status: str = "pending"
    capture_path: str = ""
    viewpoint: str = "front"
    detected_parts: List[str] = field(default_factory=list)
    missing_critical_parts: List[str] = field(default_factory=list)
    quantitative_metrics: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_perception_result(
        cls,
        perception_result: PerceptionResult,
        capture_path: str,
        viewpoint: str = "front",
        status: str = "completed",
    ) -> "FinalValidationSummary":
        return cls(
            status=status,
            capture_path=capture_path,
            viewpoint=viewpoint,
            detected_parts=list(perception_result.detected_parts),
            missing_critical_parts=list(perception_result.missing_critical_parts),
            quantitative_metrics=[
                cls._metric_to_dict(item) for item in perception_result.quantitative_metrics
            ],
        )

    @staticmethod
    def _metric_to_dict(metric: PerceptionMetric) -> Dict[str, Any]:
        return {
            "part_name": metric.part_name,
            "confidence": metric.confidence,
            "current_bounding_box_ratio": list(metric.current_bounding_box_ratio),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "capture_path": self.capture_path,
            "viewpoint": self.viewpoint,
            "detected_parts": list(self.detected_parts),
            "missing_critical_parts": list(self.missing_critical_parts),
            "quantitative_metrics": list(self.quantitative_metrics),
        }


@dataclass
class LlmPromptEventRecord:
    event_id: str
    stage: str = ""
    label: str = ""
    prompt_preview: str = ""
    response_preview: str = ""
    validation_error: str = ""
    has_images: bool = False
    image_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "stage": self.stage,
            "label": self.label,
            "prompt_preview": self.prompt_preview,
            "response_preview": self.response_preview,
            "validation_error": self.validation_error,
            "has_images": self.has_images,
            "image_count": self.image_count,
        }


@dataclass
class MultiStageProgressSnapshot:
    workflow_type: str
    status: str
    task: str
    stage: str
    stage_status: str
    request: ModelingRequest
    required_objects: List[TaskObjectSpec]
    plan: Optional[ModelingPlan] = None
    multi_expert_mode: bool = True
    planning_llm_prompt_preview: str = ""
    llm_prompt_events: List[LlmPromptEventRecord] = field(default_factory=list)
    active_task_id: str = ""
    completed_task_ids: List[str] = field(default_factory=list)
    part_tasks: List[PartTaskProgress] = field(default_factory=list)
    assembly: AssemblyProgress = field(default_factory=AssemblyProgress)
    final_validation: FinalValidationSummary = field(default_factory=FinalValidationSummary)
    stop_reason: str = ""
    max_part_refinement_rounds: int = 0
    max_assembly_rounds: int = 0
    # D&C pipeline fields
    dnc_mode: bool = False
    checkpoint_version: int = 0
    dnc_part_progress: List[DnCNodeProgress] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow_type": self.workflow_type,
            "status": self.status,
            "task": self.task,
            "stage": self.stage,
            "stage_status": self.stage_status,
            "multi_expert_mode": self.multi_expert_mode,
            "request": self.request.to_dict(),
            "required_objects": [item.to_dict() for item in self.required_objects],
            "plan": None if self.plan is None else self.plan.to_dict(),
            "planning_llm_prompt_preview": self.planning_llm_prompt_preview,
            "llm_prompt_events": [item.to_dict() for item in self.llm_prompt_events],
            "active_task_id": self.active_task_id,
            "completed_task_ids": list(self.completed_task_ids),
            "part_tasks": [item.to_dict() for item in self.part_tasks],
            "assembly": self.assembly.to_dict(),
            "final_validation": self.final_validation.to_dict(),
            "stop_reason": self.stop_reason,
            "max_part_refinement_rounds": self.max_part_refinement_rounds,
            "max_assembly_rounds": self.max_assembly_rounds,
            "dnc_mode": self.dnc_mode,
            "checkpoint_version": self.checkpoint_version,
            "dnc_part_progress": [item.to_dict() for item in self.dnc_part_progress],
        }
