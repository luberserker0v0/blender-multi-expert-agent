import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.memory.session_progress import SessionProgressStore
from ai_3d_modeling_agent.schemas.modeling_plan import ModelingRequest
from ai_3d_modeling_agent.schemas.session_progress import MultiStageProgressSnapshot


class TestSessionProgress(unittest.TestCase):
    def test_progress_store_writes_to_progress_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SessionProgressStore(Path(tmp_dir))
            path = store.mark_started("chat/window:1", "build an apple", 5)

            self.assertTrue(path.exists())
            self.assertEqual(path.name, "progress.json")

    def test_progress_store_writes_multi_stage_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = SessionProgressStore(Path(tmp_dir))
            snapshot = MultiStageProgressSnapshot(
                workflow_type="multi_stage_modeling",
                status="running",
                task="build a chair",
                stage="part_refinement",
                stage_status="running",
                request=ModelingRequest(task_prompt="build a chair"),
                required_objects=[],
            )

            path = store.write_multi_stage_snapshot("chair/session:1", snapshot)

            self.assertTrue(path.exists())
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            self.assertEqual(data["workflow_type"], "multi_stage_modeling")
            self.assertEqual(data["stage"], "part_refinement")
            self.assertEqual(data["request"]["task_prompt"], "build a chair")
            self.assertEqual(data["session_id"], "chair/session:1")


if __name__ == "__main__":
    unittest.main()
