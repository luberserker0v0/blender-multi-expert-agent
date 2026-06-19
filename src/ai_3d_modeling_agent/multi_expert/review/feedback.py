"""User feedback and correction data models for the review gate.

``UserCorrection`` captures a single field-level edit requested by the
user.  ``UserFeedback`` aggregates the user's overall review response:
approval, a list of structured corrections, and/or free-text comments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserCorrection:
    """A single correction requested by the user.

    Attributes
    ----------
    field:
        Which artifact field to correct (e.g. ``"parts"``,
        ``"target_bbox"``).
    old_value:
        The current value of the field before correction.
    new_value:
        The desired value after correction.
    reason:
        Optional human-readable explanation of why this correction is
        needed.  Forwarded to the target expert during a FocusedMeeting.
    """

    field: str
    old_value: Any
    new_value: Any
    reason: str = ""


@dataclass
class UserFeedback:
    """User's review response: approval or list of corrections.

    A feedback object is *approved* only when the user explicitly
    approves **and** supplies no corrections or free-text comments.
    Free-text feedback is parsed into structured ``UserCorrection``
    objects via :meth:`parse_free_text` (stub in Stage 4a).

    Attributes
    ----------
    approved:
        Whether the user clicked "approve".
    corrections:
        Structured corrections already parsed by the UI or caller.
    free_text:
        Unstructured user feedback that may contain additional
        correction requests.
    """

    approved: bool = False
    corrections: list[UserCorrection] = field(default_factory=list)
    free_text: str = ""

    def is_approved(self) -> bool:
        """Return ``True`` only when the user fully approved with no corrections.

        A review is considered fully approved when:
        - ``approved`` is ``True``, **and**
        - ``corrections`` is empty, **and**
        - ``free_text`` is empty.
        """
        return self.approved and not self.corrections and not self.free_text

    def parse_free_text(self, llm: Any, draft_artifact: Any) -> list[UserCorrection]:
        """Use LLM to parse ``free_text`` into structured ``UserCorrection`` list.

        Stage 4a stub — returns an empty list.  Stage 4b will wire in
        an LLM call that extracts field-level corrections from unstructured
        user comments.

        Parameters
        ----------
        llm:
            LLM interface (unused in Stage 4a).
        draft_artifact:
            The draft artifact being reviewed (unused in Stage 4a).

        Returns
        -------
        list[UserCorrection]
            Empty list in Stage 4a.
        """
        return []
