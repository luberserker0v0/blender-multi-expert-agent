import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.decision.modeling_coordinator import (
    EndpointModelingCoordinator,
    EndpointModelingCoordinatorConfig,
)
from ai_3d_modeling_agent.schemas.gap_report import BlenderContext
from ai_3d_modeling_agent.schemas.modeling_plan import ModelingRequest, UserReference


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create_chat_completion(self, system_prompt, user_prompt, max_tokens=1024, temperature=0.3):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise AssertionError("No scripted response left.")
        return self.responses.pop(0)

    def create_multimodal_chat_completion(
        self,
        system_prompt,
        user_prompt,
        image_inputs,
        max_tokens=1024,
        temperature=0.3,
    ):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "image_inputs": image_inputs,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "mode": "multimodal",
            }
        )
        if not self.responses:
            raise AssertionError("No scripted response left.")
        return self.responses.pop(0)


class TestEndpointModelingCoordinator(unittest.TestCase):
    def test_create_plan_retries_invalid_skeleton_then_builds_plan_in_batches(self) -> None:
        client = ScriptedClient(
            [
                "```json\n{\"reasoning\":\"bad\"",
                """
                {
                  "reasoning": "Build seat then backrest.",
                  "tasks": [
                    {
                      "task_id": "chair_seat",
                      "title": "Chair Seat",
                      "object_name": "chair_seat",
                      "description": "Main sitting surface."
                    },
                    {
                      "task_id": "chair_back",
                      "title": "Chair Back",
                      "object_name": "chair_back",
                      "description": "Rear support."
                    }
                  ]
                }
                """,
                """
                {
                  "task_id": "chair_seat",
                  "title": "Chair Seat",
                  "object_name": "chair_seat",
                  "description": "Main sitting surface.",
                  "preferred_primitive": "Cube",
                  "refinement_viewpoint": "Top/Front",
                  "target_bbox": {"width": 1.4, "depth": 1.2, "height": 0.2},
                  "anchor_points": [
                    {
                      "name": "seat_center",
                      "position": [0, 0, 0],
                      "description": "Center point of the seat."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "",
                    "attach_to": "scene_origin",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Primary reference part.",
                    "placement_notes": "Seat sits at the center."
                  },
                  "assembly_location": [0, 0, 0.4],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_id": "chair_back",
                  "title": "Chair Back",
                  "object_name": "chair_back",
                  "description": "Rear support.",
                  "preferred_primitive": "UV Sphere",
                  "refinement_viewpoint": "Front/Orthographic View",
                  "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
                  "anchor_points": [
                    {
                      "name": "backrest_base",
                      "position": [0, 0, -0.5],
                      "description": "Bottom center of the backrest."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "chair_seat",
                    "attach_to": "seat_back_edge",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Slightly narrower than the seat.",
                    "placement_notes": "Centered behind the seat."
                  },
                  "assembly_location": [0, -0.2, 1.0],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_objects": [
                    {
                      "name": "chair_seat",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_seat",
                      "default_hidden": false
                    },
                    {
                      "name": "chair_back",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_back",
                      "default_hidden": false
                    }
                  ]
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(
            client,
            EndpointModelingCoordinatorConfig(plan_stage_max_retries=3),
        )

        plan = coordinator.create_plan(
            ModelingRequest(
                task_prompt="Build a chair.",
                references=[UserReference(reference_type="text", content="simple wooden chair")],
            )
        )

        self.assertEqual(plan.reasoning, "Build seat then backrest.")
        self.assertEqual(len(plan.tasks), 2)
        self.assertEqual(plan.tasks[0].preferred_primitive, "cube")
        self.assertEqual(plan.tasks[0].refinement_viewpoint, "top")
        self.assertEqual(plan.tasks[0].target_bbox.to_xyz(), [1.4, 1.2, 0.2])
        self.assertEqual(plan.tasks[0].anchor_points[0].name, "seat_center")
        self.assertEqual(plan.tasks[1].preferred_primitive, "uv_sphere")
        self.assertEqual(plan.tasks[1].refinement_viewpoint, "front")
        self.assertEqual(plan.tasks[1].target_bbox.to_xyz(), [0.9, 0.25, 1.5])
        self.assertEqual(plan.tasks[1].structural_spec.parent_task_id, "chair_seat")
        self.assertEqual(len(plan.task_objects), 2)
        self.assertEqual(len(client.calls), 5)
        self.assertIn("Validation error", client.calls[1]["user_prompt"])

    def test_review_part_retries_until_valid_action_json(self) -> None:
        client = ScriptedClient(
            [
                "{\"approved\": false, \"summary\": \"\", \"action\": null}",
                """
                {
                  "approved": false,
                  "summary": "Stretch the part upward.",
                  "action": {
                    "action_type": "scale_axis_z",
                    "parameters": {"factor": 1.2},
                    "reason": "Increase height."
                  }
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(
            client,
            EndpointModelingCoordinatorConfig(review_max_retries=2),
        )
        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                    }
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [1.0, 0.2, 0.7],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertFalse(feedback.approved)
        self.assertEqual(feedback.action.action_type, "scale_axis_z")
        self.assertEqual(feedback.action.parameters["name"], "chair_back")
        self.assertEqual(len(client.calls), 2)

    def test_prompt_observer_receives_each_llm_request_attempt(self) -> None:
        client = ScriptedClient(
            [
                "{\"approved\": false, \"summary\": \"\", \"action\": null}",
                """
                {
                  "approved": true,
                  "summary": "Looks correct.",
                  "action": null
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(
            client,
            EndpointModelingCoordinatorConfig(review_max_retries=2),
        )
        events = []
        coordinator.set_prompt_observer(events.append)

        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "refinement_viewpoint": "front",
                    "task_id": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "object_name": "chair_back",
                        "refinement_viewpoint": "front",
                    },
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [1.0, 0.2, 0.7],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertTrue(feedback.approved)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["stage"], "part_review")
        self.assertEqual(events[0]["label"], "part_review:chair_back")
        self.assertIn("Validation error", events[1]["prompt_preview"])

    def test_review_part_fills_missing_object_name_for_object_specific_action(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": false,
                  "summary": "Move the part slightly backward.",
                  "action": {
                    "action_type": "move_object",
                    "parameters": {"location": [0, -0.1, 0.0]},
                    "reason": "Center the part in the reference."
                  }
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "object_name": "chair_back",
                    },
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [1.0, 0.2, 0.7],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertEqual(feedback.action.action_type, "move_object")
        self.assertEqual(feedback.action.parameters["name"], "chair_back")

    def test_review_part_uses_multimodal_request_when_capture_exists(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": true,
                  "summary": "Looks correct.",
                  "action": null
                }
                """
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            capture_path = Path(tmp_dir) / "capture.png"
            capture_path.write_bytes(b"fake-image")
            feedback = coordinator.review_part(
                task=type(
                    "Task",
                    (),
                    {
                        "object_name": "chair_back",
                        "refinement_viewpoint": "front",
                        "task_id": "chair_back",
                        "to_dict": lambda self: {
                            "task_id": "chair_back",
                            "title": "Chair Back",
                            "object_name": "chair_back",
                            "refinement_viewpoint": "front",
                        },
                    },
                )(),
                capture_path=str(capture_path),
                context=BlenderContext("OBJECT", "chair_back", "NONE"),
                round_index=1,
                object_state={
                    "object_name": "chair_back",
                    "current_scale": [1.0, 1.0, 1.0],
                    "current_dimensions": [1.0, 0.2, 0.7],
                    "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
                },
            )

        self.assertTrue(feedback.approved)
        self.assertEqual(client.calls[0]["mode"], "multimodal")
        self.assertEqual(client.calls[0]["image_inputs"][0]["viewpoint"], "front")

    def test_review_part_fills_missing_scale_for_set_object_scale_action(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": false,
                  "summary": "Match the target bounding box more closely.",
                  "action": {
                    "action_type": "set_object_scale",
                    "parameters": {},
                    "reason": "Use the planned target size for this part."
                  }
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "object_name": "chair_back",
                    },
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [2.0, 2.0, 2.0],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertEqual(feedback.action.action_type, "set_object_scale")
        self.assertEqual(feedback.action.parameters["name"], "chair_back")
        self.assertEqual(feedback.action.parameters["scale"], [0.45, 0.125, 0.75])

    def test_review_part_normalizes_null_action_parameters(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": false,
                  "summary": "Scale the part to match the target size.",
                  "action": {
                    "action_type": "set_object_scale",
                    "parameters": null,
                    "reason": "Use the planned target size for this part."
                  }
                }
                """
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "object_name": "chair_back",
                    },
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [2.0, 2.0, 2.0],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertEqual(feedback.action.parameters["name"], "chair_back")
        self.assertEqual(feedback.action.parameters["scale"], [0.45, 0.125, 0.75])

    def test_review_part_fills_missing_factor_for_axis_scale_action(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": false,
                  "summary": "Increase the backrest height.",
                  "action": {
                    "action_type": "scale_axis_z",
                    "parameters": {},
                    "reason": "Match the planned target height."
                  }
                }
                """
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        feedback = coordinator.review_part(
            task=type(
                "Task",
                (),
                {
                    "object_name": "chair_back",
                    "to_dict": lambda self: {
                        "task_id": "chair_back",
                        "title": "Chair Back",
                        "object_name": "chair_back",
                    },
                },
            )(),
            capture_path="capture.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_state={
                "object_name": "chair_back",
                "current_scale": [1.0, 1.0, 1.0],
                "current_dimensions": [0.9, 0.25, 0.75],
                "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
            },
        )

        self.assertEqual(feedback.action.action_type, "scale_axis_z")
        self.assertEqual(feedback.action.parameters["name"], "chair_back")
        self.assertEqual(feedback.action.parameters["factor"], 2.0)

    def test_create_plan_rejects_assembly_only_task_and_retries(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "reasoning": "Build the whole chair.",
                  "tasks": [
                    {
                      "task_id": "chair_assembly",
                      "title": "Assemble Chair Components",
                      "object_name": "FinalChairAssembly",
                      "description": "Combine all parts into the final object."
                    }
                  ]
                }
                """,
                """
                {
                  "reasoning": "Split the chair into seat and backrest.",
                  "tasks": [
                    {
                      "task_id": "chair_seat",
                      "title": "Chair Seat",
                      "object_name": "chair_seat",
                      "description": "Main sitting surface."
                    },
                    {
                      "task_id": "chair_back",
                      "title": "Chair Back",
                      "object_name": "chair_back",
                      "description": "Rear support."
                    }
                  ]
                }
                """,
                """
                {
                  "task_id": "chair_seat",
                  "title": "Chair Seat",
                  "object_name": "chair_seat",
                  "description": "Main sitting surface.",
                  "preferred_primitive": "cube",
                  "refinement_viewpoint": "top",
                  "target_bbox": {"width": 1.4, "depth": 1.2, "height": 0.2},
                  "anchor_points": [
                    {
                      "name": "seat_center",
                      "position": [0, 0, 0],
                      "description": "Center point of the seat."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "",
                    "attach_to": "scene_origin",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Primary reference part.",
                    "placement_notes": "Seat sits at the center."
                  },
                  "assembly_location": [0, 0, 0.4],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_id": "chair_back",
                  "title": "Chair Back",
                  "object_name": "chair_back",
                  "description": "Rear support.",
                  "preferred_primitive": "cube",
                  "refinement_viewpoint": "front",
                  "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
                  "anchor_points": [
                    {
                      "name": "backrest_base",
                      "position": [0, 0, -0.5],
                      "description": "Bottom center of the backrest."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "chair_seat",
                    "attach_to": "seat_back_edge",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Slightly narrower than the seat.",
                    "placement_notes": "Centered behind the seat."
                  },
                  "assembly_location": [0, -0.2, 1.0],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_objects": [
                    {
                      "name": "chair_seat",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_seat",
                      "default_hidden": false
                    },
                    {
                      "name": "chair_back",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_back",
                      "default_hidden": false
                    }
                  ]
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(
            client,
            EndpointModelingCoordinatorConfig(plan_stage_max_retries=3),
        )

        plan = coordinator.create_plan(ModelingRequest(task_prompt="Build a chair."))

        self.assertEqual([task.task_id for task in plan.tasks], ["chair_seat", "chair_back"])
        self.assertIn("Validation error", client.calls[1]["user_prompt"])

    def test_review_assembly_accepts_set_object_scale_action(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "approved": false,
                  "summary": "Backrest should be slightly narrower.",
                  "actions": [
                    {
                      "action_type": "set_object_scale",
                      "parameters": {"name": "chair_back", "scale": [0.85, 0.2, 1.45]},
                      "reason": "Match the seat width more closely."
                    }
                  ]
                }
                """
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        feedback = coordinator.review_assembly(
            plan=type("Plan", (), {"to_dict": lambda self: {"tasks": []}})(),
            capture_path="assembly.png",
            context=BlenderContext("OBJECT", "chair_back", "NONE"),
            round_index=1,
            object_states=[
                {
                    "task_id": "chair_back",
                    "object_name": "chair_back",
                    "current_dimensions": [0.8, 0.2, 1.3],
                    "target_bbox": {"width": 0.9, "depth": 0.25, "height": 1.5},
                }
            ],
            assembly_state={
                "assembly_step_index": 1,
                "current_task_id": "chair_back",
                "assembled_task_ids": ["chair_back"],
                "remaining_task_ids": [],
            },
        )

        self.assertFalse(feedback.approved)
        self.assertEqual(feedback.actions[0].action_type, "set_object_scale")

    def test_create_plan_defaults_missing_assembly_rotation_and_location(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "reasoning": "Split the chair into seat.",
                  "tasks": [
                    {
                      "task_id": "chair_seat",
                      "title": "Chair Seat",
                      "object_name": "chair_seat",
                      "description": "Main sitting surface."
                    }
                  ]
                }
                """,
                """
                {
                  "task_id": "chair_seat",
                  "title": "Chair Seat",
                  "object_name": "chair_seat",
                  "description": "Main sitting surface.",
                  "preferred_primitive": "cube",
                  "refinement_viewpoint": "top",
                  "target_bbox": {"width": 1.4, "depth": 1.2, "height": 0.2},
                  "anchor_points": [
                    {
                      "name": "seat_center",
                      "position": [0, 0, 0],
                      "description": "Center point of the seat."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "",
                    "attach_to": "scene_origin",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Primary reference part.",
                    "placement_notes": "Seat sits at the center."
                  },
                  "assembly_location": "",
                  "assembly_rotation_degrees": null
                }
                """,
                """
                {
                  "task_objects": [
                    {
                      "name": "chair_seat",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_seat",
                      "default_hidden": false
                    }
                  ]
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        plan = coordinator.create_plan(ModelingRequest(task_prompt="Build a chair seat."))

        self.assertEqual(plan.tasks[0].assembly_location, [0.0, 0.0, 0.0])
        self.assertEqual(plan.tasks[0].assembly_rotation_degrees, [0.0, 0.0, 0.0])

    def test_create_plan_normalizes_duplicate_object_names_in_skeleton(self) -> None:
        client = ScriptedClient(
            [
                """
                {
                  "reasoning": "Split the chair into a seat and four legs.",
                  "tasks": [
                    {
                      "task_id": "chair_seat",
                      "title": "Chair Seat",
                      "object_name": "chair_part",
                      "description": "Main sitting surface."
                    },
                    {
                      "task_id": "chair_leg",
                      "title": "Chair Leg",
                      "object_name": "chair_part",
                      "description": "Prototype leg for later duplication."
                    }
                  ]
                }
                """,
                """
                {
                  "task_id": "chair_seat",
                  "title": "Chair Seat",
                  "object_name": "chair_seat",
                  "description": "Main sitting surface.",
                  "preferred_primitive": "cube",
                  "refinement_viewpoint": "top",
                  "target_bbox": {"width": 1.4, "depth": 1.2, "height": 0.2},
                  "anchor_points": [
                    {
                      "name": "seat_center",
                      "position": [0, 0, 0],
                      "description": "Center point of the seat."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "",
                    "attach_to": "scene_origin",
                    "symmetry_group": "chair_centerline",
                    "sizing_notes": "Primary reference part.",
                    "placement_notes": "Seat sits at the center."
                  },
                  "assembly_location": [0, 0, 0.4],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_id": "chair_leg",
                  "title": "Chair Leg",
                  "object_name": "chair_leg",
                  "description": "Prototype leg for later duplication.",
                  "preferred_primitive": "cylinder",
                  "refinement_viewpoint": "front",
                  "target_bbox": {"width": 0.15, "depth": 0.15, "height": 1.0},
                  "anchor_points": [
                    {
                      "name": "leg_top",
                      "position": [0, 0, 0.5],
                      "description": "Top center of the leg."
                    }
                  ],
                  "structural_spec": {
                    "parent_task_id": "chair_seat",
                    "attach_to": "seat_corner",
                    "symmetry_group": "chair_legs",
                    "sizing_notes": "Four identical legs.",
                    "placement_notes": "One prototype leg before duplication."
                  },
                  "assembly_location": [0.5, 0.5, -0.5],
                  "assembly_rotation_degrees": [0, 0, 0]
                }
                """,
                """
                {
                  "task_objects": [
                    {
                      "name": "chair_seat",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_seat",
                      "default_hidden": false
                    },
                    {
                      "name": "chair_leg",
                      "role": "part",
                      "allowed_count": 1,
                      "creation_policy": "create_if_missing",
                      "parent_name": "chair_assembly",
                      "task_id": "chair_leg",
                      "default_hidden": false
                    }
                  ]
                }
                """,
            ]
        )
        coordinator = EndpointModelingCoordinator(client)

        plan = coordinator.create_plan(ModelingRequest(task_prompt="Build a chair."))

        self.assertEqual(plan.tasks[0].object_name, "chair_seat")
        self.assertEqual(plan.tasks[1].object_name, "chair_leg")
        skeleton_prompt = client.calls[2]["user_prompt"]
        self.assertIn('"object_name": "chair_part_2"', skeleton_prompt)


if __name__ == "__main__":
    unittest.main()
