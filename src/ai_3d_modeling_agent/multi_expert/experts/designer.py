"""Designer expert — decomposes a user's task into logical part families.

Designer prompt wrapper for the multi-expert conversational pipeline.
The Designer is one of six experts
and focuses purely on task decomposition into named part families with
instance counts, parent relationships, and symmetry groups.
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


class Designer(Expert):
    """Task decomposer that identifies logical part families in a 3D model.

    The Designer analyses a user's natural-language description of a 3D
    object and produces a structured decomposition into independently
    model-able part families with appropriate parent-child relationships
    and symmetry assignments.
    """

    role_name: str = "designer"
    description: str = (
        "Decomposes a user task into logical part families with instance "
        "counts, parent relationships, and symmetry groups."
    )
    capabilities: list[str] = [
        "task decomposition",
        "part family identification",
        "symmetry group assignment",
        "parent-child hierarchy design",
    ]
    system_prompt: str = ""

    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        """Produce a decomposition message based on the conversation history.

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
            The Designer's decomposition as a conversation message, typically
            containing a JSON ``part_families`` payload in its ``content``.
        """
        message = run_single_expert_turn(self, conversation, context, llm)
        logger.warning(
            "[EXPERT] %s turn=%d | response chars=%d",
            self.role_name, len(conversation.messages) + 1, len(message.content),
        )
        return message
