"""Design phase artifact — output of the Designer expert.

Domain: the task-level decomposition into part families, including
assembly concept and unresolved issues for downstream phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DesignArtifact:
    """Design phase output — part family decomposition and assembly concept.

    Produced by the Designer expert from the raw task prompt. Contains the
    list of proposed parts, their relationships, and a high-level assembly
    strategy. Passed to the Specifier for detailed specification.
    """

    task_prompt: str = ""
    """The original task prompt that drove this design."""

    timestamp: datetime | None = None
    """When this artifact was created."""

    parts: list[dict[str, Any]] = field(default_factory=list)
    """Part family blueprints — each entry is a PartFamilyBlueprint dict."""

    assembly_concept: str = ""
    """High-level assembly approach (NL description)."""

    unresolved_issues: list[str] = field(default_factory=list)
    """Issues the designer could not resolve — passed to Specifier."""

    summary: str = ""
    """Concise summary set by convener.extract() — used in FocusedMeetingContext."""

    failure_notes: list[str] = field(default_factory=list)
    """Non-empty only when partial recovery occurred."""
