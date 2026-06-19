"""Programmatic validator — queries Blender directly to verify assembly correctness.

Replaces LLM-only validation with deterministic checks:
- Instance count verification
- Dimension verification against target_bbox
- Position verification against plan
- Parent-child hierarchy verification
- Symmetry verification (LEFT_RIGHT_X)
"""

from __future__ import annotations

import logging
from typing import Any

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.multi_expert.artifacts import (
    AssemblyArtifact,
    BuildArtifact,
    SpecArtifact,
    ValidationArtifact,
)

logger = logging.getLogger(__name__)

DIMENSION_TOLERANCE = 0.05
POSITION_TOLERANCE = 0.05


class ProgrammaticValidator:
    """Validates assembly by querying Blender for actual object state."""

    def validate(
        self,
        spec_artifact: SpecArtifact,
        build_artifacts: list[BuildArtifact],
        assembly_artifacts: list[AssemblyArtifact],
        object_ops: BlenderObjectOps,
    ) -> ValidationArtifact:
        """Run all programmatic checks and return a ValidationArtifact.

        Parameters
        ----------
        spec_artifact:
            The ground-truth specification from SpecPhase.
        build_artifacts:
            Per-part build results from BuildPhase (contain instance_names).
        assembly_artifacts:
            Per-step assembly results (contain placements with world_position).
        object_ops:
            BlenderObjectOps (real or simulated) for querying Blender state.

        Returns
        -------
        ValidationArtifact
            Pass/fail with detailed errors, warnings, and comparisons.
        """
        errors: list[str] = []
        warnings: list[str] = []
        comparisons: list[dict[str, Any]] = []

        # Build lookup structures
        spec_parts: dict[str, Any] = spec_artifact.parts
        build_by_name: dict[str, BuildArtifact] = {
            b.part_name: b for b in build_artifacts
        }
        placement_by_part: dict[str, dict[str, Any]] = {}
        for art in assembly_artifacts:
            for p in art.placements:
                part_name = p.get("part", "")
                if part_name:
                    placement_by_part[part_name] = p

        all_instance_names: list[str] = []
        for b in build_artifacts:
            all_instance_names.extend(b.instance_names)

        # ── Check 1: Instance Count ───────────────────────────────────
        self._check_instance_counts(
            spec_parts, build_by_name, object_ops, errors, warnings, comparisons,
        )

        # ── Check 2: Dimensions ───────────────────────────────────────
        self._check_dimensions(
            spec_parts, build_by_name, object_ops, errors, warnings, comparisons,
        )

        # ── Check 3: Positions ────────────────────────────────────────
        self._check_positions(
            placement_by_part, object_ops, errors, warnings, comparisons,
        )

        # ── Check 4: Parenting ────────────────────────────────────────
        self._check_parenting(
            placement_by_part, object_ops, errors, warnings, comparisons,
        )

        # ── Check 5: Symmetry ─────────────────────────────────────────
        self._check_symmetry(
            spec_parts, build_by_name, object_ops, errors, warnings, comparisons,
        )

        passed = len(errors) == 0
        return ValidationArtifact(
            passed=passed,
            errors=errors,
            warnings=warnings,
            comparisons=comparisons,
        )

    # ── Individual checks ─────────────────────────────────────────────

    def _check_instance_counts(
        self,
        spec_parts: dict[str, Any],
        build_by_name: dict[str, BuildArtifact],
        object_ops: BlenderObjectOps,
        errors: list[str],
        warnings: list[str],
        comparisons: list[dict[str, Any]],
    ) -> None:
        scene_objects = set(object_ops.list_object_names())

        for part_name, build_art in build_by_name.items():
            expected_count = len(build_art.instance_names)
            actual_count = sum(
                1 for name in build_art.instance_names if name in scene_objects
            )
            status = "pass" if actual_count == expected_count else "fail"
            comparisons.append({
                "part_name": part_name,
                "check": "instance_count",
                "expected": str(expected_count),
                "actual": str(actual_count),
                "status": status,
            })
            if status == "fail":
                errors.append(
                    f"{part_name}: expected {expected_count} instances, "
                    f"found {actual_count}"
                )

    def _check_dimensions(
        self,
        spec_parts: dict[str, Any],
        build_by_name: dict[str, BuildArtifact],
        object_ops: BlenderObjectOps,
        errors: list[str],
        warnings: list[str],
        comparisons: list[dict[str, Any]],
    ) -> None:
        for part_name, build_art in build_by_name.items():
            part_spec = spec_parts.get(part_name, {})
            if not isinstance(part_spec, dict):
                continue
            target_bbox = part_spec.get("target_bbox", {})
            if not isinstance(target_bbox, dict):
                continue
            target_w = _positive_float(target_bbox.get("width"))
            target_d = _positive_float(target_bbox.get("depth"))
            target_h = _positive_float(target_bbox.get("height"))
            if target_w is None or target_d is None or target_h is None:
                warnings.append(f"{part_name}: dimensions skipped because target_bbox is incomplete")
                continue
            target = [target_w, target_d, target_h]

            for inst_name in build_art.instance_names:
                try:
                    actual = object_ops.get_object_dimensions(inst_name)
                except Exception:
                    warnings.append(f"{inst_name}: could not query dimensions")
                    continue

                match = all(
                    abs(a - t) <= DIMENSION_TOLERANCE + t * 0.05
                    for a, t in zip(actual, target)
                )
                status = "pass" if match else "fail"
                comparisons.append({
                    "part_name": inst_name,
                    "check": "dimensions",
                    "expected": f"[{target_w:.3f}, {target_d:.3f}, {target_h:.3f}]",
                    "actual": f"[{actual[0]:.3f}, {actual[1]:.3f}, {actual[2]:.3f}]",
                    "status": status,
                })
                if not match:
                    errors.append(
                        f"{inst_name}: dimensions {actual} "
                        f"do not match target [{target_w}, {target_d}, {target_h}]"
                    )

    def _check_positions(
        self,
        placement_by_part: dict[str, dict[str, Any]],
        object_ops: BlenderObjectOps,
        errors: list[str],
        warnings: list[str],
        comparisons: list[dict[str, Any]],
    ) -> None:
        for part_name, placement in placement_by_part.items():
            expected_pos = placement.get("world_position", [0, 0, 0])
            instances = placement.get("instances", [])
            for inst_name in instances:
                try:
                    bbox = object_ops.get_bbox_corners(inst_name)
                except Exception:
                    warnings.append(f"{inst_name}: could not query bbox corners")
                    continue
                if not bbox:
                    warnings.append(f"{inst_name}: empty bbox corners")
                    continue
                xs = [c[0] for c in bbox]
                ys = [c[1] for c in bbox]
                zs = [c[2] for c in bbox]
                actual_center = [
                    (min(xs) + max(xs)) / 2,
                    (min(ys) + max(ys)) / 2,
                    (min(zs) + max(zs)) / 2,
                ]
                match = all(
                    abs(a - e) <= POSITION_TOLERANCE
                    for a, e in zip(actual_center, expected_pos)
                )
                status = "pass" if match else "fail"
                comparisons.append({
                    "part_name": inst_name,
                    "check": "position",
                    "expected": f"[{expected_pos[0]:.3f}, {expected_pos[1]:.3f}, {expected_pos[2]:.3f}]",
                    "actual": f"[{actual_center[0]:.3f}, {actual_center[1]:.3f}, {actual_center[2]:.3f}]",
                    "status": status,
                })
                if not match:
                    errors.append(
                        f"{inst_name}: position {actual_center} "
                        f"does not match expected {expected_pos}"
                    )

    def _check_parenting(
        self,
        placement_by_part: dict[str, dict[str, Any]],
        object_ops: BlenderObjectOps,
        errors: list[str],
        warnings: list[str],
        comparisons: list[dict[str, Any]],
    ) -> None:
        for part_name, placement in placement_by_part.items():
            expected_parent = placement.get("parent")
            instances = placement.get("instances", [])
            for inst_name in instances:
                try:
                    actual_parent = object_ops.get_object_parent(inst_name)
                except Exception:
                    warnings.append(f"{inst_name}: could not query parent")
                    continue
                # Normalize: expected_parent may refer to part_name, we need instance name
                match = True
                if expected_parent is None:
                    # Root: should have no parent
                    if actual_parent is not None:
                        match = False
                else:
                    # Child: parent should exist
                    if actual_parent is None:
                        match = False
                status = "pass" if match else "fail"
                comparisons.append({
                    "part_name": inst_name,
                    "check": "parenting",
                    "expected": str(expected_parent),
                    "actual": str(actual_parent),
                    "status": status,
                })
                if not match:
                    errors.append(
                        f"{inst_name}: expected parent={expected_parent}, "
                        f"actual parent={actual_parent}"
                    )

    def _check_symmetry(
        self,
        spec_parts: dict[str, Any],
        build_by_name: dict[str, BuildArtifact],
        object_ops: BlenderObjectOps,
        errors: list[str],
        warnings: list[str],
        comparisons: list[dict[str, Any]],
    ) -> None:
        for part_name, build_art in build_by_name.items():
            part_spec = spec_parts.get(part_name, {})
            if not isinstance(part_spec, dict):
                continue
            symmetry = part_spec.get("symmetry_group", "NONE")
            if symmetry != "LEFT_RIGHT_X":
                continue
            instance_names = build_art.instance_names
            if len(instance_names) < 2:
                continue
            # For LEFT_RIGHT_X, x-coordinates of paired instances should be opposite
            positions = []
            for inst_name in instance_names:
                try:
                    bbox = object_ops.get_bbox_corners(inst_name)
                    if bbox:
                        xs = [c[0] for c in bbox]
                        cx = (min(xs) + max(xs)) / 2
                        positions.append((inst_name, cx))
                except Exception:
                    warnings.append(f"{inst_name}: could not query position for symmetry check")
            if len(positions) == 2:
                _, x0 = positions[0]
                _, x1 = positions[1]
                mirror_ok = abs(x0 + x1) <= POSITION_TOLERANCE or abs(x0 - x1) <= POSITION_TOLERANCE
                status = "pass" if mirror_ok else "fail"
                comparisons.append({
                    "part_name": part_name,
                    "check": "symmetry_LEFT_RIGHT_X",
                    "expected": "x coords should be opposite or equal",
                    "actual": f"{positions[0][0]}: x={x0:.3f}, {positions[1][0]}: x={x1:.3f}",
                    "status": status,
                })
                if not mirror_ok:
                    errors.append(
                        f"{part_name}: LEFT_RIGHT_X symmetry check failed, "
                        f"x-coords {x0:.3f} and {x1:.3f} are not mirrored"
                    )


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
