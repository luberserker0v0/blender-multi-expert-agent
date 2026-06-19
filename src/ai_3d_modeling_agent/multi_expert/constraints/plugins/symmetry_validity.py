"""Check instance_count / symmetry_group compatibility.

Plugin name: ``symmetry_validity`` (quick, structural).

Compatibility rules:

  - ``NONE``: any instance_count is acceptable.
  - ``LEFT_RIGHT_X`` / ``LEFT_RIGHT_Y``: even count ≥ 2.
  - ``QUADRANT_Z`` / ``RADIAL_4_Z``: count == 4.

This is a pure logic check — no manifest needed.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..violations import ConstraintViolation, Severity


class SymmetryGroup(str, Enum):
    """Mirror / radial symmetry options recognised by the pipeline."""

    NONE = "NONE"
    LEFT_RIGHT_X = "LEFT_RIGHT_X"
    LEFT_RIGHT_Y = "LEFT_RIGHT_Y"
    QUADRANT_Z = "QUADRANT_Z"
    RADIAL_4_Z = "RADIAL_4_Z"


class SymmetryValidityChecker:
    """Verify each part's instance_count is compatible with its symmetry_group."""

    name: str = "symmetry_validity"
    quick: bool = True

    def check(
        self,
        artifact: Any,
        manifests: Any | None = None,
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        parts = _get_parts(artifact)

        if not parts:
            return violations

        for part_name, part_spec in parts.items():
            symmetry = _get_symmetry_group(part_spec)
            count = _get_instance_count(part_spec)

            if symmetry is None or symmetry == SymmetryGroup.NONE:
                continue

            violation = _check_compatibility(symmetry, count, part_name)
            if violation is not None:
                violations.append(violation)

        return violations


# ── helpers ───────────────────────────────────────────────────────────

def _get_parts(artifact: Any) -> dict[str, Any]:
    if isinstance(artifact, dict):
        raw = artifact.get("parts") or {}
        return raw if isinstance(raw, dict) else {}
    raw = getattr(artifact, "parts", None) or {}
    return raw if isinstance(raw, dict) else {}


def _get_symmetry_group(part_spec: Any) -> SymmetryGroup | None:
    raw: Any = None
    if isinstance(part_spec, dict):
        raw = part_spec.get("symmetry_group")
    else:
        raw = getattr(part_spec, "symmetry_group", None)
    if raw is None:
        return None
    try:
        return SymmetryGroup(str(raw).strip().upper())
    except ValueError:
        return None


def _get_instance_count(part_spec: Any) -> int:
    if isinstance(part_spec, dict):
        raw = part_spec.get("instance_count", 1)
    else:
        raw = getattr(part_spec, "instance_count", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _check_compatibility(
    symmetry: SymmetryGroup,
    count: int,
    part_name: str,
) -> ConstraintViolation | None:
    if symmetry in (SymmetryGroup.LEFT_RIGHT_X, SymmetryGroup.LEFT_RIGHT_Y):
        if count < 2 or count % 2 != 0:
            return ConstraintViolation(
                rule="symmetry_validity",
                detail=(
                    f"Part '{part_name}' has symmetry_group="
                    f"{symmetry.value} but instance_count={count}. "
                    f"Expected an even number ≥ 2."
                ),
                severity=Severity.ERROR,
            )

    elif symmetry in (SymmetryGroup.QUADRANT_Z, SymmetryGroup.RADIAL_4_Z):
        if count != 4:
            return ConstraintViolation(
                rule="symmetry_validity",
                detail=(
                    f"Part '{part_name}' has symmetry_group="
                    f"{symmetry.value} but instance_count={count}. "
                    f"Expected exactly 4."
                ),
                severity=Severity.ERROR,
            )

    return None
