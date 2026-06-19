"""Assembly phase artifact — output of the Assembler expert.

Domain: per-step assembly results with placement data and review verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssemblyArtifact:
    """Assembly phase output for a single assembly step.

    Produced by the Assembler expert for each step in the plan. Contains
    the actual placements executed and the review verdict.
    """

    step_index: int = 0
    """Index of this step in the assembly sequence."""

    placements: list[dict[str, Any]] = field(default_factory=list)
    """InstancePlacement dicts for each part placed in this step."""

    responsibility_refs: list[str] = field(default_factory=list)
    """Planning responsibility refs consumed while assembling this step."""

    constraint_refs: list[str] = field(default_factory=list)
    """Ordering constraint refs consulted during assembly execution."""

    planning_warnings: list[str] = field(default_factory=list)
    """Capability-boundary warnings or fallback notes raised during plan consumption."""

    planning_failures: list[str] = field(default_factory=list)
    """Blocking planning/execution issues that prevented faithful assembly."""

    resolved_parent: str | None = None
    """Resolved parent that the assembler actually used, if any."""

    resolved_world_position: list[float] | None = None
    """Resolved world position that the assembler actually used, if any."""

    skipped: bool = False
    """Whether this step was skipped because assembly contract resolution failed."""

    unresolved_planning_gap: bool = False
    """Whether unresolved contract gaps prevented execution."""

    missing_contract_fields: list[str] = field(default_factory=list)
    """Blocking contract fields that were still missing when assembly ran."""

    fallback_used: bool = False
    """Whether execution fell back to legacy step/world-position behavior."""

    action_history: list[dict[str, Any]] = field(default_factory=list)
    """Record of all Blender actions executed during this assembly step."""

    review_verdict: str | None = None
    """Optional verdict from the review pass (e.g. 'approved', 'needs_adjustment')."""

    failure_notes: list[str] = field(default_factory=list)
    """Non-empty only when partial recovery occurred."""
