"""Pipeline checkpoint — schema for persisting pipeline state.

Resume logic is deferred to Stage 5. This module defines the
checkpoint data structure only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineCheckpoint:
    """Schema for checkpointing pipeline state.

    Resume logic is deferred to Stage 5.
    """

    session_id: str
    task_prompt: str
    phase_statuses: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    revision_count: int = 0
    timestamp: str = ""
