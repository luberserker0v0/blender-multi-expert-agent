"""Build phase artifact — output of the Builder expert.

Domain: per-part build result including capture paths, refinement
iterations, and final status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class BuildArtifact:
    """Build phase output for a single part family.

    Produced by the Builder expert for each part in the plan. Captures the
    build outcome, all refinement iterations, and any failures.
    """

    part_name: str = ""
    """Name of the part family this artifact represents."""

    source_object_name: str = ""
    """The base mesh object name in Blender (before instancing)."""

    instance_names: list[str] = field(default_factory=list)
    """Object names of each instance in the Blender scene."""

    status: Literal["built", "failed", "skipped", "blocked", "needs_revision"] = "built"
    """Outcome of the build operation for this part."""

    capture_paths: list[str] = field(default_factory=list)
    """Paths to screenshot captures taken during refinement rounds."""

    refinement_rounds: int = 0
    """Number of refinement iterations performed."""

    action_history: list[dict[str, Any]] = field(default_factory=list)
    """Record of all Blender actions executed during build."""

    responsibility_refs: list[str] = field(default_factory=list)
    """Planning responsibility refs consumed while building this part."""

    constraint_refs: list[str] = field(default_factory=list)
    """Planning constraint refs consulted during build execution."""

    planning_warnings: list[str] = field(default_factory=list)
    """Capability-boundary warnings or fallback notes raised during plan consumption."""

    failure_notes: list[str] = field(default_factory=list)
    """Non-empty only when partial recovery occurred."""
