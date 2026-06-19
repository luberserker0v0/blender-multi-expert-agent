"""Blender object operation interfaces and MVP in-memory implementation."""

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set


@dataclass
class SimulatedObject:
    name: str
    primitive_type: str
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation_degrees: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    polygon_count: int = 256
    hidden: bool = False


class BlenderObjectOps(Protocol):
    def list_object_names(self) -> List[str]:
        """Return all object names currently present in the scene."""

    def object_exists(self, name: str) -> bool:
        """Return whether an object exists."""

    def create_uv_sphere(self, name: str) -> SimulatedObject:
        """Create a sphere-like object and return it."""

    def create_primitive(self, primitive_type: str, name: str) -> SimulatedObject:
        """Create an object from a named primitive type."""

    def get_active_object(self) -> Optional[SimulatedObject]:
        """Return the active object summary."""

    def set_active_object(self, name: str) -> None:
        """Make a named object active."""

    def scale_uniform(self, factor: float) -> None:
        """Scale the active object uniformly."""

    def scale_axis(self, axis: str, factor: float) -> None:
        """Scale the active object on a single axis."""

    def move_object(self, name: str, location: List[float]) -> None:
        """Move a named object to an absolute location."""

    def get_object_dimensions(self, name: str) -> List[float]:
        """Return a named object's current XYZ dimensions."""

    def set_object_scale(self, name: str, scale: List[float]) -> None:
        """Set a named object's XYZ scale directly."""

    def rotate_object(self, name: str, rotation_degrees: List[float]) -> None:
        """Rotate a named object using XYZ degrees."""

    def set_object_hidden(self, name: str, hidden: bool) -> None:
        """Hide or unhide a named object."""

    def capture_view(
        self,
        capture_name: str,
        viewpoint: str = "front",
        object_name: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Render a Blender camera view and return the image path.

        Args:
            capture_name: Filename for the captured image (e.g. ``"part_refine.png"``).
            viewpoint: Camera viewpoint name (``"front"``, ``"top"``, ``"side"``, etc.).
            object_name: Optional specific object to focus on.
            output_dir: Optional output directory override.  If not provided,
                        implementations use a default captures directory.
        """

    def delete_object(self, name: str) -> bool:
        """Delete a named object and return whether it existed."""

    def duplicate_object(self, name: str, new_name: str) -> SimulatedObject:
        """Duplicate an existing object by name and return the new copy."""

    def mirror_object(self, name: str, axis: str) -> SimulatedObject:
        """Mirror an object across the given axis ('x', 'y', or 'z').
        Creates and applies a MIRROR modifier on that axis. Returns the modified object."""

    def get_bbox_corners(self, name: str) -> List[List[float]]:
        """Return the 8 world-space corner coordinates of an object's bounding box.
        Returns list of [x,y,z] triples, one per corner."""

    def set_parent(self, child_name: str, parent_name: str) -> None:
        """Set parent_name as the parent of child_name in Blender's transform hierarchy."""

    def get_object_parent(self, name: str) -> Optional[str]:
        """Return the parent object's name, or None if the object has no parent."""

    def get_object_children(self, name: str) -> List[str]:
        """Return the names of all direct children of the given object."""

    def get_object_location(self, name: str) -> List[float]:
        """Return the [x, y, z] location of the named object."""

    def get_object_rotation(self, name: str) -> List[float]:
        """Return the [rx, ry, rz] rotation (degrees) of the named object."""

    def get_object_scale(self, name: str) -> List[float]:
        """Return the [sx, sy, sz] scale of the named object."""

    def create_collection(self, name: str) -> None:
        """Create a new named collection in the scene."""

    def move_to_collection(self, object_name: str, collection_name: str) -> None:
        """Move an object from its current collection into the named collection."""


class SimulatedBlenderObjectOps:
    def __init__(self) -> None:
        self.objects: Dict[str, SimulatedObject] = {}
        self.active_object_name: Optional[str] = None
        self._parent_map: Dict[str, str] = {}
        self._collections: Set[str] = set()

    def object_exists(self, name: str) -> bool:
        return name in self.objects

    def list_object_names(self) -> List[str]:
        return sorted(self.objects.keys())

    def create_uv_sphere(self, name: str) -> SimulatedObject:
        return self.create_primitive("uv_sphere", name)

    def create_primitive(self, primitive_type: str, name: str) -> SimulatedObject:
        obj = SimulatedObject(name=name, primitive_type=str(primitive_type).upper())
        self.objects[name] = obj
        self.active_object_name = name
        return obj

    def get_active_object(self) -> Optional[SimulatedObject]:
        if self.active_object_name is None:
            return None
        return self.objects.get(self.active_object_name)

    def set_active_object(self, name: str) -> None:
        if name not in self.objects:
            raise RuntimeError(f"Object does not exist: {name}")
        self.active_object_name = name

    def scale_uniform(self, factor: float) -> None:
        obj = self.get_active_object()
        if obj is None:
            raise RuntimeError("No active object to scale.")
        obj.scale = [round(axis * factor, 4) for axis in obj.scale]

    def scale_axis(self, axis: str, factor: float) -> None:
        obj = self.get_active_object()
        if obj is None:
            raise RuntimeError("No active object to scale.")
        axis_map = {"x": 0, "y": 1, "z": 2}
        index = axis_map[axis]
        obj.scale[index] = round(obj.scale[index] * factor, 4)

    def move_object(self, name: str, location: List[float]) -> None:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        obj.location = [round(float(value), 4) for value in location]

    def get_object_dimensions(self, name: str) -> List[float]:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        base_dimensions = {
            "UV_SPHERE": [2.0, 2.0, 2.0],
            "CUBE": [2.0, 2.0, 2.0],
            "CYLINDER": [2.0, 2.0, 2.0],
            "PLANE": [2.0, 2.0, 0.0],
        }.get(obj.primitive_type, [2.0, 2.0, 2.0])
        dimensions: List[float] = []
        for index, base in enumerate(base_dimensions):
            value = base * obj.scale[index]
            dimensions.append(round(float(value), 4))
        return dimensions

    def set_object_scale(self, name: str, scale: List[float]) -> None:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        obj.scale = [round(float(value), 4) for value in scale]

    def rotate_object(self, name: str, rotation_degrees: List[float]) -> None:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        obj.rotation_degrees = [round(float(value), 4) for value in rotation_degrees]

    def set_object_hidden(self, name: str, hidden: bool) -> None:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        obj.hidden = bool(hidden)

    def capture_view(
        self,
        capture_name: str,
        viewpoint: str = "front",
        object_name: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        if output_dir:
            capture_dir = Path(output_dir)
        else:
            capture_dir = Path.cwd() / "data" / "runtime" / "captures"
        capture_dir.mkdir(parents=True, exist_ok=True)
        capture_path = capture_dir / capture_name
        capture_path.write_bytes(b"simulated-capture")
        return str(capture_path)

    def delete_object(self, name: str) -> bool:
        existed = name in self.objects
        if not existed:
            return False
        del self.objects[name]
        if self.active_object_name == name:
            self.active_object_name = next(iter(self.objects), None)
        return True

    def duplicate_object(self, name: str, new_name: str) -> SimulatedObject:
        original = self.objects.get(name)
        if original is None:
            raise RuntimeError(f"Object does not exist: {name}")
        duplicate = copy.deepcopy(original)
        duplicate.name = new_name
        self.objects[new_name] = duplicate
        return duplicate

    def mirror_object(self, name: str, axis: str) -> SimulatedObject:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        axis_index = {"x": 0, "y": 1, "z": 2}.get(axis)
        if axis_index is None:
            raise RuntimeError(f"Invalid mirror axis: {axis}")
        obj.location[axis_index] = round(-obj.location[axis_index], 4)
        return obj

    def get_bbox_corners(self, name: str) -> List[List[float]]:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        hx, hy, hz = obj.scale
        x, y, z = obj.location
        corners = []
        for dx in (-hx, hx):
            for dy in (-hy, hy):
                for dz in (-hz, hz):
                    corners.append([round(x + dx, 4), round(y + dy, 4), round(z + dz, 4)])
        return corners

    def set_parent(self, child_name: str, parent_name: str) -> None:
        if child_name not in self.objects:
            raise RuntimeError(f"Child object does not exist: {child_name}")
        if parent_name not in self.objects:
            raise RuntimeError(f"Parent object does not exist: {parent_name}")
        self._parent_map[child_name] = parent_name

    def get_object_parent(self, name: str) -> Optional[str]:
        if name not in self.objects:
            raise RuntimeError(f"Object does not exist: {name}")
        return self._parent_map.get(name)

    def get_object_children(self, name: str) -> List[str]:
        if name not in self.objects:
            raise RuntimeError(f"Object does not exist: {name}")
        return [child for child, parent in self._parent_map.items() if parent == name]

    def get_object_location(self, name: str) -> List[float]:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        return list(obj.location)

    def get_object_rotation(self, name: str) -> List[float]:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        return list(obj.rotation_degrees)

    def get_object_scale(self, name: str) -> List[float]:
        obj = self.objects.get(name)
        if obj is None:
            raise RuntimeError(f"Object does not exist: {name}")
        return list(obj.scale)

    def create_collection(self, name: str) -> None:
        self._collections.add(name)

    def move_to_collection(self, object_name: str, collection_name: str) -> None:
        if object_name not in self.objects:
            raise RuntimeError(f"Object does not exist: {object_name}")
        if collection_name not in self._collections:
            raise RuntimeError(f"Collection does not exist: {collection_name}")
