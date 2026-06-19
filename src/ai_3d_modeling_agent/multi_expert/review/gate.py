"""UserReviewGate — full user review flow for Design and Spec phases.

The gate wraps ONLY the Design and Spec phases (Plan, Build, Assemble,
and Validate are excluded per spec).  It coordinates preview rendering,
constraint checking, user feedback collection, and focused correction
meetings.

Flow
----
1. ``draft = phase.run_llm_conversation(context, llm)``
2. ``violations = constraint_checker.run(draft, manifests)``
3. ``previews = preview_renderer.render(draft)``
4. ``feedback = user.review(previews, violations)``
5. If ``feedback.is_approved()`` → return draft
6. ``corrections = feedback.parse_free_text(llm, draft) or feedback.corrections``
7. ``quick_violations = constraint_checker.check_corrections(corrections, draft, manifests)``
8. If ``quick_violations`` is actionable → ask user to revise
9. ``queue = CorrectionQueue(corrections)``
10. For each correction in queue:
      - Build ``FocusedMeetingContext``
      - Resolve ``target_expert`` via deterministic field→role mapping
      - Run ``FocusedMeeting(target_expert, reviewer).run(ctx, llm)``
      - Apply ``response.revised_artifact`` to draft
      - Bump ``draft.version += 1``
11. Goto re-render (step 3)
"""

from __future__ import annotations

from typing import Any

from .correction_queue import CorrectionQueue
from .feedback import UserCorrection, UserFeedback
from .focused_meeting import CorrectionResponse, FocusedMeeting, FocusedMeetingContext
from .preview import PreviewRenderer


# Deterministic mapping from artifact field names to expert role names.
# Used by ``get_target_expert`` — no LLM call required.
_FIELD_TO_EXPERT: dict[str, str] = {
    "parts": "designer",
    "target_bbox": "specifier",
    "primitive": "specifier",
    "attachment_points": "specifier",
}


class UserReviewGate:
    """Full user review flow for Design and Spec phases.

    Coordinates preview rendering, constraint validation, user feedback,
    and focused correction meetings.  Only wraps Design and Spec phases;
    Plan, Build, Assemble, and Validate are excluded per spec.

    Parameters
    ----------
    constraint_checker:
        A ``ConstraintChecker`` instance with registered plugins.
    preview_renderer:
        A ``PreviewRenderer`` implementation for rendering draft
        artifacts for user inspection.
    """

    def __init__(
        self,
        constraint_checker: Any,
        preview_renderer: PreviewRenderer,
    ) -> None:
        self.constraint_checker = constraint_checker
        self.preview_renderer = preview_renderer

    def review(
        self,
        draft: Any,
        user: Any,
        llm: Any,
        manifests: Any | None = None,
    ) -> Any:
        """Run the full review gate flow.

        Stage 4a stub — returns *draft* unchanged.  Stage 4b will
        implement the complete loop described in the module docstring.

        Parameters
        ----------
        draft:
            The draft artifact to review (``DesignArtifact`` or
            ``SpecArtifact``).
        user:
            User interface object providing a ``review(previews, violations)``
            method that returns ``UserFeedback``.
        llm:
            LLM interface for parsing free-text feedback and driving
            focused meetings.
        manifests:
            Optional manifests forwarded to the constraint checker.

        Returns
        -------
        Any
            The (possibly revised) draft artifact.
        """
        # Stage 4a stub: return draft without running the full loop.
        return draft

    @staticmethod
    def get_target_expert(correction: UserCorrection, registry: Any) -> Any:
        """Map a correction's field to the responsible expert (deterministic).

        Uses a fixed ``field → role`` mapping — no LLM call required.
        Falls back to ``"designer"`` for unrecognized fields.

        Parameters
        ----------
        correction:
            The correction whose ``field`` determines the expert.
        registry:
            An ``ExpertRegistry`` instance for looking up experts by
            role name.

        Returns
        -------
        Any
            The ``Expert`` instance for the mapped role, or ``None`` if
            the role is not registered.
        """
        role = _FIELD_TO_EXPERT.get(correction.field, "designer")
        return registry.get(role)
