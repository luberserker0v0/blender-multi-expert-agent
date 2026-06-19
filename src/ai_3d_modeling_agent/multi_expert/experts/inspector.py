"""Inspector expert verifies the final assembly against specifications."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_3d_modeling_agent.multi_expert.core.expert import Expert
from ai_3d_modeling_agent.multi_expert.experts._turn import run_single_expert_turn

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_3d_modeling_agent.multi_expert.core.conversation import Message
    from ai_3d_modeling_agent.multi_expert.core.expert import LlmInterface


class Inspector(Expert):
    """Final assembly validator that compares built scene against specs."""

    role_name: str = "inspector"
    description: str = (
        "Verifies the final assembly matches specifications: dimensions, "
        "positions, instance counts, and symmetry correctness."
    )
    capabilities: list[str] = [
        "dimensional verification",
        "instance count checking",
        "attachment alignment validation",
        "symmetry correctness checking",
        "final assembly sign-off",
    ]
    system_prompt: str = ""

    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        message = run_single_expert_turn(self, conversation, context, llm)
        logger.warning(
            "[EXPERT] %s turn=%d | response chars=%d",
            self.role_name, len(conversation.messages) + 1, len(message.content),
        )
        return message
