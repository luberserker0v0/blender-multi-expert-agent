"""Message and Conversation dataclasses for the multi-expert pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A single message exchanged during a multi-expert conversation phase.

    Attributes:
        speaker: Role or name of the expert who sent the message.
        turn: Sequential turn number within the phase.
        phase: Name of the conversation phase this message belongs to.
        content: The textual content of the message.
        structured: Optional structured data accompanying the message (e.g. JSON).
    """

    speaker: str
    turn: int
    phase: str
    content: str
    structured: dict | None = None


@dataclass
class Conversation:
    """Represents a multi-turn conversation within a single pipeline phase.

    Attributes:
        phase_name: Name of the pipeline phase (e.g. "analysis", "critique").
        messages: Ordered list of exchanged messages.
        context: Forward reference to PhaseContext (defined in Stage 3).
        summary_cache: Mapping of summary keys to cached summary text.
        full_summary: The complete summary of this conversation, if generated.
    """

    phase_name: str
    messages: list[Message] = field(default_factory=list)
    context: Any = None  # forward ref to PhaseContext (Stage 3)
    summary_cache: dict[str, str] = field(default_factory=dict)
    full_summary: str | None = None

    def append(self, msg: Message) -> None:
        """Append a message to the conversation.

        Args:
            msg: The Message instance to append.
        """
        self.messages.append(msg)

    def summary(self) -> str:
        """Return the conversation summary.

        Returns:
            The full summary if available, otherwise "No summary".
        """
        if self.full_summary:
            return self.full_summary
        return "No summary"

    def for_expert(self, role: str) -> str:
        """Format all messages from a specific speaker into a single string.

        Args:
            role: The speaker role to filter by.

        Returns:
            Newline-separated string of filtered messages.
        """
        filtered = [m for m in self.messages if m.speaker == role]
        return "\n".join(
            f"[{m.speaker}|turn {m.turn}|{m.phase}] {m.content}"
            for m in filtered
        )

    def token_estimate(self) -> int:
        """Rough token count estimate for this conversation.

        Uses a simple character-based heuristic (chars / 4).

        Returns:
            Estimated number of tokens.
        """
        return len(str(self.messages)) // 4
