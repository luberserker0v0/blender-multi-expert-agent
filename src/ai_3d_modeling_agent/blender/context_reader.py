"""Blender context reader for the MVP simulation."""

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.schemas.gap_report import BlenderContext


class SimulatedBlenderContextReader:
    def __init__(self, object_ops: BlenderObjectOps) -> None:
        self.object_ops = object_ops

    def read(self) -> BlenderContext:
        active_object = self.object_ops.get_active_object()
        return BlenderContext(
            current_mode="OBJECT",
            active_object_name=active_object.name if active_object else "",
            active_element_mode="NONE",
        )
