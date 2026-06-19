"""Convener (speaker selection) base + process (round-robin) implementation.

The Convener decides which expert speaks next, whether the conversation
should terminate, and (for LLM-based conveners) extracts the final artifact
from the conversation history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .termination import StopReason, TerminationPolicy


@dataclass
class Convener:
    """Base convener — decides speaker order, termination, and extraction.

    Parameters
    ----------
    mode:
        ``"process"`` for deterministic round-robin, ``"llm"`` for LLM-driven
        selection (deferred to Stage 3).
    summary_strategy:
        Placeholder for a ``ContextWindowStrategy`` instance (Stage 4b).
    """

    mode: str = "process"
    summary_strategy: Any = None

    def choose_next(self, conversation: Conversation, context: Any) -> str:
        """Choose the next speaker.

        Parameters
        ----------
        conversation:
            Full conversation history.
        context:
            Phase-specific context metadata.

        Returns
        -------
        str
            The role name of the next speaker.
        """
        ...

    def extract(self, conversation: Conversation, llm: Any) -> Any:
        """Extract an artifact from the completed conversation.

        Parameters
        ----------
        conversation:
            Completed conversation history.
        llm:
            LLM interface for structured extraction.

        Returns
        -------
        Any
            A typed Artifact (concrete type depends on the phase).
        """
        ...

    def check_termination(
        self, conversation: Conversation, termination: TerminationPolicy
    ) -> bool:
        """Check whether the conversation should terminate.

        Parameters
        ----------
        conversation:
            Current conversation history.
        termination:
            Termination policy to evaluate.

        Returns
        -------
        bool
            ``True`` if termination is required.
        """
        return termination.check() != StopReason.NOT_FINISHED


@dataclass
class ProcessConvener(Convener):
    """Round-robin convener that cycles through a fixed participant list.

    Each call to :meth:`choose_next` advances the internal index, producing
    a deterministic speaker sequence.  Does **not** extract artifacts —
    :meth:`extract` returns ``None``.

    Parameters
    ----------
    participants:
        Ordered list of expert role names.
    current_index:
        Starting index into *participants*.
    """

    participants: list[str] = field(default_factory=list)
    current_index: int = 0

    def choose_next(self, conversation: Conversation, context: Any) -> str:
        """Return the next participant in round-robin order.

        Parameters
        ----------
        conversation:
            Full conversation history (ignored by round-robin).
        context:
            Phase-specific context (ignored by round-robin).

        Returns
        -------
        str
            The next speaker role name.
        """
        speaker = self.participants[self.current_index % len(self.participants)]
        self.current_index += 1
        return speaker

    def extract(self, conversation: Conversation, llm: Any) -> Any:
        """Process convener does not extract artifacts.

        Parameters
        ----------
        conversation:
            Completed conversation (ignored).
        llm:
            LLM interface (ignored).

        Returns
        -------
        None
        """
        return None
