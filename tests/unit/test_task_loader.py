import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.tasks.task_loader import (
    build_required_object_names,
    build_required_object_table,
    load_checklist,
)


class TestTaskLoader(unittest.TestCase):
    def test_build_required_object_table_for_apple(self) -> None:
        checklist = load_checklist(
            REPO_ROOT / "data" / "static" / "checklists" / "apple_checklist.json"
        )

        object_table = build_required_object_table(checklist)

        self.assertEqual(len(object_table), 1)
        self.assertEqual(object_table[0].name, "apple_body")
        self.assertEqual(object_table[0].role, "target_body")
        self.assertEqual(object_table[0].allowed_count, 1)
        self.assertEqual(object_table[0].creation_policy, "create_if_missing")

    def test_required_object_names_are_derived_from_object_table(self) -> None:
        checklist = load_checklist(
            REPO_ROOT / "data" / "static" / "checklists" / "apple_checklist.json"
        )

        names = build_required_object_names(checklist)

        self.assertEqual(names, ["apple_body"])


if __name__ == "__main__":
    unittest.main()
