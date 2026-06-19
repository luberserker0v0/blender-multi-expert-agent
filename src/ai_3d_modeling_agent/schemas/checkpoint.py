"""Checkpoint schemas for the D&C pipeline.

Domain: pipeline persistence — per-part build state and the top-level
checkpoint that enables resume after interruption.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PartCheckpoint:
    """Checkpoint for a single part family's build state.

    Persisted per-part so that individual parts can be skipped or
    retried without losing the state of completed parts.
    """

    version: int = 1
    part_name: str = ""
    part_family: Dict[str, Any] = field(default_factory=dict)  # serialized PartFamily
    part_spec: Dict[str, Any] = field(default_factory=dict)  # serialized PartSpec

    # Build state
    status: str = "pending"  # "pending" | "building" | "approved" | "failed" | "skipped"
    source_object_name: str = ""
    instance_object_names: List[str] = field(default_factory=list)

    # Refinement metadata
    refinement_rounds: int = 0
    final_capture_path: str = ""
    action_history: List[Dict[str, Any]] = field(default_factory=list)

    # Failure info
    failure_policy: str = "RETRYABLE"  # "FATAL" | "RETRYABLE" | "DEGRADE"
    failure_reason: str = ""
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "part_name": self.part_name,
            "part_family": dict(self.part_family),
            "part_spec": dict(self.part_spec),
            "status": self.status,
            "source_object_name": self.source_object_name,
            "instance_object_names": list(self.instance_object_names),
            "refinement_rounds": self.refinement_rounds,
            "final_capture_path": self.final_capture_path,
            "action_history": list(self.action_history),
            "failure_policy": self.failure_policy,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PartCheckpoint":
        return cls(
            version=d.get("version", 1),
            part_name=d.get("part_name", ""),
            part_family=dict(d.get("part_family", {})),
            part_spec=dict(d.get("part_spec", {})),
            status=d.get("status", "pending"),
            source_object_name=d.get("source_object_name", ""),
            instance_object_names=list(d.get("instance_object_names", [])),
            refinement_rounds=d.get("refinement_rounds", 0),
            final_capture_path=d.get("final_capture_path", ""),
            action_history=list(d.get("action_history", [])),
            failure_policy=d.get("failure_policy", "RETRYABLE"),
            failure_reason=d.get("failure_reason", ""),
            retry_count=d.get("retry_count", 0),
        )


@dataclass
class DnCCheckpoint:
    """Top-level checkpoint for the entire D&C pipeline.

    Captures all phase outputs and per-part build state so the pipeline
    can resume from any phase after an interruption.
    """

    version: int = 1
    session_id: str = ""
    task_prompt: str = ""

    # Phase tracking
    current_phase: str = (
        "decompose"  # "decompose" | "specify" | "plan" | "build" | "assemble" | "validate"
    )

    # Phase 1-2 outputs (serialized as dicts for clean JSON round-trip)
    part_families: List[Dict[str, Any]] = field(default_factory=list)
    part_specs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    assembly_plan: Dict[str, Any] = field(default_factory=dict)

    # Per-part checkpoints
    part_checkpoints: Dict[str, PartCheckpoint] = field(default_factory=dict)

    # Assembly state
    completed_steps: List[int] = field(default_factory=list)
    current_step: int = 0

    # Validation phase
    validation_errors: List[str] = field(default_factory=list)

    # Final result
    completed: bool = False
    success: bool = False
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "task_prompt": self.task_prompt,
            "current_phase": self.current_phase,
            "part_families": list(self.part_families),
            "part_specs": {k: dict(v) for k, v in self.part_specs.items()},
            "assembly_plan": dict(self.assembly_plan),
            "part_checkpoints": {
                k: v.to_dict() for k, v in self.part_checkpoints.items()
            },
            "completed_steps": list(self.completed_steps),
            "current_step": self.current_step,
            "validation_errors": list(self.validation_errors),
            "completed": self.completed,
            "success": self.success,
            "result": dict(self.result) if self.result else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DnCCheckpoint":
        return cls(
            version=d.get("version", 1),
            session_id=d.get("session_id", ""),
            task_prompt=d.get("task_prompt", ""),
            current_phase=d.get("current_phase", "decompose"),
            part_families=list(d.get("part_families", [])),
            part_specs={
                k: dict(v) for k, v in d.get("part_specs", {}).items()
            },
            assembly_plan=dict(d.get("assembly_plan", {})),
            part_checkpoints={
                k: PartCheckpoint.from_dict(v)
                for k, v in d.get("part_checkpoints", {}).items()
            },
            completed_steps=list(d.get("completed_steps", [])),
            current_step=d.get("current_step", 0),
            validation_errors=list(d.get("validation_errors", [])),
            completed=d.get("completed", False),
            success=d.get("success", False),
            result=dict(d["result"]) if d.get("result") else None,
        )
