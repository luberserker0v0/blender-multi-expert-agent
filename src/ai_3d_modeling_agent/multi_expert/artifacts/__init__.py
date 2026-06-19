"""Artifact dataclass stubs for the multi-expert pipeline.

Each phase of the pipeline produces a typed dataclass artifact that
carries its output forward to the next phase.
"""

from __future__ import annotations

from .assembly import AssemblyArtifact
from .build import BuildArtifact
from .design import DesignArtifact
from .final import ConstraintViolation, FinalArtifact, PipelineStatus
from .plan import PlanArtifact
from .spec import SpecArtifact
from .validation import ValidationArtifact

__all__ = [
    "AssemblyArtifact",
    "BuildArtifact",
    "ConstraintViolation",
    "DesignArtifact",
    "FinalArtifact",
    "PipelineStatus",
    "PlanArtifact",
    "SpecArtifact",
    "ValidationArtifact",
]
