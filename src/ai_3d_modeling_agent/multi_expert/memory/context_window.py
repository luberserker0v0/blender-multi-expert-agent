"""Context window strategy — conversation summarization policy.

Placeholder for conversation summarization strategy.
Deferred to Stage 4b — currently a no-op pass-through.
"""

from __future__ import annotations

from typing import Any


class ContextWindowStrategy:
    """Placeholder for conversation summarization strategy.

    Deferred to Stage 4b — currently a no-op pass-through.
    """

    def summarize(self, conversation: Any) -> str:
        """Summarize a conversation history.

        Parameters
        ----------
        conversation:
            The conversation object to summarize.

        Returns
        -------
        str
            A summary string. Currently returns a no-op placeholder.
        """
        return "No summary"

    def should_summarize(self, token_count: int, max_tokens: int = 8192) -> bool:
        """Determine whether the conversation should be summarized.

        Parameters
        ----------
        token_count:
            Current token count of the conversation.
        max_tokens:
            Maximum token threshold before summarization is triggered.

        Returns
        -------
        bool
            ``True`` if ``token_count`` exceeds ``max_tokens``.
        """
        return token_count > max_tokens
