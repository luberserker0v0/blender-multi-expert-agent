"""Tests for the review system: UserFeedback, CorrectionQueue, FocusedMeeting, etc."""

from dataclasses import dataclass

import pytest

from ai_3d_modeling_agent.multi_expert.review.correction_queue import CorrectionQueue
from ai_3d_modeling_agent.multi_expert.review.feedback import UserCorrection, UserFeedback
from ai_3d_modeling_agent.multi_expert.review.focused_meeting import (
    FocusedMeeting,
    FocusedMeetingContext,
)
from ai_3d_modeling_agent.multi_expert.review.gate import UserReviewGate
from ai_3d_modeling_agent.multi_expert.review.preview import AsciiPreviewRenderer


# ===================================================================
# UserCorrection
# ===================================================================


class TestUserCorrection:
    """Verify UserCorrection dataclass fields."""

    def test_minimal_correction(self):
        c = UserCorrection(field="parts", old_value={"a": 1}, new_value={"a": 2})
        assert c.field == "parts"
        assert c.old_value == {"a": 1}
        assert c.new_value == {"a": 2}
        assert c.reason == ""

    def test_correction_with_reason(self):
        c = UserCorrection(
            field="target_bbox",
            old_value=[1.0, 1.0, 1.0],
            new_value=[2.0, 2.0, 2.0],
            reason="part needs to be bigger",
        )
        assert c.reason == "part needs to be bigger"

    def test_correction_repr(self):
        c = UserCorrection(field="parts", old_value="x", new_value="y")
        s = repr(c)
        assert "parts" in s
        assert "x" in s
        assert "y" in s


# ===================================================================
# UserFeedback
# ===================================================================


class TestUserFeedback:
    """Verify UserFeedback approval logic and parse_free_text stub."""

    def test_approved_empty(self):
        fb = UserFeedback(approved=True)
        assert fb.is_approved() is True

    def test_not_approved_by_default(self):
        fb = UserFeedback()
        assert fb.is_approved() is False

    def test_not_approved_when_has_corrections(self):
        fb = UserFeedback(
            approved=True,
            corrections=[UserCorrection(field="parts", old_value={}, new_value={})],
        )
        assert fb.is_approved() is False

    def test_not_approved_when_has_free_text(self):
        fb = UserFeedback(approved=True, free_text="make it bigger")
        assert fb.is_approved() is False

    def test_not_approved_when_both_corrections_and_free_text(self):
        fb = UserFeedback(
            approved=True,
            corrections=[UserCorrection(field="parts", old_value={}, new_value={})],
            free_text="also fix this",
        )
        assert fb.is_approved() is False

    def test_not_approved_false_with_no_corrections(self):
        fb = UserFeedback(approved=False)
        assert fb.is_approved() is False

    def test_parse_free_text_returns_empty_list(self):
        fb = UserFeedback(free_text="make the legs longer")
        assert fb.parse_free_text(llm=None, draft_artifact=None) == []

    def test_fields(self):
        fb = UserFeedback(approved=True, free_text="looks good")
        assert fb.approved is True
        assert fb.free_text == "looks good"
        assert fb.corrections == []


# ===================================================================
# CorrectionQueue
# ===================================================================


class TestCorrectionQueue:
    """Verify CorrectionQueue FIFO behavior with guards."""

    def test_empty_queue(self):
        q = CorrectionQueue()
        assert q.is_empty() is True
        assert len(q) == 0
        assert q.peek() is None
        assert q.remaining() == 0

    def test_add_and_peek(self):
        q = CorrectionQueue()
        c = UserCorrection(field="parts", old_value={}, new_value={})
        q.add(c)
        assert q.is_empty() is False
        assert q.peek() is c
        assert q.remaining() == 1

    def test_advance_through_queue(self):
        q = CorrectionQueue()
        c1 = UserCorrection(field="a", old_value=1, new_value=2)
        c2 = UserCorrection(field="b", old_value=3, new_value=4)
        q.add(c1)
        q.add(c2)
        assert q.remaining() == 2
        q.advance()
        assert q.remaining() == 1
        q.advance()
        assert q.remaining() == 0

    def test_iteration(self):
        q = CorrectionQueue()
        c1 = UserCorrection(field="a", old_value=1, new_value=2)
        c2 = UserCorrection(field="b", old_value=3, new_value=4)
        q.add(c1)
        q.add(c2)
        assert list(q) == [c1, c2]

    def test_add_rejects_non_usercorrection(self):
        q = CorrectionQueue()
        with pytest.raises(TypeError):
            q.add("not a correction")

    def test_add_rejects_empty_field(self):
        q = CorrectionQueue()
        with pytest.raises(ValueError):
            q.add(UserCorrection(field="", old_value=1, new_value=2))

    def test_add_multiple_then_peek_consistency(self):
        q = CorrectionQueue()
        corrections = [
            UserCorrection(field="parts", old_value={}, new_value={"leg": {}}),
            UserCorrection(field="primitive", old_value="torus", new_value="cube"),
        ]
        for c in corrections:
            q.add(c)
        assert q.remaining() == 2
        assert q.peek() is corrections[0]
        q.advance()
        assert q.peek() is corrections[1]

    def test_advance_past_end_does_not_error(self):
        q = CorrectionQueue()
        q.add(UserCorrection(field="x", old_value=1, new_value=2))
        q.advance()
        q.advance()
        assert q.remaining() == 0
        assert q.peek() is None


# ===================================================================
# AsciiPreviewRenderer
# ===================================================================


class TestAsciiPreviewRenderer:
    """Verify AsciiPreviewRenderer delegates to str()."""

    def test_renders_string(self):
        renderer = AsciiPreviewRenderer()
        result = renderer.render("hello")
        assert result == "hello"

    def test_renders_dict(self):
        renderer = AsciiPreviewRenderer()
        d = {"parts": ["body", "leg"]}
        result = renderer.render(d)
        assert result == str(d)

    def test_renders_none(self):
        renderer = AsciiPreviewRenderer()
        assert renderer.render(None) == "None"

    def test_renders_dataclass(self):
        from dataclasses import dataclass

        @dataclass
        class Dummy:
            x: int = 1
            y: str = "test"

        renderer = AsciiPreviewRenderer()
        result = renderer.render(Dummy())
        assert "test" in result
        assert "1" in result


# ===================================================================
# FocusedMeeting
# ===================================================================


class TestFocusedMeeting:
    """Verify FocusedMeeting (Stage 4a stub)."""

    def test_run_returns_draft_unchanged(self):
        from ai_3d_modeling_agent.multi_expert.experts import Reviewer, Specifier

        meeting = FocusedMeeting(
            target_expert=Specifier(),
            reviewer=Reviewer(),
        )
        draft = {"parts": {"body": {"primitive": "cube"}}}
        correction = UserCorrection(
            field="primitive",
            old_value="cube",
            new_value="cylinder",
        )
        ctx = FocusedMeetingContext(
            correction=correction,
            draft_artifact=draft,
            revision_history=[],
        )
        result = meeting.run(ctx, llm=None)
        assert result.revised_artifact is draft
        assert result.approved is True
        assert result.notes == []

    def test_focused_meeting_context_fields(self):
        correction = UserCorrection(field="x", old_value=1, new_value=2)
        ctx = FocusedMeetingContext(
            correction=correction,
            draft_artifact={"x": 1},
            revision_history=[{"x": 0}],
        )
        assert ctx.correction.field == "x"
        assert ctx.draft_artifact == {"x": 1}
        assert ctx.revision_history == [{"x": 0}]


# ===================================================================
# UserReviewGate
# ===================================================================


class TestUserReviewGate:
    """Verify UserReviewGate structure and get_target_expert mapping."""

    def test_get_target_expert_designer_parts(self):
        from ai_3d_modeling_agent.multi_expert.experts import Designer
        from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry

        registry = ExpertRegistry()
        registry.register(Designer())

        correction = UserCorrection(field="parts", old_value={}, new_value={})
        expert = UserReviewGate.get_target_expert(correction, registry)
        assert isinstance(expert, Designer)

    def test_get_target_expert_specifier_fields(self):
        from ai_3d_modeling_agent.multi_expert.experts import Specifier
        from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry

        registry = ExpertRegistry()
        registry.register(Specifier())

        for field in ("target_bbox", "primitive", "attachment_points"):
            correction = UserCorrection(field=field, old_value={}, new_value={})
            expert = UserReviewGate.get_target_expert(correction, registry)
            assert isinstance(expert, Specifier), f"field={field} should map to specifier"

    def test_get_target_expert_fallback_designer(self):
        from ai_3d_modeling_agent.multi_expert.experts import Designer
        from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry

        registry = ExpertRegistry()
        registry.register(Designer())

        correction = UserCorrection(field="unknown_field", old_value={}, new_value={})
        expert = UserReviewGate.get_target_expert(correction, registry)
        assert isinstance(expert, Designer)

    def test_get_target_expert_not_found_returns_none(self):
        from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry

        registry = ExpertRegistry()
        correction = UserCorrection(field="parts", old_value={}, new_value={})
        expert = UserReviewGate.get_target_expert(correction, registry)
        assert expert is None

    def test_review_stub_returns_draft(self):
        gate = UserReviewGate(
            constraint_checker=None,
            preview_renderer=AsciiPreviewRenderer(),
        )
        draft = {"parts": {"body": {"primitive": "cube"}}}
        result = gate.review(draft, user=None, llm=None, manifests=None)
        assert result is draft
