"""Check that every part primitive is in the manifest's supported set.

Plugin name: ``primitive_supported`` (quick, structural).
"""

from __future__ import annotations

from typing import Any

from ..violations import ConstraintViolation, Severity

# Default set used when the manifest provides no override.
_DEFAULT_SUPPORTED = {"cube", "uv_sphere", "cylinder", "plane"}


class PrimitiveSupportedChecker:
    """Verify all part primitives are supported by the manifest.

    The manifest should provide ``supported_primitives`` as a list of
    strings.  When the manifest is ``None`` or lacks this key the
    built-in default set (cube, uv_sphere, cylinder, plane) is used.
    """

    name: str = "primitive_supported"
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

        supported = _resolve_supported(manifests)

        for part_name, part_spec in parts.items():
            primitive = _get_str_field(part_spec, "primitive")
            if not primitive:
                continue  # skip parts without a primitive field
            if primitive.lower() not in supported:
                violations.append(
                    ConstraintViolation(
                        rule=self.name,
                        detail=(
                            f"Part '{part_name}' uses primitive "
                            f"'{primitive}' which is not in the "
                            f"supported set: {sorted(supported)}."
                        ),
                        severity=Severity.ERROR,
                    )
                )

        return violations


# ── helpers ───────────────────────────────────────────────────────────

def _get_parts(artifact: Any) -> dict[str, Any]:
    """Extract the parts mapping from *artifact* (object or dict)."""
    if isinstance(artifact, dict):
        raw = artifact.get("parts") or {}
        if isinstance(raw, dict):
            return raw
        return {}
    raw = getattr(artifact, "parts", None) or {}
    if isinstance(raw, dict):
        return raw
    return {}


def _get_str_field(obj: Any, field: str) -> str:
    """Extract *field* from *obj* (dict or object) as a stripped string."""
    if isinstance(obj, dict):
        val = obj.get(field, "")
    else:
        val = getattr(obj, field, "")
    return str(val).strip()


def _resolve_supported(manifests: Any) -> set[str]:
    """Return the supported primitive set from *manifests* or the default."""
    if manifests is None:
        return _DEFAULT_SUPPORTED

    raw: list[str] | None = None
    if isinstance(manifests, dict):
        raw = manifests.get("supported_primitives")
    else:
        raw = getattr(manifests, "supported_primitives", None)

    if not raw:
        return _DEFAULT_SUPPORTED

    return {str(p).strip().lower() for p in raw if p}
