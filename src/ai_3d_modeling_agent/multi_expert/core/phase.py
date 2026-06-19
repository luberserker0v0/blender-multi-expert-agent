"""Phase — the base execution unit of the multi-expert pipeline.

A Phase encapsulates a goal-driven LLM conversation among a group of expert
roles, followed by structured extraction via a Convener. Subclass or compose
Phase to implement pipeline stages such as analysis, critique, or synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .conversation import Conversation
from .convener import Convener
from .failure import FailurePolicy
from .termination import TerminationPolicy


@dataclass
class Phase:
    """A single pipeline phase: multi-expert conversation + convener extraction.

    Attributes:
        name: Human-readable label for this phase (e.g. "analysis").
        goal: Description of what this phase aims to accomplish.
        participants: Ordered list of expert roles that take part.
        convener: The Convener instance that drives the conversation and
            later extracts a structured artifact from it.
        termination: Policy governing when the conversation loop stops.
        failure_policy: Behaviour when the phase fails (retry / abort /
            skip). Defaults to RETRYABLE.
        artifact_type: The Artifact subclass produced by this phase. Set to
            a specific type by subclasses or config.
    """

    name: str
    goal: str
    participants: list[str]
    convener: Convener
    termination: TerminationPolicy
    failure_policy: FailurePolicy = FailurePolicy.RETRYABLE
    artifact_type: type = object  # Will be set to specific Artifact subclass

    # Set by Pipeline._emit_event injection; fallback prints to stdout.
    _emit_event: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, context: Any, llm: Any) -> Any:
        """Run the full phase: conversation + extraction.

        Parameters
        ----------
        context:
            Phase-level context object carrying metadata, assets, and
            any state shared across phases.
        llm:
            LLM interface (expected to satisfy LlmInterface) used to
            drive expert responses.

        Returns
        -------
        Any
            A typed *Artifact* produced by the convener, or ``None`` if
            extraction is not yet wired (Stage 1 stub).
        """
        conversation = self.run_llm_conversation(context, llm)
        return self.convener.extract(conversation, llm)

    def run_llm_conversation(self, context: Any, llm: Any) -> Conversation:
        """Run the LLM discussion loop without convener extraction.

        Parameters
        ----------
        context:
            Phase-level context object.
        llm:
            LLM interface.

        Returns
        -------
        Conversation
            The full *Conversation* object for callers to inspect.
        """
        conversation = Conversation(phase_name=self.name, context=context)
        self.convener.open(conversation, context)  # state goal + context
        if hasattr(self.convener, "reset"):
            self.convener.reset()
        while not self.convener.check_termination(conversation, self.termination):
            speaker_role = self.convener.choose_next(conversation, context)
            # NOTE: Stage 2 will wire in expert via registry:
            #   expert = registry.get(speaker_role)
            #   message = expert.speak(conversation, context, llm)
            #   conversation.append(message)
            break  # Stub: single iteration until expert wiring lands
        return conversation

    def run_focused(self, context: Any, correction: Any, llm: Any) -> Any:
        """Run a single-correction LLM round.

        Parameters
        ----------
        context:
            Phase-level context object.
        correction:
            Correction guidance (type depends on the concrete phase;
            may be a string description, structured diff, or ``None``).
        llm:
            LLM interface.

        Returns
        -------
        Any
            A *CorrectionResponse* placeholder. Returns ``None`` in
            Stage 1 — the return type will be concretised when the
            focused-correction sub-pipeline is implemented.
        """
        return None
