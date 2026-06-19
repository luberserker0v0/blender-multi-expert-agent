"""Assembly schemas for the D&C pipeline.

Domain: the deterministic assembly plan — placements, steps, and the
top-level plan that binds everything together.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from ai_3d_modeling_agent.schemas.part import PartFamily, PartSpec


@dataclass
class InstancePlacement:
    """Position, rotation, and scale of a single part instance.

    Computed deterministically by the attachment solver — never by LLM.
    """

    part_name: str
    instance_index: int  # 1-based within family
    source_object_name: str  # the mesh object name in Blender
    world_position: List[float]  # [x, y, z]
    world_rotation_degrees: List[float]  # [rx, ry, rz]
    world_scale: List[float]  # [sx, sy, sz] from target_bbox
    parent_name: str = ""
    parent_attachment_name: str = ""
    child_attachment_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "part_name": self.part_name,
            "instance_index": self.instance_index,
            "source_object_name": self.source_object_name,
            "world_position": list(self.world_position),
            "world_rotation_degrees": list(self.world_rotation_degrees),
            "world_scale": list(self.world_scale),
            "parent_name": self.parent_name,
            "parent_attachment_name": self.parent_attachment_name,
            "child_attachment_name": self.child_attachment_name,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InstancePlacement":
        return cls(
            part_name=d["part_name"],
            instance_index=d["instance_index"],
            source_object_name=d["source_object_name"],
            world_position=list(d["world_position"]),
            world_rotation_degrees=list(d["world_rotation_degrees"]),
            world_scale=list(d["world_scale"]),
            parent_name=d.get("parent_name", ""),
            parent_attachment_name=d.get("parent_attachment_name", ""),
            child_attachment_name=d.get("child_attachment_name", ""),
        )


@dataclass
class AssemblyStep:
    """One step in the assembly sequence.

    All placements within a step can execute in parallel
    (same dependency layer in the DAG).
    """

    step_index: int
    placements: List[InstancePlacement] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_index": self.step_index,
            "placements": [p.to_dict() for p in self.placements],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AssemblyStep":
        return cls(
            step_index=d["step_index"],
            placements=[
                InstancePlacement.from_dict(p) for p in d.get("placements", [])
            ],
        )


@dataclass
class AssemblyPlan:
    """Complete assembly plan with all steps, families, and specs.

    Produced deterministically from Phase 1 (decompose) + Phase 2 (specify).
    No LLM call involved.
    """

    steps: List[AssemblyStep] = field(default_factory=list)
    part_families: List[PartFamily] = field(default_factory=list)
    part_specs: Dict[str, PartSpec] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "part_families": [pf.to_dict() for pf in self.part_families],
            "part_specs": {k: v.to_dict() for k, v in self.part_specs.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AssemblyPlan":
        return cls(
            steps=[AssemblyStep.from_dict(s) for s in d.get("steps", [])],
            part_families=[
                PartFamily.from_dict(pf) for pf in d.get("part_families", [])
            ],
            part_specs={
                k: PartSpec.from_dict(v) for k, v in d.get("part_specs", {}).items()
            },
        )
