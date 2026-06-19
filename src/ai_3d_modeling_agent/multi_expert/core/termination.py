"""Termination policy and consensus protocol for the multi-expert pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StopReason(Enum):
    """Enumeration of possible reasons a pipeline phase may stop."""

    MAX_ROUNDS = "max_rounds"
    MAX_WALL_CLOCK = "max_wall_clock"
    MAX_COMPUTE = "max_compute"
    EARLY_CONSENSUS = "early_consensus"
    NOT_FINISHED = "not_finished"


@dataclass
class ConsensusProtocol:
    """Configuration for how consensus is determined among experts.

    Attributes:
        mode: Consensus mode (e.g. "unanimous", "majority").
        veto_weight: Role whose veto carries extra weight (e.g. "reviewer").
    """

    mode: str = "unanimous"
    veto_weight: str = "reviewer"


@dataclass
class TerminationPolicy:
    """Policies and runtime counters that determine when a phase stops.

    Hard limits (max_*) are set at construction and preserved across resets.
    Current counters accumulate during execution and are reset by reset_limits().
    revision_count accumulates across the entire pipeline run.

    Attributes:
        max_rounds: Maximum number of conversation rounds allowed.
        max_wall_clock_seconds: Maximum wall-clock time in seconds.
        max_compute_seconds: Maximum compute time in seconds.
        early_consensus: Whether to allow early stop when consensus is reached.
        consensus_protocol: Optional consensus configuration.
        current_rounds: Number of rounds completed so far.
        current_wall_elapsed: Wall-clock seconds elapsed so far.
        current_compute_elapsed: Compute seconds consumed so far.
        revision_count: Total revision count across the pipeline run.
    """

    max_rounds: int = 10
    max_wall_clock_seconds: int = 600
    max_compute_seconds: int = 300
    early_consensus: bool = True
    consensus_protocol: ConsensusProtocol | None = None
    current_rounds: int = 0
    current_wall_elapsed: float = 0.0
    current_compute_elapsed: float = 0.0
    revision_count: int = 0

    def reset_limits(self) -> None:
        """Reset current counters while preserving hard limits.

        revision_count is NOT reset — it accumulates across the run.
        """
        self.current_rounds = 0
        self.current_wall_elapsed = 0.0
        self.current_compute_elapsed = 0.0

    def check(self) -> StopReason:
        """Evaluate current state against hard limits.

        Returns:
            The first exceeded StopReason, or NOT_FINISHED if all limits
            are still within bounds. Early consensus is a soft stop that
            must be evaluated externally by the orchestrator.
        """
        if self.current_rounds >= self.max_rounds:
            return StopReason.MAX_ROUNDS
        if self.current_wall_elapsed >= self.max_wall_clock_seconds:
            return StopReason.MAX_WALL_CLOCK
        if self.current_compute_elapsed >= self.max_compute_seconds:
            return StopReason.MAX_COMPUTE
        return StopReason.NOT_FINISHED
