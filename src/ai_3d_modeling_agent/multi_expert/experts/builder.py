"""Builder expert translates specifications into Blender object operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_3d_modeling_agent.multi_expert.core.expert import Expert
from ai_3d_modeling_agent.multi_expert.experts._turn import run_single_expert_turn

if TYPE_CHECKING:
    from ai_3d_modeling_agent.multi_expert.core.conversation import Message
    from ai_3d_modeling_agent.multi_expert.core.expert import LlmInterface


class Builder(Expert):
    """Blender geometry builder that creates primitives per part spec."""

    role_name: str = "builder"
    description: str = (
        "Creates Blender primitives, places instances, and applies transforms "
        "to match Markdown design/spec/build plans."
    )
    capabilities: list[str] = [
        "primitive creation",
        "blender object construction",
        "spatial placement",
        "attachment alignment",
        "transform application",
        "mesh dimensioning",
    ]
    system_prompt: str = ""

    def speak(
        self,
        conversation: "Conversation",
        context: "PhaseContext",
        llm: LlmInterface,
    ) -> "Message":
        return run_single_expert_turn(self, conversation, context, llm)
