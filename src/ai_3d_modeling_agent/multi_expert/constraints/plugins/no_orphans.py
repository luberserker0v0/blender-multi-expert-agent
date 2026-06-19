"""Check the part hierarchy has exactly one root and no dangling references.

Plugin name: ``no_orphans`` (quick, structural).

Rules:
  1. Exactly one part has ``parent_name`` that is ``None`` / empty (the root).
  2. Every other part references a ``parent_name`` that exists in the
     parts table.

This is a pure logic check — no manifest needed.
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity


class NoOrphansPartsChecker:
    """Verify the part hierarchy has exactly one root and no orphans."""

    name: str = "no_orphans"
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

        part_names = set(parts.keys())

        # Find roots (parts with no parent) and collect parent refs.
        roots: list[str] = []
        parent_refs: set[str] = set()

        for part_name, part_spec in parts.items():
            parent = _get_parent_name(part_spec)
            if parent:
                parent_refs.add(parent)
            else:
                roots.append(part_name)

        # ── exactly one root ──────────────────────────────────────
        if len(roots) == 0:
            violations.append(
                ConstraintViolation(
                    rule=self.name,
                    detail=(
                        "No root part found.  Exactly one part must "
                        "have parent_name = None."
                    ),
                    severity=Severity.ERROR,
                )
            )
        elif len(roots) > 1:
            violations.append(
                ConstraintViolation(
                    rule=self.name,
                    detail=(
                        f"Multiple root parts found: {sorted(roots)}. "
                        f"Exactly one root is allowed."
                    ),
                    severity=Severity.ERROR,
                )
            )

        # ── dangling parent references ────────────────────────────
        dangling = parent_refs - part_names
        if dangling:
            violations.append(
                ConstraintViolation(
                    rule=self.name,
                    detail=(
                        f"Dangling parent reference(s): {sorted(dangling)}. "
                        f"Every parent_name must exist as a part key."
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
