"""Three-tier expert memory system.

Tiers:
- ephemeral: cleared by reset_limits() — current round reasoning
- persistent: cleared by conversation delete — confirmed decisions
- permanent: never cleared (Stage 5+) — cross-session learning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExpertMemory:
    """Three-tier memory for expert state.

    Tiers:
    - ephemeral: cleared by reset_limits() — current round reasoning
    - persistent: cleared by conversation delete — confirmed decisions
    - permanent: never cleared (Stage 5+) — cross-session learning
    """

    ephemeral: dict[str, Any] = field(default_factory=dict)
    persistent: dict[str, Any] = field(default_factory=dict)
    permanent: dict[str, Any] = field(default_factory=dict)

    def clear_ephemeral(self) -> None:
        """Clear the ephemeral tier (current round reasoning)."""
        self.ephemeral.clear()

    def clear_persistent(self) -> None:
        """Clear the persistent tier (confirmed decisions)."""
        self.persistent.clear()

    def get(self, key: str, tier: str = "ephemeral") -> Any:
        """Retrieve a value from the specified memory tier.

        Parameters
        ----------
        key:
            The key to look up.
        tier:
            Memory tier name: ``"ephemeral"``, ``"persistent"``, or ``"permanent"``.

        Returns
        -------
        Any
            The stored value, or ``None`` if not found.
        """
        store = getattr(self, tier, self.ephemeral)
        return store.get(key)

    def set(self, key: str, value: Any, tier: str = "ephemeral") -> None:
        """Store a value in the specified memory tier.

        Parameters
        ----------
        key:
            The key to store under.
        value:
            The value to store.
        tier:
            Memory tier name: ``"ephemeral"``, ``"persistent"``, or ``"permanent"``.
        """
        store = getattr(self, tier, self.ephemeral)
        store[key] = value
