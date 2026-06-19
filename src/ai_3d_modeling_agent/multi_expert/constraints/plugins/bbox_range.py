"""Check that bounding-box dimensions are within manifest-defined ranges.

Plugin name: ``bbox_range`` (quick, structural).

Default range: width, depth, height ∈ [0.001, 100.0] metres.
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity

_DEFAULT_MIN = {"width": 0.001, "depth": 0.001, "height": 0.001}
_DEFAULT_MAX = {"width": 100.0, "depth": 100.0, "height": 100.0}
_BBOX_DIMS = ("width", "depth", "height")


class BboxRangeChecker:
    """Verify each part's ``target_bbox`` is within the configured range.

    The manifest may provide ``min_bbox`` and ``max_bbox`` dicts with
    keys ``width``, ``depth``, ``height``.  Missing keys fall back to
    the default range.
    """

    name: str = "bbox_range"
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

        min_bbox, max_bbox = _resolve_ranges(manifests)

        for part_name, part_spec in parts.items():
            bbox = _get_bbox(part_spec)
            if bbox is None:
                continue

            for dim in _BBOX_DIMS:
                val = bbox.get(dim)
                if val is None:
                    continue

                lo = min_bbox.get(dim, _DEFAULT_MIN[dim])
                hi = max_bbox.get(dim, _DEFAULT_MAX[dim])

                if val < lo - 1e-9:
                    violations.append(
                        ConstraintViolation(
                            rule=self.name,
                            detail=(
                                f"Part '{part_name}'.target_bbox.{dim} = "
                                f"{val} is below minimum {lo}."
                            ),
                            severity=Severity.ERROR,
                        )
                    )
                elif val > hi + 1e-9:
                    violations.append(
                        ConstraintViolation(
                            rule=self.name,
                            detail=(
                                f"Part '{part_name}'.target_bbox.{dim} = "
                                f"{val} exceeds maximum {hi}."
                            ),
                            severity=Severity.ERROR,
                        )
                    )

        return violations


# ── helpers ───────────────────────────────────────────────────────────

def _get_parts(artifact: Any) -> dict[str, Any]:
    """Extract parts from *artifact* (object or dict)."""
    if isinstance(artifact, dict):
        raw = artifact.get("parts") or {}
        return raw if isinstance(raw, dict) else {}
    raw = getattr(artifact, "parts", None) or {}
    return raw if isinstance(raw, dict) else {}


def _get_bbox(part_spec: Any) -> dict[str, float] | None:
    """Extract ``target_bbox`` from a part spec (dict or object)."""
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


def _resolve_ranges(
    manifests: Any,
) -> tuple[dict[str, float], dict[str, float]]:
    """Return (min_bbox, max_bbox) dicts from *manifests* or defaults."""
    if manifests is None:
        return dict(_DEFAULT_MIN), dict(_DEFAULT_MAX)

    if isinstance(manifests, dict):
        raw_min = manifests.get("min_bbox", {})
        raw_max = manifests.get("max_bbox", {})
    else:
        raw_min = getattr(manifests, "min_bbox", None) or {}
        raw_max = getattr(manifests, "max_bbox", None) or {}

    min_b = {}
    max_b = {}
    for dim in _BBOX_DIMS:
        lo = raw_min.get(dim) if isinstance(raw_min, dict) else _DEFAULT_MIN[dim]
        hi = raw_max.get(dim) if isinstance(raw_max, dict) else _DEFAULT_MAX[dim]
        try:
            min_b[dim] = float(lo) if lo is not None else _DEFAULT_MIN[dim]
        except (TypeError, ValueError):
            min_b[dim] = _DEFAULT_MIN[dim]
        try:
            max_b[dim] = float(hi) if hi is not None else _DEFAULT_MAX[dim]
        except (TypeError, ValueError):
            max_b[dim] = _DEFAULT_MAX[dim]

    return min_b, max_b
