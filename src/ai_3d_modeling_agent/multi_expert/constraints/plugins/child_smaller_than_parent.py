"""Check that every child is smaller than its parent in at least one dimension.

Plugin name: ``child_smaller_than_parent`` (quick, structural).

A child must be strictly **smaller** than its parent in at least one of
the three bbox dimensions (width, depth, height).  A tolerance of 5 %
is applied — the child can be up to 5 % larger before a violation is
raised.

A child larger or equal to the parent in **all** dimensions triggers an
ERROR.

This is a pure logic check — no manifest needed.
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity

_BBOX_DIMS = ("width", "depth", "height")
_TOLERANCE = 1.05  # 5 % margin


class ChildSmallerThanParentChecker:
    """Verify each child is smaller than its parent in at least one dimension."""

    name: str = "child_smaller_than_parent"
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
            parent_name = _get_parent_name(part_spec)
            if not parent_name or parent_name not in parts:
                continue

            child_bbox = _get_bbox(part_spec)
            parent_bbox = _get_bbox(parts[parent_name])

            if child_bbox is None or parent_bbox is None:
                continue

            smaller_dims = 0
            for dim in _BBOX_DIMS:
                child_val = child_bbox.get(dim)
                parent_val = parent_bbox.get(dim)
                if child_val is None or parent_val is None:
                    continue
                if child_val <= parent_val * _TOLERANCE:
                    smaller_dims += 1

            if smaller_dims == 0:
                violations.append(
                    ConstraintViolation(
                        rule=self.name,
                        detail=(
                            f"Part '{part_name}' ({_fmt_bbox(child_bbox)}) "
                            f"is NOT smaller than parent '{parent_name}' "
                            f"({_fmt_bbox(parent_bbox)}) in any dimension. "
                            f"Child must be smaller than parent in at "
                            f"least one dimension."
                        ),
                        severity=Severity.ERROR,
                    )
                )

        return violations


# ── helpers ───────────────────────────────────────────────────────────

def _get_parts(artifact: Any) -> dict[str, Any]:
    if isinstance(artifact, dict):
        raw = artifact.get("parts") or {}
        return raw if isinstance(raw, dict) else {}
    raw = getattr(artifact, "parts", None) or {}
    return raw if isinstance(raw, dict) else {}


def _get_parent_name(part_spec: Any) -> str | None:
    if isinstance(part_spec, dict):
        val = part_spec.get("parent_name")
    else:
        val = getattr(part_spec, "parent_name", None)
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _get_bbox(part_spec: Any) -> dict[str, float] | None:
    raw: Any = None
    if isinstance(part_spec, dict):
        raw = part_spec.get("target_bbox")
    else:
        raw = getattr(part_spec, "target_bbox", None)
    if raw is None or not isinstance(raw, dict):
        return None
    result: dict[str, float] = {}
    for dim in _BBOX_DIMS:
        v = raw.get(dim)
        if v is not None:
            try:
                result[dim] = float(v)
            except (TypeError, ValueError):
                pass
    return result if result else None


def _fmt_bbox(bbox: dict[str, float]) -> str:
    w = bbox.get("width", "?")
    d = bbox.get("depth", "?")
    h = bbox.get("height", "?")
    return f"W={w} D={d} H={h}"
