"""Part-family schemas for the D&C pipeline.

Domain: everything that defines *what a part is* — its family membership,
specification (geometry, attachment points), symmetry rule, and the
world-scale normalization constant.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SymmetryGroup(str, Enum):
    """Symmetry group for instance placement.

    Determines how multiple instances of a part family are positioned.
    """

    NONE = "NONE"
    LEFT_RIGHT_X = "LEFT_RIGHT_X"
    LEFT_RIGHT_Y = "LEFT_RIGHT_Y"
    QUADRANT_Z = "QUADRANT_Z"
    RADIAL_4_Z = "RADIAL_4_Z"


# ── constants ──────────────────────────────────────────────────────────

SCALE_NORMALIZATION = 0.5
"""Blender default primitives are 2 units (from -1 to +1).  Multiply bounding
box dimensions by this factor in build steps to normalize to world scale."""


@dataclass
class AttachmentPoint:
    """A semantic anchor point on a part, defined as an offset from the part's center.

    The LLM declares this offset in local space; the attachment solver
    computes the world-space position during assembly.
    """

    name: str
    local_offset: List[float]  # [x, y, z] offset from part center
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "local_offset": list(self.local_offset),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttachmentPoint":
        return cls(
            name=d["name"],
            local_offset=list(d["local_offset"]),
            description=d.get("description", ""),
        )


@dataclass
class PartFamily:
    """A logical group of identical or symmetrically-placed parts.

    E.g. "leg" with instance_count=4 and symmetry_group=QUADRANT_Z
    means 4 identical legs placed at 90° intervals around Z.
    """

    name: str
    description: str
    instance_count: int = 1
    parent_name: Optional[str] = None
    symmetry_group: SymmetryGroup = SymmetryGroup.NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "instance_count": self.instance_count,
            "parent_name": self.parent_name,
            "symmetry_group": self.symmetry_group.value,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PartFamily":
        return cls(
            name=d["name"],
            description=d["description"],
            instance_count=d.get("instance_count", 1),
            parent_name=d.get("parent_name"),
            symmetry_group=SymmetryGroup(d.get("symmetry_group", "NONE")),
        )


@dataclass
class PartSpec:
    """Detailed specification for a part family — geometry and attachment."""

    primitive: str  # "cube" | "uv_sphere" | "cylinder" | "plane"
    target_bbox: Dict[str, float]  # {"width": float, "depth": float, "height": float}
    refinement_viewpoint: str = "front"
    attachment_points: List[AttachmentPoint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "primitive": self.primitive,
            "target_bbox": dict(self.target_bbox),
            "refinement_viewpoint": self.refinement_viewpoint,
            "attachment_points": [ap.to_dict() for ap in self.attachment_points],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PartSpec":
        return cls(
            primitive=d["primitive"],
            target_bbox=dict(d["target_bbox"]),
            refinement_viewpoint=d.get("refinement_viewpoint", "front"),
            attachment_points=[
                AttachmentPoint.from_dict(ap) for ap in d.get("attachment_points", [])
            ],
        )
