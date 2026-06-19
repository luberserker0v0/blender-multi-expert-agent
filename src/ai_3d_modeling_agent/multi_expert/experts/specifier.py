"""Specifier expert — specifies exact geometry for each part family.

Specifier prompt wrapper for the multi-expert conversational pipeline.
The Specifier receives a ``DesignArtifact``
(part families) and produces a ``SpecArtifact`` (per-family geometry specs
including primitive, bounding box, and attachment points).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_3d_modeling_agent.multi_expert.core.expert import Expert
from ai_3d_modeling_agent.multi_expert.experts._turn import run_single_expert_turn

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_3d_modeling_agent.multi_expert.core.conversation import Message
    from ai_3d_modeling_agent.multi_expert.core.expert import LlmInterface


class Specifier(Expert):
    """Geometry specifier that translates part families into concrete specs.

    The Specifier takes a design decomposition (part families with parent-
    child relationships and symmetry groups) and produces precise geometric
    specifications: Blender primitives, bounding box dimensions, attachment
    points, and recommended refinement viewpoints.
    """

    role_name: str = "specifier"
    description: str = (
        "Specifies exact geometry (primitive, bounding box, attachment "
        "points) for each part family from a design decomposition."
    )
    capabilities: list[str] = [
        "geometry specification",
        "bounding box assignment",
        "attachment point design",
        "parent-child alignment",
    ]
    system_prompt: str = ""

    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        """Produce a geometry specification message.

        Parameters
        ----------
        conversation:
            Full conversation history exchanged so far in this phase.
        context:
            Metadata and state for the current pipeline phase.
        llm:
            LLM interface through which the expert generates its response.

        Returns
        -------
        Message
            The Specifier's geometry specification as a conversation message,
            typically containing a JSON ``part_specs`` payload in its
            ``content``.
        """
        message = run_single_expert_turn(self, conversation, context, llm)
        logger.warning(
            "[EXPERT] %s turn=%d | response chars=%d",
            self.role_name, len(conversation.messages) + 1, len(message.content),
        )
        return message
