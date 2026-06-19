"""Specification phase artifact — output of the Specifier expert.

Domain: precise geometric specification for each part family, including
bounding boxes, primitives, and attachment points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpecArtifact:
    """Specification phase output — precise part specs with validation notes.

    Produced by the Specifier expert from a DesignArtifact. Resolves all
    ambiguous or underspecified fields left by the Designer.
    """

    blueprint_id: str = ""
    """Unique identifier for this specification blueprint."""

    version: int = 1
    """Bumped on each revision cycle."""

    depends_on_artifact: str = "design"
    """Upstream artifact name this spec was built from."""

    depends_on_version: int = 1
    """Version of the design artifact this spec was built from."""

    compatible_versions: range = range(1, 2)
    """Valid upstream version range for compatibility checking."""

    parts: dict[str, Any] = field(default_factory=dict)
    point_registry: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    """Part specs keyed by part name — each value is a PartSpec dict."""

    validation_notes: list[str] = field(default_factory=list)
    """Records all changes from DesignArtifact (e.g. bbox adjustments)."""

    summary: str = ""
    """Summary set by convener.extract()."""

    failure_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "blueprint_id": self.blueprint_id,
            "version": self.version,
            "depends_on_artifact": self.depends_on_artifact,
            "depends_on_version": self.depends_on_version,
            "compatible_versions": [self.compatible_versions.start, self.compatible_versions.stop],
            "parts": self.parts,
            "point_registry": self.point_registry,
            "validation_notes": list(self.validation_notes),
            "summary": self.summary,
            "failure_notes": list(self.failure_notes),
        }
    """Non-empty only when partial recovery occurred."""
