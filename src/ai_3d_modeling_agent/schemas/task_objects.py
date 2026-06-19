"""Task-scoped object table models."""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class TaskObjectSpec:
    name: str
    role: str
    allowed_count: int = 1
    creation_policy: str = "create_if_missing"
    parent_name: str = ""
    task_id: str = ""
    default_hidden: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "allowed_count": self.allowed_count,
            "creation_policy": self.creation_policy,
            "parent_name": self.parent_name,
            "task_id": self.task_id,
            "default_hidden": self.default_hidden,
        }


def task_object_names(object_table: List["TaskObjectSpec"]) -> List[str]:
    return [item.name for item in object_table]
