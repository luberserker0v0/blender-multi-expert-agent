"""Unit tests for CheckpointManager.

Covers all 13 public methods of CheckpointManager including
construction, top-level checkpoint I/O, per-part checkpoint I/O,
resume helpers, and edge cases. All tests use real filesystem
operations on temporary directories for isolation.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "src")

from ai_3d_modeling_agent.pipelines.checkpoint_manager import CheckpointManager
from ai_3d_modeling_agent.schemas.checkpoint import DnCCheckpoint, PartCheckpoint


class TestCheckpointManager(unittest.TestCase):
    """Full coverage for CheckpointManager — construction, I/O, resume."""

    def setUp(self):
        """Create a temporary checkpoint directory for each test."""
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.checkpoint_dir = self.tmp_dir.name
        self.mgr = CheckpointManager(checkpoint_dir=self.checkpoint_dir)

        # Convenience: a minimal DnCCheckpoint with no parts
        self.base_checkpoint = DnCCheckpoint(
            session_id="test-session",
            task_prompt="build a chair",
            current_phase="decompose",
            part_families=[{"name": "seat", "count": 1}],
            completed_steps=[],
            current_step=0,
        )

    def tearDown(self):
        """Clean up the temporary directory."""
        self.tmp_dir.cleanup()

    # ── construction ───────────────────────────────────────────────

    def test_default_checkpoint_dir(self):
        """Default checkpoint dir matches the class constant."""
        mgr = CheckpointManager()
        self.assertEqual(mgr._checkpoint_dir, CheckpointManager.DEFAULT_CHECKPOINT_DIR)

    def test_custom_checkpoint_dir(self):
        """Custom checkpoint_dir is used when provided."""
        mgr = CheckpointManager(checkpoint_dir=self.checkpoint_dir)
        self.assertEqual(mgr._checkpoint_dir, self.checkpoint_dir)

    # ── top-level checkpoint ───────────────────────────────────────

    def test_save_and_load_checkpoint(self):
        """Round-trip: save then load returns an identical DnCCheckpoint."""
        cp = DnCCheckpoint(
            session_id="sess-1",
            task_prompt="build a chair",
            current_phase="decompose",
            part_families=[{"name": "seat", "count": 1}],
        )
        path = self.mgr.save_checkpoint("sess-1", cp)

        self.assertTrue(os.path.isfile(path))
        self.assertIn("sess-1.json", path)

        loaded = self.mgr.load_checkpoint("sess-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.session_id, "sess-1")
        self.assertEqual(loaded.task_prompt, "build a chair")
        self.assertEqual(loaded.current_phase, "decompose")
        self.assertEqual(loaded.part_families, [{"name": "seat", "count": 1}])

    def test_load_checkpoint_nonexistent_returns_none(self):
        """load_checkpoint returns None when no file exists."""
        loaded = self.mgr.load_checkpoint("no-such-session")
        self.assertIsNone(loaded)

    def test_checkpoint_exists_true_after_save(self):
        """checkpoint_exists returns True after saving."""
        self.mgr.save_checkpoint("exists-test", self.base_checkpoint)
        self.assertTrue(self.mgr.checkpoint_exists("exists-test"))

    def test_checkpoint_exists_false_by_default(self):
        """checkpoint_exists returns False before any save."""
        self.assertFalse(self.mgr.checkpoint_exists("no-session"))

    def test_checkpoint_exists_false_after_delete(self):
        """checkpoint_exists returns False after deleting a saved checkpoint."""
        self.mgr.save_checkpoint("del-me", self.base_checkpoint)
        self.mgr.delete_checkpoint("del-me")
        self.assertFalse(self.mgr.checkpoint_exists("del-me"))

    def test_delete_checkpoint_removes_top_level(self):
        """delete_checkpoint removes the top-level JSON file."""
        self.mgr.save_checkpoint("to-delete", self.base_checkpoint)
        top_path = self.mgr._top_level_path("to-delete")
        self.assertTrue(os.path.isfile(top_path))

        self.mgr.delete_checkpoint("to-delete")
        self.assertFalse(os.path.isfile(top_path))

    def test_delete_checkpoint_removes_part_dir(self):
        """delete_checkpoint removes the per-part directory."""
        part_cp = PartCheckpoint(part_name="leg")
        self.mgr.save_part_checkpoint("with-parts", "leg", part_cp)
        part_dir = self.mgr._part_dir("with-parts")
        self.assertTrue(os.path.isdir(part_dir))

        self.mgr.delete_checkpoint("with-parts")
        self.assertFalse(os.path.isdir(part_dir))

    def test_delete_checkpoint_removes_both(self):
        """delete_checkpoint removes both top-level and per-part files."""
        self.mgr.save_checkpoint("both", self.base_checkpoint)
        self.mgr.save_part_checkpoint("both", "leg", PartCheckpoint(part_name="leg"))
        self.mgr.save_part_checkpoint("both", "seat", PartCheckpoint(part_name="seat"))

        self.mgr.delete_checkpoint("both")

        self.assertFalse(self.mgr.checkpoint_exists("both"))
        self.assertFalse(os.path.isdir(self.mgr._part_dir("both")))

    def test_delete_checkpoint_nonexistent_does_not_error(self):
        """delete_checkpoint on a non-existent session runs without error."""
        # Should not raise FileNotFoundError or similar
        self.mgr.delete_checkpoint("never-existed")

    # ── per-part checkpoint ────────────────────────────────────────

    def test_save_and_load_part_checkpoint(self):
        """Round-trip: save then load a per-part PartCheckpoint."""
        part_cp = PartCheckpoint(
            part_name="leg",
            status="approved",
            source_object_name="leg_source",
            instance_object_names=["leg_inst_1", "leg_inst_2"],
            refinement_rounds=3,
            final_capture_path="captures/leg.png",
            action_history=[{"action": "scale", "value": 1.5}],
            failure_policy="RETRYABLE",
            failure_reason="",
            retry_count=0,
        )
        path = self.mgr.save_part_checkpoint("sess-parts", "leg", part_cp)

        self.assertTrue(os.path.isfile(path))
        self.assertIn("sess-parts", path)
        self.assertIn("leg.json", path)

        loaded = self.mgr.load_part_checkpoint("sess-parts", "leg")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.part_name, "leg")
        self.assertEqual(loaded.status, "approved")
        self.assertEqual(loaded.source_object_name, "leg_source")
        self.assertEqual(loaded.instance_object_names, ["leg_inst_1", "leg_inst_2"])
        self.assertEqual(loaded.refinement_rounds, 3)
        self.assertEqual(loaded.final_capture_path, "captures/leg.png")
        self.assertEqual(loaded.action_history, [{"action": "scale", "value": 1.5}])
        self.assertEqual(loaded.failure_policy, "RETRYABLE")
        self.assertEqual(loaded.retry_count, 0)

    def test_load_part_checkpoint_nonexistent_returns_none(self):
        """load_part_checkpoint returns None when part file is missing."""
        loaded = self.mgr.load_part_checkpoint("no-session", "no-part")
        self.assertIsNone(loaded)

    def test_list_part_checkpoints_multiple(self):
        """list_part_checkpoints returns all saved parts."""
        self.mgr.save_part_checkpoint("multi", "leg", PartCheckpoint(part_name="leg"))
        self.mgr.save_part_checkpoint("multi", "seat", PartCheckpoint(part_name="seat"))
        self.mgr.save_part_checkpoint("multi", "backrest", PartCheckpoint(part_name="backrest"))

        parts = self.mgr.list_part_checkpoints("multi")
        self.assertEqual(len(parts), 3)
        self.assertIn("leg", parts)
        self.assertIn("seat", parts)
        self.assertIn("backrest", parts)
        self.assertEqual(parts["leg"].part_name, "leg")
        self.assertEqual(parts["seat"].part_name, "seat")
        self.assertEqual(parts["backrest"].part_name, "backrest")

    def test_list_part_checkpoints_empty(self):
        """list_part_checkpoints returns empty dict when no parts exist."""
        parts = self.mgr.list_part_checkpoints("empty-session")
        self.assertEqual(parts, {})

    def test_list_part_checkpoints_ignores_non_json_files(self):
        """list_part_checkpoints skips files that don't end with .json."""
        part_dir = self.mgr._part_dir("mixed-files")
        os.makedirs(part_dir, exist_ok=True)

        # Save a real part checkpoint
        self.mgr.save_part_checkpoint("mixed-files", "real_part",
                                       PartCheckpoint(part_name="real_part"))
        # Drop a non-JSON file in the part directory
        with open(os.path.join(part_dir, "readme.txt"), "w") as f:
            f.write("not a checkpoint")

        parts = self.mgr.list_part_checkpoints("mixed-files")
        self.assertIn("real_part", parts)
        self.assertEqual(len(parts), 1)

    # ── resume helpers ─────────────────────────────────────────────

    def test_get_resume_state_returns_checkpoint(self):
        """get_resume_state returns the checkpoint when one exists."""
        cp = DnCCheckpoint(session_id="resume-me", task_prompt="test")
        self.mgr.save_checkpoint("resume-me", cp)
        state = self.mgr.get_resume_state("resume-me")
        self.assertIsNotNone(state)
        self.assertEqual(state.session_id, "resume-me")

    def test_get_resume_state_none_when_missing(self):
        """get_resume_state returns None when no checkpoint exists."""
        state = self.mgr.get_resume_state("no-such")
        self.assertIsNone(state)

    def test_get_approved_part_names(self):
        """get_approved_part_names returns only parts with status='approved'."""
        base = DnCCheckpoint(
            session_id="approve-test",
            task_prompt="test",
            part_checkpoints={
                "leg": PartCheckpoint(part_name="leg", status="approved"),
                "seat": PartCheckpoint(part_name="seat", status="approved"),
                "backrest": PartCheckpoint(part_name="backrest", status="pending"),
                "armrest": PartCheckpoint(part_name="armrest", status="failed"),
            },
        )
        self.mgr.save_checkpoint("approve-test", base)
        approved = self.mgr.get_approved_part_names("approve-test")
        self.assertCountEqual(approved, ["leg", "seat"])

    def test_get_approved_part_names_no_checkpoint(self):
        """get_approved_part_names returns [] when no checkpoint exists."""
        approved = self.mgr.get_approved_part_names("ghost")
        self.assertEqual(approved, [])

    def test_get_approved_part_names_empty_parts(self):
        """get_approved_part_names returns [] when no parts exist."""
        self.mgr.save_checkpoint("empty-parts", self.base_checkpoint)
        approved = self.mgr.get_approved_part_names("empty-parts")
        self.assertEqual(approved, [])

    def test_get_failed_part_names(self):
        """get_failed_part_names returns only failed+RETRYABLE parts."""
        base = DnCCheckpoint(
            session_id="fail-test",
            task_prompt="test",
            part_checkpoints={
                "leg": PartCheckpoint(part_name="leg", status="failed",
                                      failure_policy="RETRYABLE"),
                "seat": PartCheckpoint(part_name="seat", status="failed",
                                       failure_policy="FATAL"),
                "backrest": PartCheckpoint(part_name="backrest", status="approved"),
                "armrest": PartCheckpoint(part_name="armrest", status="failed",
                                          failure_policy="RETRYABLE"),
            },
        )
        self.mgr.save_checkpoint("fail-test", base)
        failed = self.mgr.get_failed_part_names("fail-test")
        self.assertCountEqual(failed, ["leg", "armrest"])

    def test_get_failed_part_names_no_checkpoint(self):
        """get_failed_part_names returns [] when no checkpoint exists."""
        failed = self.mgr.get_failed_part_names("ghost")
        self.assertEqual(failed, [])

    def test_get_failed_part_names_excludes_fatal(self):
        """Parts with failure_policy='FATAL' are excluded from failed list."""
        base = DnCCheckpoint(
            session_id="fatal-test",
            task_prompt="test",
            part_checkpoints={
                "leg": PartCheckpoint(part_name="leg", status="failed",
                                      failure_policy="FATAL"),
                "seat": PartCheckpoint(part_name="seat", status="failed",
                                       failure_policy="RETRYABLE"),
            },
        )
        self.mgr.save_checkpoint("fatal-test", base)
        failed = self.mgr.get_failed_part_names("fatal-test")
        self.assertEqual(failed, ["seat"])

    def test_get_completed_step_indices(self):
        """get_completed_step_indices returns the completed step indices."""
        base = DnCCheckpoint(
            session_id="steps-test",
            task_prompt="test",
            completed_steps=[1, 2, 3],
        )
        self.mgr.save_checkpoint("steps-test", base)
        steps = self.mgr.get_completed_step_indices("steps-test")
        self.assertEqual(steps, [1, 2, 3])

    def test_get_completed_step_indices_no_checkpoint(self):
        """get_completed_step_indices returns [] when no checkpoint."""
        steps = self.mgr.get_completed_step_indices("ghost")
        self.assertEqual(steps, [])

    def test_get_completed_step_indices_empty(self):
        """get_completed_step_indices returns [] with no completed steps."""
        self.mgr.save_checkpoint("no-steps", self.base_checkpoint)
        steps = self.mgr.get_completed_step_indices("no-steps")
        self.assertEqual(steps, [])

    # ── resume_summary ─────────────────────────────────────────────

    def test_resume_summary_resumable(self):
        """resume_summary returns a correct dict when checkpoint exists."""
        self.mgr.save_part_checkpoint(
            "summary-test", "leg",
            PartCheckpoint(part_name="leg", status="approved"),
        )
        self.mgr.save_part_checkpoint(
            "summary-test", "seat",
            PartCheckpoint(part_name="seat", status="failed",
                           failure_policy="RETRYABLE"),
        )
        base = DnCCheckpoint(
            session_id="summary-test",
            task_prompt="build a chair",
            current_phase="build",
            part_families=[{"name": "seat"}, {"name": "leg"}, {"name": "backrest"}],
            part_checkpoints={
                "leg": PartCheckpoint(part_name="leg", status="approved"),
                "seat": PartCheckpoint(part_name="seat", status="failed",
                                       failure_policy="RETRYABLE"),
            },
            completed_steps=[0, 1],
        )
        self.mgr.save_checkpoint("summary-test", base)

        summary = self.mgr.resume_summary("summary-test")
        self.assertTrue(summary["resumable"])
        self.assertEqual(summary["session_id"], "summary-test")
        self.assertEqual(summary["current_phase"], "build")
        self.assertEqual(summary["approved_parts"], ["leg"])
        self.assertEqual(summary["failed_retryable_parts"], ["seat"])
        self.assertEqual(summary["completed_assembly_steps"], [0, 1])
        self.assertEqual(summary["total_part_families"], 3)

    def test_resume_summary_not_resumable(self):
        """resume_summary returns resumable=False when no checkpoint."""
        summary = self.mgr.resume_summary("phantom")
        self.assertFalse(summary["resumable"])
        self.assertIn("reason", summary)
        self.assertEqual(summary["reason"], "No checkpoint found.")

    # ── edge cases ─────────────────────────────────────────────────

    def test_empty_checkpoint_dir_tolerated(self):
        """Operations on a nonexistent checkpoint dir do not raise errors."""
        # load / exists / delete on pristine dir
        self.assertIsNone(self.mgr.load_checkpoint("any"))
        self.assertFalse(self.mgr.checkpoint_exists("any"))
        self.mgr.delete_checkpoint("any")  # should not raise
        self.assertEqual(self.mgr.list_part_checkpoints("any"), {})
        self.assertIsNone(self.mgr.get_resume_state("any"))
        self.assertEqual(self.mgr.get_approved_part_names("any"), [])
        self.assertEqual(self.mgr.get_failed_part_names("any"), [])
        self.assertEqual(self.mgr.get_completed_step_indices("any"), [])

    def test_save_checkpoint_creates_dir_automatically(self):
        """save_checkpoint creates the checkpoint directory if it doesn't exist."""
        nested_dir = os.path.join(self.checkpoint_dir, "nested", "subdir")
        mgr = CheckpointManager(checkpoint_dir=nested_dir)
        mgr.save_checkpoint("deep-test", self.base_checkpoint)
        self.assertTrue(os.path.isfile(os.path.join(nested_dir, "deep-test.json")))

    def test_save_part_checkpoint_creates_dir_automatically(self):
        """save_part_checkpoint creates the part directory automatically."""
        part_cp = PartCheckpoint(part_name="leg")
        self.mgr.save_part_checkpoint("auto-dir", "leg", part_cp)
        part_dir = self.mgr._part_dir("auto-dir")
        self.assertTrue(os.path.isdir(part_dir))
        self.assertTrue(os.path.isfile(os.path.join(part_dir, "leg.json")))

    def test_multiple_sessions_do_not_interfere(self):
        """Checkpoints for different sessions are independent."""
        for i in range(3):
            cp = DnCCheckpoint(
                session_id=f"sess-{i}",
                task_prompt=f"task-{i}",
            )
            self.mgr.save_checkpoint(f"sess-{i}", cp)
            self.mgr.save_part_checkpoint(
                f"sess-{i}", "part_a",
                PartCheckpoint(part_name="part_a", status="approved"),
            )

        for i in range(3):
            loaded = self.mgr.load_checkpoint(f"sess-{i}")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.task_prompt, f"task-{i}")

            parts = self.mgr.list_part_checkpoints(f"sess-{i}")
            self.assertEqual(len(parts), 1)
            self.assertEqual(parts["part_a"].status, "approved")

    def test_overwrite_checkpoint_replaces_content(self):
        """Saving twice with the same session_id overwrites the old checkpoint."""
        cp1 = DnCCheckpoint(session_id="overwrite", task_prompt="version-1")
        self.mgr.save_checkpoint("overwrite", cp1)

        cp2 = DnCCheckpoint(session_id="overwrite", task_prompt="version-2")
        self.mgr.save_checkpoint("overwrite", cp2)

        loaded = self.mgr.load_checkpoint("overwrite")
        self.assertEqual(loaded.task_prompt, "version-2")

    def test_overwrite_part_checkpoint_replaces_content(self):
        """Saving the same part twice replaces the old PartCheckpoint."""
        pc1 = PartCheckpoint(part_name="leg", status="pending")
        self.mgr.save_part_checkpoint("overwrite-part", "leg", pc1)

        pc2 = PartCheckpoint(part_name="leg", status="approved")
        self.mgr.save_part_checkpoint("overwrite-part", "leg", pc2)

        loaded = self.mgr.load_part_checkpoint("overwrite-part", "leg")
        self.assertEqual(loaded.status, "approved")

    def test_round_trip_preserves_nested_dnccheckpoint(self):
        """Full DnCCheckpoint with nested PartCheckpoints round-trips exactly."""
        original = DnCCheckpoint(
            version=2,
            session_id="full-roundtrip",
            task_prompt="complex build",
            current_phase="assemble",
            part_families=[{"name": "base"}, {"name": "top"}],
            part_specs={"base": {"primitive": "cube"}, "top": {"primitive": "sphere"}},
            assembly_plan={"steps": ["step1", "step2"]},
            part_checkpoints={
                "base": PartCheckpoint(
                    part_name="base",
                    status="approved",
                    source_object_name="base_src",
                    instance_object_names=["base_1"],
                    refinement_rounds=2,
                    final_capture_path="captures/base.png",
                    action_history=[{"action": "move"}],
                    failure_policy="RETRYABLE",
                    failure_reason="",
                    retry_count=0,
                ),
                "top": PartCheckpoint(
                    part_name="top",
                    status="failed",
                    failure_policy="FATAL",
                    failure_reason="collision",
                    retry_count=1,
                ),
            },
            completed_steps=[0],
            current_step=1,
            completed=False,
            success=False,
            result=None,
        )
        self.mgr.save_checkpoint("full-roundtrip", original)
        loaded = self.mgr.load_checkpoint("full-roundtrip")

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.version, 2)
        self.assertEqual(loaded.session_id, "full-roundtrip")
        self.assertEqual(loaded.task_prompt, "complex build")
        self.assertEqual(loaded.current_phase, "assemble")
        self.assertEqual(loaded.completed_steps, [0])
        self.assertEqual(loaded.current_step, 1)
        self.assertFalse(loaded.completed)
        self.assertFalse(loaded.success)
        self.assertIsNone(loaded.result)

        # Nested part checkpoints
        self.assertIn("base", loaded.part_checkpoints)
        self.assertEqual(loaded.part_checkpoints["base"].status, "approved")
        self.assertEqual(loaded.part_checkpoints["base"].refinement_rounds, 2)
        self.assertEqual(loaded.part_checkpoints["base"].action_history,
                         [{"action": "move"}])

        self.assertIn("top", loaded.part_checkpoints)
        self.assertEqual(loaded.part_checkpoints["top"].status, "failed")
        self.assertEqual(loaded.part_checkpoints["top"].failure_policy, "FATAL")
        self.assertEqual(loaded.part_checkpoints["top"].failure_reason, "collision")
        self.assertEqual(loaded.part_checkpoints["top"].retry_count, 1)


if __name__ == "__main__":
    unittest.main()
