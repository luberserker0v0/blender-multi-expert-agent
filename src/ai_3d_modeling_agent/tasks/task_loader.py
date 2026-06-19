"""Task and checklist loading utilities."""

import json
from pathlib import Path

from ai_3d_modeling_agent.schemas.task_objects import TaskObjectSpec, task_object_names
from ai_3d_modeling_agent.schemas.target_part_checklist import TargetPartChecklist


def load_checklist(checklist_path: Path) -> TargetPartChecklist:
    with checklist_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return TargetPartChecklist.from_dict(data)


def build_required_object_table(checklist: TargetPartChecklist) -> list[TaskObjectSpec]:
    target_root = f"{checklist.target_object_class}_body"
    object_table = [
        TaskObjectSpec(
            name=target_root,
            role="target_body",
            allowed_count=1,
            creation_policy="create_if_missing",
        )
    ]
    known_names = {target_root}
    for item in checklist.critical_parts_checklist:
        part_name = str(item.part_name).strip().replace(" ", "_").lower()
        if part_name and part_name not in known_names:
            object_table.append(
                TaskObjectSpec(
                    name=part_name,
                    role=f"critical_part:{item.part_id}",
                    allowed_count=1,
                    creation_policy="create_if_missing",
                )
            )
            known_names.add(part_name)
    return object_table


def build_required_object_names(checklist: TargetPartChecklist) -> list[str]:
    return task_object_names(build_required_object_table(checklist))
