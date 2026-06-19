"""Action executor for the MVP pipeline.

Supported action types: create_uv_sphere, create_primitive, select_object,
scale_uniform, scale_axis_x, scale_axis_y, scale_axis_z, move_object,
set_object_scale, rotate_object, hide_object, show_object,
duplicate_object, mirror_object, set_parent, create_collection,
move_to_collection, finish
"""

from typing import List

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.schemas.actions import Action


class ActionExecutor:
    def __init__(self, object_ops: BlenderObjectOps) -> None:
        self.object_ops = object_ops

    def execute(self, action: Action) -> bool:
        if action.action_type == "create_uv_sphere":
            self.object_ops.create_uv_sphere(str(action.parameters["name"]))
            return True
        if action.action_type == "create_primitive":
            self.object_ops.create_primitive(
                str(action.parameters["primitive_type"]),
                str(action.parameters["name"]),
            )
            return True
        if action.action_type == "select_object":
            self.object_ops.set_active_object(str(action.parameters["name"]))
            return True
        if action.action_type == "scale_uniform":
            self._set_active_object_if_present(action)
            self.object_ops.scale_uniform(float(action.parameters["factor"]))
            return True
        if action.action_type == "scale_axis_x":
            self._set_active_object_if_present(action)
            self.object_ops.scale_axis("x", float(action.parameters["factor"]))
            return True
        if action.action_type == "scale_axis_y":
            self._set_active_object_if_present(action)
            self.object_ops.scale_axis("y", float(action.parameters["factor"]))
            return True
        if action.action_type == "scale_axis_z":
            self._set_active_object_if_present(action)
            self.object_ops.scale_axis("z", float(action.parameters["factor"]))
            return True
        if action.action_type == "move_object":
            self.object_ops.move_object(
                str(action.parameters["name"]),
                self._as_float_list(action.parameters["location"]),
            )
            return True
        if action.action_type == "set_object_scale":
            self.object_ops.set_object_scale(
                str(action.parameters["name"]),
                self._as_float_list(action.parameters["scale"]),
            )
            return True
        if action.action_type == "rotate_object":
            self.object_ops.rotate_object(
                str(action.parameters["name"]),
                self._as_float_list(action.parameters["rotation_degrees"]),
            )
            return True
        if action.action_type == "hide_object":
            self.object_ops.set_object_hidden(str(action.parameters["name"]), True)
            return True
        if action.action_type == "show_object":
            self.object_ops.set_object_hidden(str(action.parameters["name"]), False)
            return True
        if action.action_type == "duplicate_object":
            self.object_ops.duplicate_object(
                str(action.parameters["name"]),
                str(action.parameters["new_name"]),
            )
            return True
        if action.action_type == "delete_object":
            self.object_ops.delete_object(str(action.parameters["name"]))
            return True
        if action.action_type == "mirror_object":
            self.object_ops.mirror_object(
                str(action.parameters["name"]),
                str(action.parameters["axis"]),
            )
            return True
        if action.action_type == "set_parent":
            self.object_ops.set_parent(
                str(action.parameters["child_name"]),
                str(action.parameters["parent_name"]),
            )
            return True
        if action.action_type == "create_collection":
            self.object_ops.create_collection(str(action.parameters["name"]))
            return True
        if action.action_type == "move_to_collection":
            self.object_ops.move_to_collection(
                str(action.parameters["object_name"]),
                str(action.parameters["collection_name"]),
            )
            return True
        if action.action_type == "finish":
            return True
        raise ValueError(f"Unsupported action type: {action.action_type}")

    @staticmethod
    def _as_float_list(value) -> List[float]:
        return [float(item) for item in list(value)]

    def _set_active_object_if_present(self, action: Action) -> None:
        name = action.parameters.get("name")
        if isinstance(name, str) and name.strip():
            self.object_ops.set_active_object(name)
