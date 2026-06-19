"""Focused correction meeting between a target expert and a reviewer.

A ``FocusedMeeting`` is **not** a Phase variant — it is an independent
class with a simple consensus rule: if the reviewer does not veto the
proposed revision, the correction is approved.

``CorrectionResponse`` carries the revised artifact back to the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feedback import UserCorrection


@dataclass
class CorrectionResponse:
    """Result of a focused correction meeting.

    Attributes
    ----------
    revised_artifact:
        The artifact after the correction has been applied.  May be the
        same object as the input draft when no change was made (e.g. the
        reviewer vetoed the correction).
    approved:
        Whether the reviewer approved the correction.  ``True`` by
        default in Stage 4a (no real reviewer wired yet).
    notes:
        Optional notes from the meeting (e.g. reviewer comments).
    """

    revised_artifact: Any = None
    approved: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class FocusedMeetingContext:
    """Context passed into a focused correction meeting.

    Attributes
    ----------
    correction:
        The ``UserCorrection`` to address in this meeting.
    draft_artifact:
        The current draft artifact being corrected.
    revision_history:
        Prior versions of the artifact (for reference by the expert).
    """

    correction: UserCorrection
    draft_artifact: Any
    revision_history: list[Any] = field(default_factory=list)


class FocusedMeeting:
    """Run a focused conversation between a target expert and a reviewer.

    Not a Phase variant — independent class with simple consensus:
    reviewer doesn't veto → approved.

    Parameters
    ----------
    target_expert:
        The expert responsible for the field being corrected (e.g.
        ``designer`` for ``parts``, ``specifier`` for ``target_bbox``).
    reviewer:
        The reviewer expert who validates the correction.
    """

    def __init__(self, target_expert: Any, reviewer: Any) -> None:
        self.target_expert = target_expert
        self.reviewer = reviewer

    def run(self, context: FocusedMeetingContext, llm: Any) -> CorrectionResponse:
        """Run the focused meeting and return a ``CorrectionResponse``.

        Stage 4a stub — returns the draft artifact unchanged with
        ``approved=True``.  Stage 4b will wire in real expert/reviewer
        LLM calls:

        1. Target expert speaks with the correction context.
        2. Reviewer speaks to validate.
        3. If reviewer approves → return revised artifact.

        Parameters
        ----------
        context:
            Meeting context carrying the correction and draft artifact.
        llm:
            LLM interface (unused in Stage 4a).

        Returns
        -------
        CorrectionResponse
            Stub response with the original draft artifact.
        """
        return CorrectionResponse(revised_artifact=context.draft_artifact)
