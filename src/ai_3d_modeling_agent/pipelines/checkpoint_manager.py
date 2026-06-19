"""Checkpoint persistence for the D&C pipeline.

Supports per-part and top-level checkpoints so the pipeline can resume
from any phase after interruption. Checkpoints are stored as flat JSON
files (one per session + one per part) — no .blend serialization needed.
"""

import json
import os
import shutil
from typing import Any, Dict, List, Optional

from ai_3d_modeling_agent.schemas.checkpoint import DnCCheckpoint, PartCheckpoint


class CheckpointManager:
    """Saves and loads D&C pipeline checkpoints.

    Directory layout::

        <checkpoint_dir>/
            <session_id>.json              # top-level DnCCheckpoint
            <session_id>/
                <part_name>.json          # per-part PartCheckpoint

    Design decisions:
    - Flat JSON files (no DB dependency, easy to inspect / debug)
    - Per-part files so individual parts can be saved without rewriting the
      entire checkpoint (avoids race conditions during parallel build)
    - No .blend serialization: rebuild from primitive + scale on resume,
      which is faster and more reliable than serializing scene state.
    """

    DEFAULT_CHECKPOINT_DIR = "data/runtime/checkpoints/dnc"

    def __init__(self, checkpoint_dir: Optional[str] = None):
        self._checkpoint_dir = checkpoint_dir or self.DEFAULT_CHECKPOINT_DIR

    # ── helpers ──────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        os.makedirs(self._checkpoint_dir, exist_ok=True)

    def _top_level_path(self, session_id: str) -> str:
        return os.path.join(self._checkpoint_dir, f"{session_id}.json")

    def _part_dir(self, session_id: str) -> str:
        return os.path.join(self._checkpoint_dir, session_id)

    def _part_path(self, session_id: str, part_name: str) -> str:
        return os.path.join(self._part_dir(session_id), f"{part_name}.json")

    # ── top-level checkpoint ─────────────────────────────────────────

    def save_checkpoint(self, session_id: str, checkpoint: DnCCheckpoint) -> str:
        """Save the top-level D&C checkpoint. Returns the file path."""
        self._ensure_dir()
        path = self._top_level_path(session_id)
        with open(path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        return path

    def load_checkpoint(self, session_id: str) -> Optional[DnCCheckpoint]:
        """Load the top-level D&C checkpoint. Returns None if not found."""
        path = self._top_level_path(session_id)
        if not os.path.isfile(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        return DnCCheckpoint.from_dict(data)

    def checkpoint_exists(self, session_id: str) -> bool:
        """Check whether a top-level checkpoint exists for this session."""
        return os.path.isfile(self._top_level_path(session_id))

    def delete_checkpoint(self, session_id: str) -> None:
        """Delete all checkpoint data for a session (top-level + per-part)."""
        top = self._top_level_path(session_id)
        if os.path.isfile(top):
            os.remove(top)
        part_dir = self._part_dir(session_id)
        if os.path.isdir(part_dir):
            shutil.rmtree(part_dir)

    # ── per-part checkpoint ──────────────────────────────────────────

    def save_part_checkpoint(
        self, session_id: str, part_name: str, checkpoint: PartCheckpoint
    ) -> str:
        """Save a per-part checkpoint. Returns the file path."""
        part_dir = self._part_dir(session_id)
        os.makedirs(part_dir, exist_ok=True)
        path = self._part_path(session_id, part_name)
        with open(path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)
        return path

    def load_part_checkpoint(
        self, session_id: str, part_name: str
    ) -> Optional[PartCheckpoint]:
        """Load a per-part checkpoint. Returns None if not found."""
        path = self._part_path(session_id, part_name)
        if not os.path.isfile(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        return PartCheckpoint.from_dict(data)

    def list_part_checkpoints(self, session_id: str) -> Dict[str, PartCheckpoint]:
        """Load all per-part checkpoints for a session."""
        part_dir = self._part_dir(session_id)
        if not os.path.isdir(part_dir):
            return {}
        result: Dict[str, PartCheckpoint] = {}
        for filename in os.listdir(part_dir):
            if filename.endswith(".json"):
                part_name = filename[: -5]  # strip ".json"
                checkpoint = self.load_part_checkpoint(session_id, part_name)
                if checkpoint is not None:
                    result[part_name] = checkpoint
        return result

    # ── resume ───────────────────────────────────────────────────────

    def get_resume_state(self, session_id: str) -> Optional[DnCCheckpoint]:
        """Return the checkpoint for resume, or None if no checkpoint exists."""
        return self.load_checkpoint(session_id)

    def get_approved_part_names(self, session_id: str) -> List[str]:
        """Return names of parts that are fully built and approved."""
        checkpoint = self.load_checkpoint(session_id)
        if checkpoint is None:
            return []
        return [
            name
            for name, pc in checkpoint.part_checkpoints.items()
            if pc.status == "approved"
        ]

    def get_failed_part_names(
        self, session_id: str
    ) -> List[str]:
        """Return names of parts that failed and are retryable."""
        checkpoint = self.load_checkpoint(session_id)
        if checkpoint is None:
            return []
        return [
            name
            for name, pc in checkpoint.part_checkpoints.items()
            if pc.status == "failed" and pc.failure_policy == "RETRYABLE"
        ]

    def get_completed_step_indices(self, session_id: str) -> List[int]:
        """Return assembly step indices that were already placed."""
        checkpoint = self.load_checkpoint(session_id)
        if checkpoint is None:
            return []
        return list(checkpoint.completed_steps)

    def resume_summary(self, session_id: str) -> Dict[str, Any]:
        """Return a human-readable dict summarising the resume state."""
        checkpoint = self.load_checkpoint(session_id)
        if checkpoint is None:
            return {"resumable": False, "reason": "No checkpoint found."}

        approved = self.get_approved_part_names(session_id)
        failed = self.get_failed_part_names(session_id)
        completed_steps = self.get_completed_step_indices(session_id)

        return {
            "resumable": True,
            "session_id": session_id,
            "current_phase": checkpoint.current_phase,
            "approved_parts": approved,
            "failed_retryable_parts": failed,
            "completed_assembly_steps": completed_steps,
            "total_part_families": len(checkpoint.part_families),
        }
