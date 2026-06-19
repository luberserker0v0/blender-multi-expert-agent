"""Ordered correction queue with validation guards.

The ``CorrectionQueue`` holds an ordered list of ``UserCorrection``
objects to be processed sequentially by the user review gate.  Guards
reject malformed corrections before they enter the queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feedback import UserCorrection


@dataclass
class CorrectionQueue:
    """Ordered queue of corrections with validation guards.

    Corrections are processed in FIFO order by the ``UserReviewGate``.
    The queue provides basic validation on :meth:`add` to prevent
    malformed corrections from entering the pipeline.

    Attributes
    ----------
    corrections:
        Ordered list of queued corrections.
    """

    corrections: list[UserCorrection] = field(default_factory=list)
    _index: int = field(default=0, repr=False)

    def __iter__(self):
        """Iterate over queued corrections in order."""
        return iter(self.corrections)

    def __len__(self) -> int:
        """Return the number of queued corrections."""
        return len(self.corrections)

    def is_empty(self) -> bool:
        """Return ``True`` when no corrections are queued."""
        return len(self.corrections) == 0

    def add(self, correction: Any) -> None:
        """Add a correction after basic validation.

        Parameters
        ----------
        correction:
            A ``UserCorrection`` instance to enqueue.

        Raises
        ------
        TypeError
            If *correction* is not a ``UserCorrection``.
        ValueError
            If *correction* has an empty ``field`` attribute.
        """
        if not isinstance(correction, UserCorrection):
            raise TypeError(
                f"Expected UserCorrection, got {type(correction).__name__}"
            )
        if not correction.field:
            raise ValueError("Correction must target a non-empty field name")
        self.corrections.append(correction)

    def peek(self) -> UserCorrection | None:
        """Return the next correction without removing it, or ``None``."""
        if self._index < len(self.corrections):
            return self.corrections[self._index]
        return None

    def advance(self) -> None:
        """Advance the internal index by one position."""
        if self._index < len(self.corrections):
            self._index += 1

    def remaining(self) -> int:
        """Return the number of unprocessed corrections."""
        return len(self.corrections) - self._index
