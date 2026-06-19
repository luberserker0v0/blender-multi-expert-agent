"""Check that each attachment point's offset falls within its part's bbox.

Plugin name: ``attachment_in_bbox`` (quick, structural).

For each attachment point on every part, verify::

    |offset.x| <= bbox.width  / 2
    |offset.y| <= bbox.depth / 2
    |offset.z| <= bbox.height / 2
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity

_BBOX_DIMS = ("width", "depth", "height")
_OFFSET_KEYS = (0, 1, 2)  # index into the local_offset list [x, y, z]


class AttachmentInBboxChecker:
    """Verify each attachment point's local_offset is within the part bbox."""

    name: str = "attachment_in_bbox"
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
            bbox = _get_bbox(part_spec)
            if bbox is None:
                continue

            half = {dim: bbox[dim] / 2.0 for dim in _BBOX_DIMS}

            attachments = _get_attachments(part_spec)
            for ap in attachments:
                offset = _get_offset(ap)
                if offset is None:
                    continue

                checks = [
                    ("width", 0, _OFFSET_KEYS[0]),
                    ("depth", 1, _OFFSET_KEYS[1]),
                    ("height", 2, _OFFSET_KEYS[2]),
                ]
                for dim_name, dim_idx, _ in checks:
                    limit = half[dim_name]
                    if abs(offset[dim_idx]) > limit + 1e-9:
                        ap_name = _get_name(ap)
                        violations.append(
                            ConstraintViolation(
                                rule=self.name,
                                detail=(
                                    f"Part '{part_name}' attachment "
                                    f"'{ap_name}'.local_offset[{dim_idx}] "
                                    f"= {offset[dim_idx]:.4f} exceeds "
                                    f"bbox half-{dim_name} ({limit:.4f})."
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
    return result if len(result) == 3 else None


def _get_attachments(part_spec: Any) -> list[Any]:
    if isinstance(part_spec, dict):
        raw = part_spec.get("attachment_points", [])
    else:
        raw = getattr(part_spec, "attachment_points", None) or []
    if not isinstance(raw, list):
        return []
    return raw


def _get_offset(ap: Any) -> list[float] | None:
    raw: Any = None
    if isinstance(ap, dict):
        raw = ap.get("local_offset")
    else:
        raw = getattr(ap, "local_offset", None)
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    try:
        return [float(v) for v in raw]
    except (TypeError, ValueError):
        return None


def _get_name(ap: Any) -> str:
    if isinstance(ap, dict):
        return str(ap.get("name", "")).strip()
    return str(getattr(ap, "name", "")).strip()
