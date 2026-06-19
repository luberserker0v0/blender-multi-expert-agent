"""Check that every referenced parent has at least one attachment point.

Plugin name: ``parent_has_attachment`` (quick, structural).

A parent name comes from a child's ``parent_name`` field.  The parent
part **must** define at least one attachment point so the child knows
where to attach.

This is a pure logic check — no manifest needed.
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity


class ParentHasAttachmentChecker:
    """Verify every parent referenced by a child has ≥ 1 attachment point."""

    name: str = "parent_has_attachment"
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

        # Build a set of parent names referenced by any child.
        parent_refs: set[str] = set()
        for part_name, part_spec in parts.items():
            parent = _get_parent_name(part_spec)
            if parent:
                parent_refs.add(parent)

        if not parent_refs:
            return violations

        # Check each referenced parent has at least one attachment point.
        for parent_name in sorted(parent_refs):
            parent_spec = parts.get(parent_name)
            if parent_spec is None:
                # A dangling reference — reported by NoOrphansPartsChecker.
                continue

            attachments = _get_attachments(parent_spec)
            if not attachments:
                violations.append(
                    ConstraintViolation(
                        rule=self.name,
                        detail=(
                            f"Parent part '{parent_name}' is referenced by "
                            f"a child but has no attachment points. "
                            f"At least one attachment point is required "
                            f"so the child can be placed correctly."
                        ),
                        severity=Severity.WARNING,
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


def _get_attachments(part_spec: Any) -> list[Any]:
    if isinstance(part_spec, dict):
        raw = part_spec.get("attachment_points", [])
    else:
        raw = getattr(part_spec, "attachment_points", None) or []
    if not isinstance(raw, list):
        return []
    return raw
