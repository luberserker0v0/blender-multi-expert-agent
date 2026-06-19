from ai_3d_modeling_agent.multi_expert.core.action_plan import ASSEMBLY_ACTIONS, BUILD_ACTIONS, parse_agent_action_plan


def test_parse_action_plan_accepts_markdown_json_fence() -> None:
    raw = """```json
{
  "status": "ready",
  "parts": [
    {
      "part_name": "E2E_Cube",
      "actions": [
        {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "E2E_Cube_source"}}
      ]
    }
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Builder")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "E2E_Cube"


def test_parse_action_plan_accepts_top_level_build_actions() -> None:
    raw = """```json
{
  "target_family": "cube",
  "step_index": 0,
  "actions": [
    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "cube_source"}},
    {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "cube"
    assert plan.parts[0]["source_object_name"] == "cube_source"
    assert plan.parts[0]["instance_names"] == ["cube_01"]


def test_parse_action_plan_accepts_task_dependencies_shape() -> None:
    raw = """```json
{
  "target_family": "cube",
  "task": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "cube_source"},
  "dependencies": [
    {"action_type": "set_object_scale", "parameters": {"name": "cube_source", "scale": [1.0, 1.0, 1.0]}},
    {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}},
    {"action_type": "delete_object", "parameters": {"name": "cube_source"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "cube"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_action_sequence_alias() -> None:
    raw = """```json
{
  "family": "cube",
  "source_name": "temp_cube_body",
  "action_sequence": [
    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "temp_cube_body"}},
    {"action_type": "duplicate_object", "parameters": {"name": "temp_cube_body", "new_name": "cube_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "cube"
    assert plan.parts[0]["source_object_name"] == "temp_cube_body"


def test_parse_action_plan_accepts_command_next_actions_shape() -> None:
    raw = """```json
{
  "family": "cube",
  "command": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "cube_source"},
  "next_actions": [
    {"command": "set_object_scale", "parameters": {"name": "cube_source", "scale": [1.0, 1.0, 1.0]}},
    {"command": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
    ]


def test_parse_action_plan_accepts_operation_subsequent_actions_shape() -> None:
    raw = """```json
{
  "operation": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "cube_source"},
  "subsequent_actions": [
    {"action_type": "set_object_scale", "parameters": {"name": "cube_source", "scale": [1.0, 1.0, 1.0]}},
    {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
    ]


def test_parse_action_plan_accepts_action_follow_up_actions_shape() -> None:
    raw = """```json
{
  "target_family": "seat",
  "action": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "seat_source"},
  "follow_up_actions": [
    {"action_type": "set_object_scale", "parameters": {"name": "seat_source", "scale": [0.4, 0.4, 0.02]}},
    {"action_type": "duplicate_object", "parameters": {"name": "seat_source", "new_name": "seat_01"}},
    {"action_type": "delete_object", "parameters": {"name": "seat_source"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "seat"
    assert plan.parts[0]["source_object_name"] == "seat_source"
    assert plan.parts[0]["instance_names"] == ["seat_01"]
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_semantic_build_shape_with_pending_status() -> None:
    raw = """```json
{
  "task_id": "build:leg",
  "status": "pending",
  "target_family": "leg",
  "primitive_type": "cube",
  "instance_count": 4,
  "scale": [0.05, 0.05, 0.45],
  "operation_description": "Create four cube legs."
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "leg"
    assert plan.parts[0]["source_object_name"] == "leg_source"
    assert plan.parts[0]["instance_names"] == ["leg_01", "leg_02", "leg_03", "leg_04"]
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "duplicate_object",
        "duplicate_object",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_top_level_action_type_with_actions_to_run_dependencies() -> None:
    raw = """```json
{
  "action_type": "create_primitive",
  "parameters": {"name": "seat_source", "primitive_type": "cube"},
  "dependencies": [
    {
      "part_name": "seat",
      "step_index": 0,
      "instance_names": ["seat_01"],
      "actions_to_run": [
        {"action_type": "set_object_scale", "parameters": {"name": "seat_source", "scale": [0.4, 0.4, 0.15]}},
        {"action_type": "duplicate_object", "parameters": {"name": "seat_source", "new_name": "seat_01"}},
        {"action_type": "delete_object", "parameters": {"name": "seat_source"}}
      ]
    }
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert plan.parts[0]["part_name"] == "seat"
    assert plan.parts[0]["instance_names"] == ["seat_01"]
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_top_level_action_type_with_post_actions() -> None:
    raw = """```json
{
  "action_type": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "seat_source"},
  "post_actions": [
    {"action_type": "set_object_scale", "parameters": {"name": "seat_source", "scale": [50.0, 50.0, 10.0]}},
    {"action_type": "duplicate_object", "parameters": {"name": "seat_source", "new_name": "seat_01"}},
    {"action_type": "delete_object", "parameters": {"name": "seat_source"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_task_with_successors() -> None:
    raw = """```json
{
  "task": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "Cube_Primary_Instance"},
  "successors": [
    {"action_type": "set_object_scale", "parameters": {"name": "Cube_Primary_Instance", "scale": [1.0, 1.0, 1.0]}},
    {"action_type": "duplicate_object", "parameters": {"name": "Cube_Primary_Instance", "new_name": "cube_01"}},
    {"action_type": "delete_object", "parameters": {"name": "Cube_Primary_Instance"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_treats_completed_as_ready_and_drops_optional_material_action() -> None:
    raw = """```json
{
  "status": "completed",
  "target_family": "cube",
  "source_object_name": "Cube_Instance_01",
  "instance_count": 1,
  "actions": [
    {"action_type": "create_primitive", "parameters": {"primitive_type": "cube", "name": "Cube_Instance_01"}},
    {"action_type": "set_object_scale", "parameters": {"name": "Cube_Instance_01", "scale": [1.0, 1.0, 1.0]}},
    {"action_type": "apply_material", "parameters": {"name": "Cube_Instance_01", "material": "Mat_Cube_Base"}},
    {"action_type": "duplicate_object", "parameters": {"name": "Cube_Instance_01", "new_name": "cube_01"}},
    {"action_type": "delete_object", "parameters": {"name": "Cube_Instance_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_top_level_action_type_with_required_actions() -> None:
    raw = """```json
{
  "action_type": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "seat_source"},
  "required_actions": [
    {"action_type": "set_object_scale", "parameters": {"name": "seat_source", "scale": [0.5, 1.0, 0.1]}},
    {"action_type": "duplicate_object", "parameters": {"name": "seat_source", "new_name": "seat_01"}},
    {"action_type": "delete_object", "parameters": {"name": "seat_source"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_top_level_task_with_task_action_sequence() -> None:
    raw = """```json
{
  "task": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "cube_source"},
  "action_sequence": [
    {"task": "set_object_scale", "parameters": {"name": "cube_source", "scale": [1.0, 1.0, 1.0]}},
    {"task": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}},
    {"task": "delete_object", "parameters": {"name": "cube_source"}}
  ],
  "material_assignment": {"name": "Default_Plastic"}
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_post_operation_actions() -> None:
    raw = """```json
{
  "operation": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "cube_source"},
  "post_operation_actions": [
    {"action_type": "set_object_scale", "parameters": {"name": "cube_source", "scale": [0.5, 0.5, 0.5]}},
    {"action_type": "duplicate_object", "parameters": {"name": "cube_source", "new_name": "cube_01"}},
    {"action_type": "delete_object", "parameters": {"name": "cube_source"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
        "delete_object",
    ]


def test_parse_action_plan_accepts_operation_aliases_inside_action_sequence() -> None:
    raw = """```json
{
  "operation": "create_primitive",
  "parameters": {"primitive_type": "cube", "name": "main_object_source"},
  "action_sequence": [
    {"operation": "create_primitive", "parameters": {"primitive_type": "cube", "name": "main_object_source"}},
    {"operation": "set_object_scale", "parameters": {"name": "main_object_source", "scale": [0.225, 0.225, 0.01]}},
    {"operation": "duplicate_object", "parameters": {"name": "main_object_source", "new_name": "main_object_01"}}
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    assert plan.status == "ready"
    assert [action["action_type"] for action in plan.parts[0]["actions"]] == [
        "create_primitive",
        "create_primitive",
        "set_object_scale",
        "duplicate_object",
    ]


def test_parse_action_plan_moves_root_name_into_create_parameters() -> None:
    raw = """```json
{
  "operation": "create_primitive",
  "name": "seat_source",
  "parameters": {
    "primitive_type": "cube"
  },
  "action_sequence": [
    {
      "action_type": "set_object_scale",
      "parameters": {"name": "seat_source", "scale": [1.0, 1.0, 1.0]}
    },
    {
      "action_type": "duplicate_object",
      "parameters": {"name": "seat_source", "new_name": "seat_01"}
    },
    {
      "action_type": "delete_object",
      "parameters": {"name": "seat_source"}
    }
  ]
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")

    first_action = plan.parts[0]["actions"][0]
    assert first_action["action_type"] == "create_primitive"
    assert first_action["parameters"] == {"primitive_type": "cube", "name": "seat_source"}


def test_parse_action_plan_accepts_semantic_placement_shape() -> None:
    raw = """```json
{
  "task_id": "place:cube",
  "family": "cube",
  "step_index": 0,
  "placement_rule": "place_at_world_position",
  "instances_to_place": ["cube_01"],
  "target_world_position": {"x": 0.0, "y": 0.0, "z": 0.0},
  "target_rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
  "parent_object_name": null
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=ASSEMBLY_ACTIONS, context_label="Assembly Markdown extraction")

    assert plan.status == "ready"
    assert plan.steps[0]["step_index"] == 0
    assert [action["action_type"] for action in plan.steps[0]["actions"]] == ["show_object", "move_object"]
    assert plan.steps[0]["actions"][1]["parameters"] == {"name": "cube_01", "location": [0.0, 0.0, 0.0]}


def test_parse_action_plan_accepts_assembly_extraction_placement_rule_shape() -> None:
    raw = """```json
{
  "operation_description": "Place and validate leg parts",
  "target_family": "leg",
  "step_index": 1,
  "instance_count": 4,
  "placement_rule": "place_at_world_position",
  "location": [0.275, -0.015, -0.235],
  "rotation_degrees": [0.0, 0.0, 0.0],
  "instance_locations": [
    [0.275, -0.015, -0.235],
    [-0.275, -0.015, -0.235],
    [-0.275, 0.015, -0.235],
    [0.275, 0.015, -0.235]
  ],
  "validation_check": {
    "status": "pending",
    "criteria": "All leg instances must exist at specified world positions."
  }
}
```"""

    plan = parse_agent_action_plan(raw, allowed_actions=ASSEMBLY_ACTIONS, context_label="Assembly Markdown extraction")

    assert plan.status == "ready"
    assert plan.steps[0]["step_index"] == 1
    moves = [action for action in plan.steps[0]["actions"] if action["action_type"] == "move_object"]
    assert [move["parameters"]["name"] for move in moves] == ["leg_01", "leg_02", "leg_03", "leg_04"]
    assert moves[1]["parameters"]["location"] == [-0.275, -0.015, -0.235]
