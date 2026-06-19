"""Preview rendering for the user review gate.

Provides the ``PreviewRenderer`` protocol and a default ASCII/text
implementation so that users can inspect draft artifacts before approving
or requesting corrections.
"""

from __future__ import annotations

from typing import Any, Protocol


class PreviewRenderer(Protocol):
    """Protocol for rendering an artifact into a human-readable preview.

    Implementations may produce ASCII art, HTML, Markdown, or any other
    text-based representation suitable for display in a review UI.
    """

    def render(self, artifact: Any) -> str:
        """Render *artifact* as a human-readable string.

        Parameters
        ----------
        artifact:
            The draft artifact to preview (e.g. ``DesignArtifact``,
            ``SpecArtifact``).

        Returns
        -------
        str
            A text representation of the artifact.
        """
        ...


class AsciiPreviewRenderer:
    """Render an artifact as plain-text / ASCII preview.

    Default implementation that delegates to ``str(artifact)``.  Suitable
    for CLI-based review flows and debugging.  Replace with a richer
    renderer (HTML, Markdown) for GUI front-ends.
    """

    def render(self, artifact: Any) -> str:
        """Return a simple text representation of *artifact*.

        Parameters
        ----------
        artifact:
            The draft artifact to preview.

        Returns
        -------
        str
            ``str(artifact)`` — the dataclass default ``__repr__`` or a
            custom ``__str__`` if the artifact defines one.
        """
        return str(artifact)
