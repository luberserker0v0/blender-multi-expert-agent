"""Tests for core infrastructure: Convener, TerminationPolicy, FailurePolicy."""

import time

import pytest

from ai_3d_modeling_agent.multi_expert.core.convener import Convener, ProcessConvener
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy, FailureRecovery
from ai_3d_modeling_agent.multi_expert.core.termination import (
    ConsensusProtocol,
    StopReason,
    TerminationPolicy,
)


# ===================================================================
# Convener (base)
# ===================================================================


class TestConvener:
    """Verify base Convener default behavior (no-op methods)."""

    def test_choose_next_is_noop(self):
        conv = Convener()
        result = conv.choose_next(conversation=None, context=None)
        assert result is None

    def test_extract_is_noop(self):
        conv = Convener()
        result = conv.extract(conversation=None, llm=None)
        assert result is None

    def test_default_mode(self):
        conv = Convener()
        assert conv.mode == "process"

    def test_default_summary_strategy(self):
        conv = Convener()
        assert conv.summary_strategy is None


# ===================================================================
# ProcessConvener
# ===================================================================


class TestProcessConvener:
    """Verify round-robin speaker selection."""

    def test_single_participant(self):
        conv = ProcessConvener(participants=["designer"])
        assert conv.choose_next(None, None) == "designer"
        assert conv.choose_next(None, None) == "designer"
        assert conv.choose_next(None, None) == "designer"

    def test_two_participants_alternate(self):
        conv = ProcessConvener(participants=["designer", "reviewer"])
        assert conv.choose_next(None, None) == "designer"
        assert conv.choose_next(None, None) == "reviewer"
        assert conv.choose_next(None, None) == "designer"
        assert conv.choose_next(None, None) == "reviewer"

    def test_three_participants_cycle(self):
        conv = ProcessConvener(participants=["a", "b", "c"])
        expected = ["a", "b", "c", "a", "b", "c"]
        for exp in expected:
            assert conv.choose_next(None, None) == exp

    def test_extract_returns_none(self):
        conv = ProcessConvener(participants=["a"])
        assert conv.extract(None, None) is None

    def test_current_index_persists(self):
        conv = ProcessConvener(participants=["x", "y"])
        conv.choose_next(None, None)
        conv.choose_next(None, None)
        assert conv.current_index == 2

    def test_custom_start_index(self):
        conv = ProcessConvener(participants=["a", "b", "c"], current_index=1)
        assert conv.choose_next(None, None) == "b"
        assert conv.choose_next(None, None) == "c"

    def test_empty_participants_raises(self):
        conv = ProcessConvener(participants=[])
        with pytest.raises(ZeroDivisionError):
            conv.choose_next(None, None)

    def test_process_convener_fields(self):
        conv = ProcessConvener(participants=["a", "b"], current_index=0)
        assert conv.participants == ["a", "b"]
        assert conv.current_index == 0
        assert conv.mode == "process"


# ===================================================================
# Convener.check_termination
# ===================================================================


class TestConvenerCheckTermination:
    """Verify check_termination delegates to TerminationPolicy."""

    def test_not_finished(self):
        conv = Convener()
        term = TerminationPolicy(max_rounds=10)
        assert conv.check_termination(None, term) is False

    def test_max_rounds_reached(self):
        conv = Convener()
        term = TerminationPolicy(max_rounds=3, current_rounds=3)
        assert conv.check_termination(None, term) is True

    def test_convert_stop_reason(self):
        conv = Convener()
        for reason in (StopReason.MAX_ROUNDS, StopReason.MAX_WALL_CLOCK, StopReason.MAX_COMPUTE):
            term = TerminationPolicy(current_rounds=999)
            assert conv.check_termination(None, term) is True


# ===================================================================
# TerminationPolicy
# ===================================================================


class TestTerminationPolicy:
    """Verify TerminationPolicy limits and reset."""

    def test_default_max_rounds(self):
        policy = TerminationPolicy()
        assert policy.max_rounds == 10

    def test_not_finished_initially(self):
        policy = TerminationPolicy()
        assert policy.check() == StopReason.NOT_FINISHED

    def test_max_rounds_triggers(self):
        policy = TerminationPolicy(max_rounds=5, current_rounds=5)
        assert policy.check() == StopReason.MAX_ROUNDS

    def test_max_rounds_exceeded(self):
        policy = TerminationPolicy(max_rounds=3, current_rounds=4)
        assert policy.check() == StopReason.MAX_ROUNDS

    def test_max_wall_clock_triggers(self):
        policy = TerminationPolicy(max_wall_clock_seconds=10, current_wall_elapsed=10.0)
        assert policy.check() == StopReason.MAX_WALL_CLOCK

    def test_max_compute_triggers(self):
        policy = TerminationPolicy(max_compute_seconds=5, current_compute_elapsed=5.0)
        assert policy.check() == StopReason.MAX_COMPUTE

    def test_reset_limits(self):
        policy = TerminationPolicy(
            max_rounds=10,
            current_rounds=5,
            current_wall_elapsed=30.0,
            current_compute_elapsed=15.0,
        )
        policy.reset_limits()
        assert policy.current_rounds == 0
        assert policy.current_wall_elapsed == 0.0
        assert policy.current_compute_elapsed == 0.0
        assert policy.max_rounds == 10

    def test_reset_preserves_revision_count(self):
        policy = TerminationPolicy(revision_count=3)
        policy.current_rounds = 5
        policy.reset_limits()
        assert policy.revision_count == 3

    def test_early_consensus_default(self):
        policy = TerminationPolicy()
        assert policy.early_consensus is True

    def test_consensus_protocol_default(self):
        policy = TerminationPolicy()
        assert policy.consensus_protocol is None

    def test_consensus_protocol_custom(self):
        protocol = ConsensusProtocol(mode="majority", veto_weight="reviewer")
        policy = TerminationPolicy(consensus_protocol=protocol)
        assert policy.consensus_protocol.mode == "majority"
        assert policy.consensus_protocol.veto_weight == "reviewer"

    def test_order_of_checks(self):
        policy = TerminationPolicy(
            max_rounds=1,
            max_wall_clock_seconds=1,
            max_compute_seconds=1,
            current_rounds=2,
            current_wall_elapsed=2,
            current_compute_elapsed=2,
        )
        assert policy.check() == StopReason.MAX_ROUNDS

    def test_not_finished_when_below_all_limits(self):
        policy = TerminationPolicy(
            max_rounds=5,
            max_wall_clock_seconds=60,
            max_compute_seconds=30,
            current_rounds=3,
            current_wall_elapsed=20,
            current_compute_elapsed=10,
        )
        assert policy.check() == StopReason.NOT_FINISHED


# ===================================================================
# StopReason
# ===================================================================


class TestStopReason:
    """Verify StopReason enum values."""

    def test_values(self):
        assert StopReason.MAX_ROUNDS.value == "max_rounds"
        assert StopReason.MAX_WALL_CLOCK.value == "max_wall_clock"
        assert StopReason.MAX_COMPUTE.value == "max_compute"
        assert StopReason.EARLY_CONSENSUS.value == "early_consensus"
        assert StopReason.NOT_FINISHED.value == "not_finished"

    def test_unique_values(self):
        values = [r.value for r in StopReason]
        assert len(values) == len(set(values))


# ===================================================================
# FailurePolicy & FailureRecovery
# ===================================================================


class TestFailurePolicy:
    """Verify FailurePolicy enum values."""

    def test_values(self):
        assert FailurePolicy.FATAL.value == "FATAL"
        assert FailurePolicy.RETRYABLE.value == "RETRYABLE"
        assert FailurePolicy.DEGRADE.value == "DEGRADE"

    def test_unique_values(self):
        values = [p.value for p in FailurePolicy]
        assert len(values) == len(set(values))


class TestFailureRecovery:
    """Verify FailureRecovery dataclass."""

    def test_default_max_retries(self):
        r = FailureRecovery(policy=FailurePolicy.RETRYABLE)
        assert r.max_retries == 3

    def test_default_description(self):
        r = FailureRecovery(policy=FailurePolicy.FATAL)
        assert r.description == ""

    def test_custom_values(self):
        r = FailureRecovery(
            policy=FailurePolicy.RETRYABLE,
            max_retries=5,
            description="LLM call failed",
        )
        assert r.policy == FailurePolicy.RETRYABLE
        assert r.max_retries == 5
        assert r.description == "LLM call failed"

    def test_fatal_policy(self):
        r = FailureRecovery(policy=FailurePolicy.FATAL)
        assert r.policy == FailurePolicy.FATAL

    def test_degrade_policy(self):
        r = FailureRecovery(policy=FailurePolicy.DEGRADE)
        assert r.policy == FailurePolicy.DEGRADE

    def test_fields(self):
        r = FailureRecovery(policy=FailurePolicy.RETRYABLE)
        assert hasattr(r, "policy")
        assert hasattr(r, "max_retries")
        assert hasattr(r, "description")
