"""User review gate system for the multi-expert pipeline.

Stage 4a — user-facing correction flow with preview rendering,
constraint violation reporting, and focused correction meetings.

Typical usage::

    from ai_3d_modeling_agent.multi_expert.review import (
        AsciiPreviewRenderer,
        CorrectionQueue,
        UserFeedback,
        UserReviewGate,
    )

    gate = UserReviewGate(
        constraint_checker=checker,
        preview_renderer=AsciiPreviewRenderer(),
    )
    approved_draft = gate.review(draft, user, llm, manifests)
"""

from __future__ import annotations

from .correction_queue import CorrectionQueue
from .feedback import UserCorrection, UserFeedback
from .focused_meeting import CorrectionResponse, FocusedMeeting, FocusedMeetingContext
from .gate import UserReviewGate
from .preview import AsciiPreviewRenderer, PreviewRenderer

__all__ = [
    "AsciiPreviewRenderer",
    "CorrectionQueue",
    "CorrectionResponse",
    "FocusedMeeting",
    "FocusedMeetingContext",
    "PreviewRenderer",
    "UserCorrection",
    "UserFeedback",
    "UserReviewGate",
]
