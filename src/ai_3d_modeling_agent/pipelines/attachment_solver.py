"""Pure-math attachment solver for the D&C pipeline.

Transforms local attachment point offsets declared by the LLM into
world-space positions, rotations, and scales.  No LLM calls involved —
every placement is computed deterministically.

Key idea
--------
The LLM only declares *local* offsets (e.g. "the legs attach at the
bottom_center of the seat").  The solver handles all coordinate math:

    1.  Compute the parent's attachment point in world space
        (accounting for parent rotation & scale).
    2.  Place the child so its own attachment point aligns with that
        world-space point.
    3.  Apply symmetry transformations (mirror / rotate) for multi-
        instance families.
"""

import logging
import math
from typing import List, Tuple

from ai_3d_modeling_agent.schemas.part import SymmetryGroup

logger = logging.getLogger(__name__)


# Type alias: a 3-element vector represented as a plain list.
Vec3 = List[float]


# ── public API ───────────────────────────────────────────────────────


def solve_placement(
    parent_world_position: Vec3,
    parent_world_rotation_degrees: Vec3,
    parent_world_scale: Vec3,
    parent_attachment_local: Vec3,
    child_attachment_local: Vec3,
    child_world_scale: Vec3,
    symmetry: SymmetryGroup,
    instance_index: int,  # 1-based
) -> Tuple[Vec3, Vec3, Vec3]:
    """Compute world-space (position, rotation_degrees, scale) for a child instance.

    Parameters
    ----------
    parent_world_position:
        World-space [x, y, z] of the parent's centre.
    parent_world_rotation_degrees:
        Euler [rx, ry, rz] in **degrees**, applied in XYZ order.
    parent_world_scale:
        World-space [sx, sy, sz] of the parent.
    parent_attachment_local:
        Local offset from the parent's centre where the child attaches.
    child_attachment_local:
        Local offset from the child's centre that should align with the
        parent's attachment point.
    child_world_scale:
        World-space [sx, sy, sz] of the child (typically its ``target_bbox``).
    symmetry:
        Symmetry group for multi-instance families.
    instance_index:
        1-based index within the part family.

    Returns
    -------
    (world_position, world_rotation_degrees, world_scale)
        The placement values to apply in Blender.
    """
    # ── Step 1: parent attachment point in world space ───────────────
    rot_m = _euler_to_matrix(parent_world_rotation_degrees)
    # Attachment offsets from the LLM are in physical meters (same unit
    # as target_bbox).  Do NOT multiply by parent_world_scale — that
    # would double-scale and place children near the origin.
    parent_attachment_world = _vec_add(
        parent_world_position, _mat_vec_mul(rot_m, parent_attachment_local)
    )

    # ── Step 2: child position so its attachment meets parent ────────
    child_position = _vec_sub(
        parent_attachment_world, child_attachment_local
    )

    # ── Step 3: symmetry transformation ──────────────────────────────
    rotation = [0.0, 0.0, 0.0]

    if symmetry in (SymmetryGroup.QUADRANT_Z, SymmetryGroup.RADIAL_4_Z):
        angle_deg = 90.0 * float(instance_index - 1)
        rotation[2] = angle_deg
        child_position = _rotate_point_around_z(child_position, angle_deg)

    elif symmetry == SymmetryGroup.LEFT_RIGHT_X:
        if instance_index % 2 == 0:
            # Mirror attachment point (swap left_face ↔ right_face)
            mirrored_attachment = list(child_attachment_local)
            mirrored_attachment[0] *= -1.0
            child_position = _vec_sub(parent_attachment_world, mirrored_attachment)

    elif symmetry == SymmetryGroup.LEFT_RIGHT_Y:
        if instance_index % 2 == 0:
            # Mirror attachment point (swap front_face ↔ back_face)
            mirrored_attachment = list(child_attachment_local)
            mirrored_attachment[1] *= -1.0
            child_position = _vec_sub(parent_attachment_world, mirrored_attachment)

    # SymmetryGroup.NONE: no transformation.

    # ── Step 4: symmetry fallback (zero-offset on the relevant axis) ──
    if symmetry in (SymmetryGroup.QUADRANT_Z, SymmetryGroup.RADIAL_4_Z):
        if abs(child_position[0]) < 1e-9 and abs(child_position[1]) < 1e-9:
            half_w = parent_world_scale[0] / 2.0
            half_d = parent_world_scale[1] / 2.0
            if instance_index == 1:
                child_position[:2] = [ half_w,  half_d]
            elif instance_index == 2:
                child_position[:2] = [-half_w,  half_d]
            elif instance_index == 3:
                child_position[:2] = [-half_w, -half_d]
            elif instance_index == 4:
                child_position[:2] = [ half_w, -half_d]
            logger.warning("Symmetry fallback: QUADRANT_Z child at origin, spreading XY")

    if symmetry == SymmetryGroup.LEFT_RIGHT_X:
        if abs(child_attachment_local[0]) < 1e-9:
            half_w = child_world_scale[0] / 2.0
            if instance_index % 2 == 0:
                child_position[0] = -half_w
            else:
                child_position[0] = half_w
            logger.warning("Symmetry fallback: LEFT_RIGHT_X child at origin, injecting X offset")

    if symmetry == SymmetryGroup.LEFT_RIGHT_Y:
        if abs(child_attachment_local[1]) < 1e-9:
            half_d = child_world_scale[1] / 2.0
            if instance_index % 2 == 0:
                child_position[1] = -half_d
            else:
                child_position[1] = half_d
            logger.warning("Symmetry fallback: LEFT_RIGHT_Y child at origin, injecting Y offset")

    return child_position, rotation, list(child_world_scale)


def solve_root_placement(target_bbox: Vec3) -> Tuple[Vec3, Vec3, Vec3]:
    """Return the placement for the root part (always centred at origin)."""
    return ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0], list(target_bbox))


# ── internal helpers ─────────────────────────────────────────────────


def _euler_to_matrix(euler_degrees: Vec3) -> List[List[float]]:
    """Build a 3×3 rotation matrix from Euler angles (degrees, XYZ order).

    This uses the common (Rx @ Ry @ Rz) convention.
    """
    rx = math.radians(euler_degrees[0])
    ry = math.radians(euler_degrees[1])
    rz = math.radians(euler_degrees[2])

    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # R = Rz @ Ry @ Rx
    return [
        [cy * cz, cz * sx * sy - cx * sz, cx * cz * sy + sx * sz],
        [cy * sz, cx * cz + sx * sy * sz, -cz * sx + cx * sy * sz],
        [-sy, cy * sx, cx * cy],
    ]


def _mat_vec_mul(mat: List[List[float]], vec: Vec3) -> Vec3:
    """3×3 matrix × 3-vector multiplication."""
    return [
        mat[0][0] * vec[0] + mat[0][1] * vec[1] + mat[0][2] * vec[2],
        mat[1][0] * vec[0] + mat[1][1] * vec[1] + mat[1][2] * vec[2],
        mat[2][0] * vec[0] + mat[2][1] * vec[1] + mat[2][2] * vec[2],
    ]


def _rotate_point_around_z(point: Vec3, angle_degrees: float) -> Vec3:
    """Rotate a 3D point around the Z axis by *angle_degrees*."""
    rad = math.radians(angle_degrees)
    c, s = math.cos(rad), math.sin(rad)
    x = point[0] * c - point[1] * s
    y = point[0] * s + point[1] * c
    return [x, y, point[2]]


def _vec_add(a: Vec3, b: Vec3) -> Vec3:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _vec_sub(a: Vec3, b: Vec3) -> Vec3:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _vec_mul(a: Vec3, b: Vec3) -> Vec3:
    """Element-wise multiplication (Hadamard product)."""
    return [a[0] * b[0], a[1] * b[1], a[2] * b[2]]


# ── higher-level convenience ─────────────────────────────────────────


def compute_attachment_world_position(
    parent_world_position: Vec3,
    parent_world_rotation_degrees: Vec3,
    parent_world_scale: Vec3,
    attachment_local_offset: Vec3,
) -> Vec3:
    """Compute the world-space coordinates of an attachment point.

    *attachment_local_offset* is in physical meters (same unit as
    ``target_bbox``), not in object-local unit coordinates.  The
    *parent_world_scale* parameter is retained for API compatibility
    but is NOT used in the computation (see ``solve_placement``).
    """
    rot_m = _euler_to_matrix(parent_world_rotation_degrees)
    return _vec_add(parent_world_position, _mat_vec_mul(rot_m, attachment_local_offset))
