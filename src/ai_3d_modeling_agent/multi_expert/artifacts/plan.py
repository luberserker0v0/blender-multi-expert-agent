"""Planning phase artifact for execution order and rationale."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class PlanArtifact:
    """Planning phase output for build order, world positions, and rationale."""

    spec_id: str = ""
    """Links to the source SpecArtifact.blueprint_id."""

    dag: Any = None
    """Directed acyclic graph describing dependency order."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    """Build and assembly steps in execution order."""

    world_positions: dict[str, list[float]] = field(default_factory=dict)
    """Computed world positions keyed by part family."""

    summary: str = ""
    """Human-readable summary of the accepted planning decisions."""

    execution_rationale: list[str] = field(default_factory=list)
    """Short rationale notes explaining why this order is safe and practical."""

    build_responsibilities: list[dict[str, Any]] = field(default_factory=list)
    """Planning items that the Builder is expected to resolve during geometry creation."""

    assembly_responsibilities: list[dict[str, Any]] = field(default_factory=list)
    """Planning items that the Assembler is expected to resolve during placement and hierarchy work.

    Each item may include structured execution-intent fields such as:
    - ``target_parent_family``
    - ``attachment_target_family``
    - ``attachment_target_point_id``
    - ``local_anchor_point_id``
    - ``placement_rule``
    - ``required_parenting``
    """

    dependency_summary: list[str] = field(default_factory=list)
    """Human-readable dependency highlights extracted from the planning phase."""

    ordering_constraints: list[dict[str, Any]] = field(default_factory=list)
    """Structured ordering/dependency constraints that Build and Assemble must respect."""

    risk_hotspots: list[dict[str, Any]] = field(default_factory=list)
    """Capability-boundary or sequencing risks that remain relevant after planning."""

    open_issues: list[str] = field(default_factory=list)
    """Planning issues intentionally left unresolved at phase close."""

    failure_notes: list[str] = field(default_factory=list)
    """Non-empty only when partial recovery occurred."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_id": self.spec_id,
            "dag": _serialize_value(self.dag),
            "steps": _serialize_value(self.steps),
            "world_positions": _serialize_value(self.world_positions),
            "summary": self.summary,
            "execution_rationale": list(self.execution_rationale),
            "build_responsibilities": _serialize_value(self.build_responsibilities),
            "assembly_responsibilities": _serialize_value(self.assembly_responsibilities),
            "dependency_summary": list(self.dependency_summary),
            "ordering_constraints": _serialize_value(self.ordering_constraints),
            "risk_hotspots": _serialize_value(self.risk_hotspots),
            "open_issues": list(self.open_issues),
            "failure_notes": list(self.failure_notes),
        }


def _serialize_value(value: Any) -> Any:
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    return value
