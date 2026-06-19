"""Validation phase artifact — output of the Inspector expert.

Domain: comparison of built assembly against the original specification,
listing errors, warnings, and detailed comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationArtifact:
    """Validation phase output — pass/fail with detailed comparison results.

    Produced by the Inspector expert. Compares the final assembly against
    the specification and reports discrepancies.
    """

    passed: bool = False
    """Whether validation passed overall."""

    errors: list[str] = field(default_factory=list)
    """Critical validation errors that caused failures."""

    warnings: list[str] = field(default_factory=list)
    """Non-critical issues found during validation."""

    comparisons: list[dict[str, Any]] = field(default_factory=list)
    """Blueprint-vs-actual comparison line items."""

    failure_notes: list[str] = field(default_factory=list)
    """Non-empty only when partial recovery occurred."""

    planning_warnings: list[str] = field(default_factory=list)
    """Planning-related warnings observed during execution or validation."""

    planning_failures: list[str] = field(default_factory=list)
    """Planning-related failures that should affect retry/triage decisions."""

    planning_constraint_refs: list[str] = field(default_factory=list)
    """Refs to ordering/constraint items implicated in validation outcomes."""

    planning_responsibility_refs: list[str] = field(default_factory=list)
    """Refs to builder/assembler responsibility items implicated in outcomes."""
