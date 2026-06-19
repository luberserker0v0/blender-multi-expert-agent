"""Rejection and correction types for the revision pipeline.

When a phase artifact fails validation, a Rejection is produced.
The pipeline routes the rejection to the appropriate expert via
a CorrectionRequest, and the expert returns a CorrectionResponse.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RejectionReason(str, Enum):
    """Deterministic rejection categories — no LLM interpretation needed."""

    UNSUPPORTED_PRIMITIVE = "UNSUPPORTED_PRIMITIVE"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    UNSUPPORTED_MATERIAL = "UNSUPPORTED_MATERIAL"
    INSTANCE_LIMIT_EXCEEDED = "INSTANCE_LIMIT_EXCEEDED"
    UNSUPPORTED_TRANSFORM = "UNSUPPORTED_TRANSFORM"
    DIMENSION_OUT_OF_RANGE = "DIMENSION_OUT_OF_RANGE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


@dataclass
class Rejection:
    """A single rejection record from a validation or review phase."""

    reason: RejectionReason
    detail: str
    phase_name: str
    artifact_field: str = ""


@dataclass
class CorrectionRequest:
    """Request sent to an expert to correct a rejected artifact."""

    rejection: Rejection
    current_artifact: Any
    suggested_fix: str = ""


@dataclass
class CorrectionResponse:
    """Response from an expert after attempting correction."""

    revised_artifact: Any
    approved: bool = False
    reviewer_notes: str = ""
