"""Final pipeline artifact — aggregate of all phase outputs.

Domain: top-level pipeline result including status, degradation tracking,
and references to all phase artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .assembly import AssemblyArtifact
from .build import BuildArtifact
from .design import DesignArtifact
from .plan import PlanArtifact
from .spec import SpecArtifact
from .validation import ValidationArtifact


class PipelineStatus(str, Enum):
    """Overall pipeline outcome status.

    Reflects the cumulative result of all phases and any degradation
    or failure recovery that occurred during execution.
    """

    SUCCESS = "SUCCESS"
    """All phases completed without degradation."""
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    """All phases completed, but warnings were overridden by user."""
    DEGRADED = "DEGRADED"
    """Pipeline completed but some phases used DEGRADE fallback."""
    PARTIAL = "PARTIAL"
    """Pipeline completed but some artifacts are partial."""
    FAILED = "FAILED"
    """Pipeline aborted due to a FATAL error."""


@dataclass
class ConstraintViolation:
    """A constraint violation record for user override tracking.

    Documents a specification or policy violation that was detected and
    optionally overridden by the user.
    """

    rule: str = ""
    """The constraint or rule that was violated."""
    detail: str = ""
    """Human-readable description of the violation."""
    overridden: bool = False
    """Whether the user explicitly overrode this violation."""


@dataclass
class FinalArtifact:
    """Top-level pipeline result aggregating all phase outputs.

    Produced by the Convener after all pipeline phases complete. Carries
    the overall status, per-phase artifacts, and degradation metadata.
    """

    task_prompt: str = ""
    """The original task prompt that initiated the pipeline."""

    design: DesignArtifact | None = None
    """Output of the Designer phase."""

    specs: SpecArtifact | None = None
    """Output of the Specifier phase."""

    plan: PlanArtifact | None = None
    """Output of the Architect phase."""

    build_results: dict[str, BuildArtifact] = field(default_factory=dict)
    """BuildArtifacts keyed by part name — output of the Builder phase."""

    assembly_results: list[AssemblyArtifact] = field(default_factory=list)
    """AssemblyArtifacts — output of the Assembler phase, one per step."""

    validation: ValidationArtifact | None = None
    """Output of the Inspector phase."""

    conversation_id: str = ""
    """Links this artifact to the parent conversation."""

    status: PipelineStatus = PipelineStatus.FAILED
    """Overall pipeline outcome status."""

    degraded_parts: list[str] = field(default_factory=list)
    """Parts that fell back to DEGRADE policy."""

    overridden_violations: list[ConstraintViolation] = field(default_factory=list)
    """Constraint violations that were explicitly overridden by the user."""

    phase_statuses: dict[str, PipelineStatus] = field(default_factory=dict)
    """Per-phase status keyed by phase name."""

    revision_count: int = 0
    """Total number of revision cycles used across all phases."""
