"""Scope engine — determines which phases need re-run when an artifact changes.

When a rejection triggers a correction, the ScopeEngine computes the
blast radius: which downstream phases are affected and in what order
they should be re-executed.
"""

from __future__ import annotations

from typing import Any


class ScopeEngine:
    """Determines which phases need re-run when an artifact changes."""

    def compute_impact(
        self, changed_artifact_type: str, pipeline_state: dict
    ) -> list[str]:
        """Return list of phase names affected by a change to the given artifact.

        Parameters
        ----------
        changed_artifact_type:
            The artifact type that was modified (e.g. ``"design"``, ``"spec"``).
        pipeline_state:
            Current pipeline state dict (reserved for future use).

        Returns
        -------
        list[str]
            Phase names that must be re-executed, unordered.
        """
        impact_map: dict[str, list[str]] = {
            "design": ["design", "spec", "plan", "build", "assemble", "validate"],
            "spec": ["spec", "plan", "build", "assemble", "validate"],
            "plan": ["plan", "build", "assemble", "validate"],
            "build": ["build", "assemble", "validate"],
            "assembly": ["assemble", "validate"],
            "validation": ["validate"],
        }
        return impact_map.get(changed_artifact_type, [])

    def cascade_strategy(self, impacted_phases: list[str]) -> list[str]:
        """Order impacted phases for re-execution (topological).

        Parameters
        ----------
        impacted_phases:
            Unordered list of phase names from ``compute_impact``.

        Returns
        -------
        list[str]
            Topologically ordered list of phases to re-run.
        """
        phase_order = ["design", "spec", "plan", "build", "assemble", "validate"]
        return [p for p in phase_order if p in impacted_phases]
