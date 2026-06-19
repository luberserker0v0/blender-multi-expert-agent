"""Constraint violation data model with severity mapping.

Provides the ``ConstraintViolation`` dataclass used throughout the
constraint validation pipeline and the ``Severity`` enum that controls
whether a violation is overridable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Severity level of a constraint violation.

    Controls the ``overridable`` computed property:
      - ERROR: not overridable (must be fixed).
      - WARNING / INFO: overridable (user may bypass).
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ConstraintViolation:
    """A single constraint violation detected by a plugin.

    Attributes
    ----------
    rule:
        Plugin / rule identifier, e.g. ``"primitive_supported"``.
    detail:
        Human-readable description of the violation.
    severity:
        Severity level (ERROR, WARNING, INFO).
    """

    rule: str
    detail: str
    severity: Severity

    @property
    def overridable(self) -> bool:
        """Whether the user can override this violation.

        Only ERROR-level violations are non-overridable.
        """
        return self.severity != Severity.ERROR
