"""Planner expert for moderated planning meetings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ai_3d_modeling_agent.multi_expert.core.expert import Expert
from ai_3d_modeling_agent.multi_expert.experts._turn import run_single_expert_turn

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ai_3d_modeling_agent.multi_expert.core.conversation import Message
    from ai_3d_modeling_agent.multi_expert.core.expert import LlmInterface


class Planner(Expert):
    role_name: str = "planner"
    description: str = "Turns an accepted specification into an execution plan with rationale."
    capabilities: list[str] = [
        "execution planning",
        "dependency analysis",
        "assembly ordering",
        "risk identification",
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
