"""Reviewer expert — critically evaluates outputs of other experts.

The Reviewer validates that part family decompositions, geometry specs,
build instructions, and assembly plans are internally consistent and
correct.  It checks for issues such as circular parent references,
missing family references, symmetry / count mismatches, root constraint
violations, and dimensional inconsistencies.
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


class Reviewer(Expert):
    """Cross-cutting quality checker across all expert outputs.

    The Reviewer examines the outputs produced by the Designer, Specifier,
    Builder, and Inspector experts and reports any consistency,
    correctness, or completeness issues found.  Its feedback drives
    iterative refinement rounds in the pipeline.
    """

    role_name: str = "reviewer"
    description: str = (
        "Critically evaluates expert outputs for correctness, consistency, "
        "and completeness across the entire pipeline."
    )
    capabilities: list[str] = [
        "consistency checking",
        "constraint validation",
        "cross-expert verification",
        "issue reporting",
    ]
    system_prompt: str = ""

    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        """Produce a review / critique message.

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
            The Reviewer's critique as a conversation message, listing any
            issues found across expert outputs or confirming correctness.
        """
        message = run_single_expert_turn(self, conversation, context, llm)
        logger.warning(
            "[EXPERT] %s turn=%d | response chars=%d",
            self.role_name, len(conversation.messages) + 1, len(message.content),
        )
        return message
