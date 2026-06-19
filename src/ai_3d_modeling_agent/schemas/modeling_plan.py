"""Structured contracts for multi-stage 3D modeling workflows."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.task_objects import TaskObjectSpec


@dataclass
class UserReference:
    reference_type: str
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "reference_type": self.reference_type,
            "content": self.content,
        }


@dataclass
class ModelingRequest:
    task_prompt: str
    references: List[UserReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_prompt": self.task_prompt,
            "references": [item.to_dict() for item in self.references],
        }


@dataclass
class BoundingBoxSpec:
    width: float
    depth: float
    height: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "width": float(self.width),
            "depth": float(self.depth),
            "height": float(self.height),
        }

    def to_xyz(self) -> List[float]:
        return [float(self.width), float(self.depth), float(self.height)]


@dataclass
class AnchorPointSpec:
    name: str
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    description: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "position": list(self.position),
            "description": self.description,
        }


@dataclass
class StructuralSpec:
    parent_task_id: str = ""
    attach_to: str = ""
    symmetry_group: str = ""
    # D&C fields (used when --use-dnc is active)
    instance_count: int = 1
    instance_generation_mode: str = "independent"  # "independent" | "duplicate_from_source"
    sizing_notes: str = ""
    placement_notes: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "parent_task_id": self.parent_task_id,
            "attach_to": self.attach_to,
            "symmetry_group": self.symmetry_group,
            "instance_count": self.instance_count,
            "instance_generation_mode": self.instance_generation_mode,
            "sizing_notes": self.sizing_notes,
            "placement_notes": self.placement_notes,
        }


@dataclass
class ModelingTask:
    task_id: str
    title: str
    object_name: str
    description: str
    preferred_primitive: str
    refinement_viewpoint: str = "front"
    target_bbox: BoundingBoxSpec = field(default_factory=lambda: BoundingBoxSpec(1.0, 1.0, 1.0))
    anchor_points: List[AnchorPointSpec] = field(default_factory=list)
    structural_spec: StructuralSpec = field(default_factory=StructuralSpec)
    assembly_scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    assembly_location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    assembly_rotation_degrees: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "object_name": self.object_name,
            "description": self.description,
            "preferred_primitive": self.preferred_primitive,
            "refinement_viewpoint": self.refinement_viewpoint,
            "target_bbox": self.target_bbox.to_dict(),
            "anchor_points": [item.to_dict() for item in self.anchor_points],
            "structural_spec": self.structural_spec.to_dict(),
            "assembly_scale": list(self.assembly_scale),
            "assembly_location": list(self.assembly_location),
            "assembly_rotation_degrees": list(self.assembly_rotation_degrees),
        }


@dataclass
class ModelingPlan:
    task_prompt: str
    reasoning: str
    tasks: List[ModelingTask]
    task_objects: List[TaskObjectSpec] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "task_prompt": self.task_prompt,
            "reasoning": self.reasoning,
            "tasks": [item.to_dict() for item in self.tasks],
            "task_objects": [item.to_dict() for item in self.task_objects],
        }


@dataclass
class PartFeedback:
    approved: bool
    summary: str
    action: Optional[Action] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "summary": self.summary,
            "action": None
            if self.action is None
            else {
                "action_type": self.action.action_type,
                "parameters": dict(self.action.parameters),
                "reason": self.action.reason,
            },
        }


@dataclass
class AssemblyFeedback:
    approved: bool
    summary: str
    actions: List[Action] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "summary": self.summary,
            "actions": [
                {
                    "action_type": item.action_type,
                    "parameters": dict(item.parameters),
                    "reason": item.reason,
                }
                for item in self.actions
            ],
        }
