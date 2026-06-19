"""Tests for extraction module including truncation detection and retry."""

import pytest

from ai_3d_modeling_agent.multi_expert.core.extraction import (
    _is_truncated,
    _add_truncation_hint,
    extract_design_artifact,
    extract_plan_artifact,
    extract_spec_artifact,
    extract_validation_artifact,
)
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation


class TestIsTruncated:
    """Tests for _is_truncated function."""

    def test_complete_json_not_truncated(self):
        """Complete JSON is not detected as truncated."""
        assert _is_truncated('{"parts": {"seat": {"primitive": "cube"}}}') is False

    def test_unbalanced_braces_detected(self):
        """JSON with more opening braces than closing is detected as truncated."""
        assert _is_truncated('{"parts": {"seat": {"primitive": "cube"') is True

    def test_empty_string_not_truncated(self):
        """Empty string is not truncated."""
        assert _is_truncated('') is False

    def test_truncated_mid_value(self):
        """Response ending mid-value is detected as truncated."""
        assert _is_truncated('{"width": 0.5, "depth": 0.') is True

    def test_complete_array_not_truncated(self):
        """Complete JSON array is not truncated."""
        assert _is_truncated('[{"name": "seat"}]') is False

    def test_truncated_string_value(self):
        """Response ending mid-string is detected as truncated."""
        assert _is_truncated('{"name": "seat"') is True


class TestAddTruncationHint:
    """Tests for _add_truncation_hint function."""

    def test_adds_hint_messages(self):
        """Truncation hint adds assistant and user messages."""
        original = [{"role": "system", "content": "test"}]
        truncated = '{"parts": {"seat": {"primitive": "cube"'

        result = _add_truncation_hint(original, truncated)

        assert len(result) == 3
        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == truncated
        assert result[2]["role"] == "user"
        assert "truncated" in result[2]["content"].lower()

    def test_does_not_modify_original(self):
        """Original messages list is not modified."""
        original = [{"role": "system", "content": "test"}]
        truncated = '{"parts": {"seat": {"primitive": "cube"'

        result = _add_truncation_hint(original, truncated)

        assert len(original) == 1
        assert len(result) == 3


class TestExtractionRetry:
    """Tests for extraction retry on truncation."""

    def test_retries_on_truncated_response(self):
        """Extraction retries when first response is truncated."""
        class TruncatedThenFixedLLM:
            def __init__(self):
                self.call_count = 0
            def call(self, system_prompt="", messages=None, response_model=None, sampling=None):
                self.call_count += 1
                if self.call_count == 1:
                    return '{"parts": {"seat": {"primitive": "cube"'
                return '{"parts": {"seat": {"primitive": "cube", "target_bbox": {"width": 1.0, "depth": 1.0, "height": 0.1}}}, "validation_notes": [], "summary": "ok"}'

        llm = TruncatedThenFixedLLM()
        conversation = Conversation(phase_name="spec")

        result = extract_spec_artifact(conversation, llm)

        assert result.parts is not None
        assert llm.call_count == 2  # Retried once

    def test_gives_up_after_max_attempts(self):
        """Extraction gives up after max truncation attempts."""
        class AlwaysTruncatedLLM:
            def __init__(self):
                self.call_count = 0
            def call(self, system_prompt="", messages=None, response_model=None, sampling=None):
                self.call_count += 1
                return '{"parts": {"seat": {"primitive": "cube"'

        llm = AlwaysTruncatedLLM()
        conversation = Conversation(phase_name="spec")

        result = extract_spec_artifact(conversation, llm)

        assert len(result.failure_notes) > 0
        assert llm.call_count == 3  # Tried max_attempts times


class TestSpecExtraction:
    def test_null_bbox_is_preserved_as_missing_geometry_not_default_unit_cube(self):
        class NullBBoxLLM:
            def call(self, system_prompt="", messages=None, response_model=None, sampling=None):
                return (
                    '{"parts":{"leg":{"primitive":"cube","instance_count":4,'
                    '"target_bbox":{"width":null,"depth":null,"height":null}}},'
                    '"validation_notes":["dimensions unresolved"],"summary":"spec"}'
                )

        result = extract_spec_artifact(Conversation(phase_name="spec"), NullBBoxLLM())

        assert result.parts["leg"]["instance_count"] == 4
        assert result.parts["leg"]["target_bbox"] == {}

    def test_spec_extraction_preserves_geometry_source_and_assumptions(self):
        class AssumedBBoxLLM:
            def call(self, system_prompt="", messages=None, response_model=None, sampling=None):
                return (
                    '{"parts":{"seat":{"primitive":"cube","geometry_source":"assumed",'
                    '"assumptions":["standard chair seat"],'
                    '"target_bbox":{"width":0.5,"depth":0.4,"height":0.1}}},'
                    '"validation_notes":["seat dimensions assumed"],"summary":"spec"}'
                )

        result = extract_spec_artifact(Conversation(phase_name="spec"), AssumedBBoxLLM())

        assert result.parts["seat"]["geometry_source"] == "assumed"
        assert result.parts["seat"]["assumptions"] == ["standard chair seat"]


class TestPlanExtraction:
    def test_plan_extraction_parses_responsibility_split(self):
        class PlanLLM:
            def call(self, system_prompt="", messages=None, response_model=None, sampling=None):
                return (
                    '{'
                    '"summary":"Build the seat first, then place the leg.",'
                    '"execution_rationale":["Seat is the root."],'
                    '"build_responsibilities":[{"id":"build-seat","family":"seat","summary":"Builder creates the seat.","geometry_assumptions":["Use the agreed primitive."],"deferred_placement":["Assembly handles final placement."],"decision_refs":["plan.build_responsibilities.seat"]}],'
                    '"assembly_responsibilities":[{"id":"assemble-leg","family":"leg","summary":"Builder places the leg.","placement_relations":["Attach leg to seat."],"hierarchy_notes":["Seat remains the root parent."],"decision_refs":["plan.assembly_responsibilities.leg"]}],'
                    '"dependency_summary":["Build seat before placing the leg."],'
                    '"ordering_constraints":[{"id":"ordering-seat-before-leg","summary":"Seat must exist before leg placement.","depends_on":["build:seat"],"responsibility":"builder","decision_refs":["plan.ordering_constraints.seat-before-leg"]}],'
                    '"risk_hotspots":[{"id":"risk-leg-attach","summary":"Leg attachment requires clear anchors.","owner":"builder","issue_refs":["plan-open-1"],"reason":"Missing anchors would create assembly ambiguity."}],'
                    '"open_issues":["Confirm the final leg attachment tolerance."]'
                    '}'
                )

        conversation = Conversation(phase_name="plan")
        result = extract_plan_artifact(conversation, PlanLLM())

        assert result.summary
        assert result.build_responsibilities[0]["family"] == "seat"
        assert result.assembly_responsibilities[0]["family"] == "leg"
        assert result.ordering_constraints[0]["responsibility"] == "builder"
        assert result.risk_hotspots[0]["owner"] == "builder"


class TestAoExtractionRouting:
    def test_phase_extraction_routes_to_moderator_with_skill(self):
        class RoutingLLM:
            def __init__(self):
                self.calls = []

            def call(self, system_prompt="", messages=None, response_model=None, sampling=None, **kwargs):
                self.calls.append({"system_prompt": system_prompt, "messages": messages or [], **kwargs})
                skill = kwargs.get("skill", "")
                if skill == "extract-design-artifact":
                    return '{"parts":[],"assembly_concept":"simple","unresolved_issues":[],"summary":"design"}'
                if skill == "extract-spec-artifact":
                    return '{"parts":{},"validation_notes":[],"summary":"spec"}'
                if skill == "extract-plan-artifact":
                    return '{"summary":"plan","execution_rationale":[],"build_responsibilities":[],"assembly_responsibilities":[],"dependency_summary":[],"ordering_constraints":[],"risk_hotspots":[],"open_issues":[]}'
                if skill == "extract-validation-artifact":
                    return '{"passed":true,"errors":[],"warnings":[],"comparisons":[]}'
                return "{}"

        llm = RoutingLLM()

        extract_design_artifact(Conversation(phase_name="design"), llm)
        extract_spec_artifact(Conversation(phase_name="spec"), llm)
        extract_plan_artifact(Conversation(phase_name="plan"), llm)
        extract_validation_artifact(Conversation(phase_name="validate"), llm)

        assert [call["agent"] for call in llm.calls] == ["moderator", "moderator", "moderator", "moderator"]
        assert [call["skill"] for call in llm.calls] == [
            "extract-design-artifact",
            "extract-spec-artifact",
            "extract-plan-artifact",
            "extract-validation-artifact",
        ]
        assert all(call["system_prompt"] == "" for call in llm.calls)
