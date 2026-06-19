import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
from ai_3d_modeling_agent.schemas.actions import Action


class FakeObjectOps:
    def __init__(self) -> None:
        self.calls = []

    def set_active_object(self, name: str) -> None:
        self.calls.append(("set_active_object", name))

    def scale_uniform(self, factor: float) -> None:
        self.calls.append(("scale_uniform", factor))

    def scale_axis(self, axis: str, factor: float) -> None:
        self.calls.append(("scale_axis", axis, factor))

    def delete_object(self, name: str) -> bool:
        self.calls.append(("delete_object", name))
        return True


class TestActionExecutor(unittest.TestCase):
    def test_scale_uniform_selects_named_object_before_scaling(self) -> None:
        object_ops = FakeObjectOps()
        executor = ActionExecutor(object_ops)

        executor.execute(Action("scale_uniform", {"name": "chair_back", "factor": 1.2}))

        self.assertEqual(
            object_ops.calls,
            [("set_active_object", "chair_back"), ("scale_uniform", 1.2)],
        )

    def test_scale_axis_selects_named_object_before_scaling(self) -> None:
        object_ops = FakeObjectOps()
        executor = ActionExecutor(object_ops)

        executor.execute(Action("scale_axis_z", {"name": "chair_back", "factor": 1.5}))

        self.assertEqual(
            object_ops.calls,
            [("set_active_object", "chair_back"), ("scale_axis", "z", 1.5)],
        )

    def test_delete_object_delegates_to_object_ops(self) -> None:
        object_ops = FakeObjectOps()
        executor = ActionExecutor(object_ops)

        self.assertTrue(executor.execute(Action("delete_object", {"name": "source_cube"})))

        self.assertEqual(object_ops.calls, [("delete_object", "source_cube")])
