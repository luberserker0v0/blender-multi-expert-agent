"""Constraint validation system for the multi-expert pipeline.

Provides the ``ConstraintChecker`` orchestrator and 7 built-in
validation plugins that enforce structural, geometric, and logical
constraints on pipeline artifacts.

Typical usage::

    from ai_3d_modeling_agent.multi_expert.constraints import (
        ConstraintChecker,
        PrimitiveSupportedChecker,
        BboxRangeChecker,
    )

    checker = ConstraintChecker()
    checker.register(PrimitiveSupportedChecker())
    checker.register(BboxRangeChecker())

    violations = checker.run(spec_artifact, manifest_data)
"""

from __future__ import annotations

from .checker import ConstraintChecker, ConstraintPlugin
from .plugins import (
    AttachmentInBboxChecker,
    BboxRangeChecker,
    ChildSmallerThanParentChecker,
    NoOrphansPartsChecker,
    ParentHasAttachmentChecker,
    PrimitiveSupportedChecker,
    SymmetryValidityChecker,
)
from .violations import ConstraintViolation, Severity

__all__ = [
    # orchestrator
    "ConstraintChecker",
    "ConstraintPlugin",
    # data model
    "ConstraintViolation",
    "Severity",
    # plugins
    "AttachmentInBboxChecker",
    "BboxRangeChecker",
    "ChildSmallerThanParentChecker",
    "NoOrphansPartsChecker",
    "ParentHasAttachmentChecker",
    "PrimitiveSupportedChecker",
    "SymmetryValidityChecker",
]
