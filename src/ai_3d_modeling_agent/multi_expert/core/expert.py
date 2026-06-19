"""Expert ABC and LlmInterface Protocol — foundation of the multi-expert pipeline.

Defines the contract that every domain expert must satisfy and the LLM
interface through which experts communicate with language models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Protocol, Type

from pydantic import BaseModel


@dataclass(frozen=True)
class SamplingOptions:
    """Provider-agnostic sampling controls for LLM calls."""

    temperature: float = 0.3


class LlmInterface(Protocol):
    """Protocol for an LLM client that the multi-expert pipeline uses.

    Implementations may wrap OpenAI-compatible endpoints, local models,
    or mock responders.
    """

    def call(
        self,
        system_prompt: str,
        messages: list[dict],
        response_model: Optional[Type[BaseModel]] = None,
        sampling: Optional[SamplingOptions] = None,
        **kwargs: object,
    ) -> str:
        """Call the LLM and return the text response.

        Parameters
        ----------
        system_prompt:
            System-level instruction for the LLM.
        messages:
            Conversation history formatted as
            ``[{"role": "user", "content": ...}]``.
        response_model:
            Optional Pydantic model for structured (JSON) output.  When
            provided the implementation should parse the response into
            the given model and return its JSON representation.
        sampling:
            Optional provider-agnostic generation controls. v1 uses
            ``temperature`` only.

        Returns
        -------
        str
            The text response (or parsed JSON when *response_model* is
            given).
        """
        ...


class Expert(ABC):
    """Abstract base class for a domain expert in the multi-expert pipeline.

    Subclasses define a specific area of modelling expertise (e.g. mesh
    topology, materials, mechanical constraints) and produce messages
    grounded in the full conversation history and current phase context.
    """

    role_name: str
    """Short label for this expert, e.g. ``"topology_advisor"``."""

    description: str
    """Human-readable summary of this expert's domain."""

    capabilities: list[str]
    """Keywords describing what this expert can do."""

    system_prompt: str
    """System-level instruction injected before this expert speaks."""

    @abstractmethod
    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        """Produce one message based on the conversation and phase context.

        Parameters
        ----------
        conversation:
            Full conversation history exchanged so far.
        context:
            Metadata and state for the current pipeline phase.
        llm:
            LLM interface through which the expert may generate
            its response.

        Returns
        -------
        Message
            The expert's contribution to the conversation.
        """
        ...
