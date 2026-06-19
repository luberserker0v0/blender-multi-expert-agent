"""Failure policy and recovery models for the multi-expert pipeline.

Defines how the pipeline responds to expert failures — fatal abort,
automatic retry, or graceful degradation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailurePolicy(Enum):
    """Policy for handling an expert failure.

    Attributes
    ----------
    FATAL:
        Abort the pipeline immediately.
    RETRYABLE:
        Re-invoke the expert up to ``max_retries`` times.
    DEGRADE:
        Skip the failing expert and continue with remaining experts.
    """

    FATAL = "FATAL"
    RETRYABLE = "RETRYABLE"
    DEGRADE = "DEGRADE"


@dataclass
class FailureRecovery:
    """Configuration for recovering from an expert failure.

    Parameters
    ----------
    policy:
        The recovery strategy to apply.
    max_retries:
        Maximum number of retry attempts (only meaningful when
        *policy* is ``RETRYABLE``).
    description:
        Human-readable explanation of what went wrong.
    """

    policy: FailurePolicy
    max_retries: int = 3
    description: str = ""
