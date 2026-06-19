"""ConstraintChecker — orchestrator for constraint validation plugins.

Usage::

    from ai_3d_modeling_agent.multi_expert.constraints import ConstraintChecker
    from .plugins import PrimitiveSupportedChecker

    checker = ConstraintChecker()
    checker.register(PrimitiveSupportedChecker())

    violations = checker.run(spec_artifact, manifest_data)
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Protocol

from .violations import ConstraintViolation, Severity


class ConstraintPlugin(Protocol):
    """Protocol that every constraint plugin must satisfy.

    A plugin is a stateless check with a ``name`` identifier and a
    ``check`` method.  Plugins that require no LLM call should set
    ``quick = True`` so that ``run_quick()`` includes them.
    """

    name: str
    """Unique identifier for this plugin, e.g. ``"bbox_range"``."""

    def check(
        self,
        artifact: Any,
        manifests: Any | None = None,
    ) -> list[ConstraintViolation]:
        """Run checks on *artifact* and return any violations found.

        Parameters
        ----------
        artifact:
            The artifact to validate (e.g. a ``SpecArtifact`` or raw dict).
        manifests:
            Optional manifests or configuration data containing
            supported primitives, bbox ranges, etc.

        Returns
        -------
        list[ConstraintViolation]
            Empty list when no violations are detected.
        """
        ...


class ConstraintChecker:
    """Orchestrates constraint validation across registered plugins.

    The checker maintains an ordered registry of plugins.  The main
    entry point is :meth:`run`, which executes every registered plugin
    and aggregates the results.  :meth:`run_quick` and
    :meth:`check_corrections` provide filtered / copy-based workflows
    for interactive correction loops.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, ConstraintPlugin] = {}

    # ── registry ──────────────────────────────────────────────────────

    def register(self, plugin: ConstraintPlugin) -> None:
        """Register a single plugin keyed by ``plugin.name``.

        If a plugin with the same name already exists it is replaced.
        """
        self._plugins[plugin.name] = plugin

    # ── full run ──────────────────────────────────────────────────────

    def run(
        self,
        artifact: Any,
        manifests: Any | None = None,
    ) -> list[ConstraintViolation]:
        """Run **all** registered plugins and return aggregated violations.

        Parameters
        ----------
        artifact:
            The artifact to validate.
        manifests:
            Optional manifests forwarded to each plugin.

        Returns
        -------
        list[ConstraintViolation]
            Every violation from every plugin.  Plugins that raise an
            unexpected exception produce a single ERROR-level violation
            so that a single buggy plugin does not take down the run.
        """
        all_violations: list[ConstraintViolation] = []
        for name in sorted(self._plugins):
            plugin = self._plugins[name]
            try:
                violations = plugin.check(artifact, manifests)
                all_violations.extend(violations)
            except Exception as exc:
                all_violations.append(
                    ConstraintViolation(
                        rule=name,
                        detail=f"Plugin raised an unexpected error: {exc}",
                        severity=Severity.ERROR,
                    )
                )
        return all_violations

    # ── quick run (structural-only, no LLM) ───────────────────────────

    def run_quick(
        self,
        artifact: Any,
        manifests: Any | None = None,
    ) -> list[ConstraintViolation]:
        """Run only plugins that are fast/structural (no LLM needed).

        A plugin is included when its ``quick`` attribute is truthy
        (``True`` by default, set at the class level).
        """
        all_violations: list[ConstraintViolation] = []
        for name in sorted(self._plugins):
            plugin = self._plugins[name]
            if not getattr(plugin, "quick", True):
                continue
            try:
                violations = plugin.check(artifact, manifests)
                all_violations.extend(violations)
            except Exception as exc:
                all_violations.append(
                    ConstraintViolation(
                        rule=name,
                        detail=f"Plugin raised an unexpected error: {exc}",
                        severity=Severity.ERROR,
                    )
                )
        return all_violations

    # ── corrections workflow ──────────────────────────────────────────

    def check_corrections(
        self,
        corrections: Callable[[Any], None],
        artifact: Any,
        manifests: Any | None = None,
    ) -> list[ConstraintViolation]:
        """Apply *corrections* to a deep copy of *artifact*, then run quick plugins.

        This lets the caller propose edits and see what violations
        remain **without** mutating the original artifact.

        Parameters
        ----------
        corrections:
            Callable that receives a **deep copy** of *artifact* and
            mutates it in-place (e.g. adjusts bbox dimensions).
        artifact:
            Original artifact to copy.
        manifests:
            Optional manifests forwarded to each plugin.

        Returns
        -------
        list[ConstraintViolation]
            Violations detected on the corrected copy.
        """
        artifact_copy = copy.deepcopy(artifact)
        corrections(artifact_copy)
        return self.run_quick(artifact_copy, manifests)
