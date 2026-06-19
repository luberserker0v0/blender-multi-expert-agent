"""Simple dict-based registry for Expert instances.

Stage 2 implementation — no memory tiers, no capability filtering.
ExpertMemory integration deferred to Stage 4b.
"""

from __future__ import annotations

from typing import Any

from ai_3d_modeling_agent.multi_expert.core.expert import Expert


class ExpertRegistry:
    """Simple dict-based registry for Expert instances.

    Maps ``role_name`` → ``Expert`` instance.  Thin wrapper around a plain
    dict — no persistence, no capability querying, no memory tiers.

    Stage 2 implementation — no memory tiers, no capability filtering.
    ExpertMemory integration deferred to Stage 4b.
    """

    def __init__(self) -> None:
        self._experts: dict[str, Expert] = {}

    def register(self, expert: Expert) -> None:
        """Register an expert instance by its ``role_name``.

        Parameters
        ----------
        expert:
            An ``Expert`` subclass instance.  Its ``role_name`` attribute is
            used as the registry key.

        Raises
        ------
        ValueError
            If an expert with the same ``role_name`` is already registered.
        """
        role = expert.role_name
        if role in self._experts:
            msg = f"Expert with role_name {role!r} is already registered"
            raise ValueError(msg)
        self._experts[role] = expert

    def get(self, role_name: str) -> Expert | None:
        """Retrieve an expert by role name.

        Parameters
        ----------
        role_name:
            The role name to look up.

        Returns
        -------
        Expert or None
            The registered expert, or ``None`` if not found.
        """
        return self._experts.get(role_name)

    def list_roles(self) -> list[str]:
        """Return all registered role names.

        Returns
        -------
        list[str]
            Sorted list of registered role names.
        """
        return sorted(self._experts.keys())

    def has_role(self, role_name: str) -> bool:
        """Check if a role is registered.

        Parameters
        ----------
        role_name:
            The role name to check.

        Returns
        -------
        bool
            ``True`` if an expert with that role name is registered.
        """
        return role_name in self._experts

    @property
    def count(self) -> int:
        """Number of registered experts."""
        return len(self._experts)
