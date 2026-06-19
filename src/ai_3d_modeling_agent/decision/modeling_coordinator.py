"""Planning and review abstractions for multi-stage modeling loops."""

import json
import re
import time
from ai_3d_modeling_agent.utils.llm_parser import extract_json_from_llm
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Protocol

from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.gap_report import BlenderContext
from ai_3d_modeling_agent.schemas.modeling_plan import (
    AnchorPointSpec,
    AssemblyFeedback,
    BoundingBoxSpec,
    ModelingPlan,
    ModelingRequest,
    ModelingTask,
    PartFeedback,
    StructuralSpec,
)
from ai_3d_modeling_agent.schemas.part import PartFamily, PartSpec
from ai_3d_modeling_agent.schemas.task_objects import TaskObjectSpec
from ai_3d_modeling_agent.services.llm_endpoint import OpenAiCompatibleEndpointClient
from ai_3d_modeling_agent.prompts import read_markdown_prompt


class ModelingCoordinator(Protocol):
    def create_plan(self, request: ModelingRequest) -> ModelingPlan:
        """Turn user input into a structured multi-part modeling plan."""

    def review_part(
        self,
        task: ModelingTask,
        capture_path: str,
        context: BlenderContext,
        round_index: int,
        object_state: Dict[str, Any],
        review_bundle: Optional[Dict[str, Any]] = None,
    ) -> PartFeedback:
        """Review one part capture and optionally request another edit."""

    def review_assembly(
        self,
        plan: ModelingPlan,
        capture_path: str,
        context: BlenderContext,
        round_index: int,
        object_states: List[Dict[str, Any]],
        assembly_state: Dict[str, Any],
        review_bundle: Optional[Dict[str, Any]] = None,
    ) -> AssemblyFeedback:
        """Review the full assembled object and optionally request edits."""


@dataclass
class EndpointModelingCoordinatorConfig:
    max_tokens: int = 1024
    temperature: float = 0.3
    plan_stage_max_retries: int = 3
    review_max_retries: int = 2
    retry_timeout_seconds: float = 300.0
    max_identical_invalid_response_repeats: int = 3


class EndpointModelingCoordinator:
    def __init__(
        self,
        client: OpenAiCompatibleEndpointClient,
        config: EndpointModelingCoordinatorConfig = None,
    ) -> None:
        self.client = client
        self.config = config or EndpointModelingCoordinatorConfig()
        self.prompt_observer: Optional[Callable[[Dict[str, Any]], None]] = None

    def set_prompt_observer(self, observer: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        self.prompt_observer = observer

    def create_plan(self, request: ModelingRequest) -> ModelingPlan:
        request_json = json.dumps(request.to_dict(), ensure_ascii=False)

        skeleton_payload = self._request_valid_json(
            system_prompt=read_markdown_prompt("decision/modeling_coordinator/plan_skeleton_system.md"),
            user_prompt=f"User request:\n{request_json}",
            validator=self._validate_plan_skeleton_payload,
            max_retries=self.config.plan_stage_max_retries,
            prompt_stage="planning",
            prompt_label="plan_skeleton",
        )

        reasoning = str(skeleton_payload.get("reasoning", "")).strip()
        skeleton_tasks = skeleton_payload.get("tasks", [])
        enriched_tasks = [
            self._request_task_detail(request, reasoning, item, index)
            for index, item in enumerate(skeleton_tasks, start=1)
        ]

        task_objects_payload = self._request_valid_json(
            system_prompt=read_markdown_prompt("decision/modeling_coordinator/task_objects_system.md"),
            user_prompt=json.dumps(
                {
                    "request": request.to_dict(),
                    "reasoning": reasoning,
                    "tasks": [item.to_dict() for item in enriched_tasks],
                },
                ensure_ascii=False,
            ),
            validator=lambda data: self._validate_task_objects_payload(data, enriched_tasks),
            max_retries=self.config.plan_stage_max_retries,
            prompt_stage="planning",
            prompt_label="task_objects",
        )

        return ModelingPlan(
            task_prompt=request.task_prompt,
            reasoning=reasoning,
            tasks=enriched_tasks,
            task_objects=[
                TaskObjectSpec(
                    name=str(item["name"]),
                    role=str(item["role"]),
                    allowed_count=int(item.get("allowed_count", 1)),
                    creation_policy=str(item.get("creation_policy", "create_if_missing")),
                    parent_name=str(item.get("parent_name", "")),
                    task_id=str(item.get("task_id", "")),
                    default_hidden=bool(item.get("default_hidden", False)),
                )
                for item in task_objects_payload.get("task_objects", [])
            ],
        )

    def review_part(
        self,
        task: ModelingTask,
        capture_path: str,
        context: BlenderContext,
        round_index: int,
        object_state: Dict[str, Any],
        review_bundle: Optional[Dict[str, Any]] = None,
    ) -> PartFeedback:
        task_payload = task.to_dict()
        default_object_name = str(getattr(task, "object_name", "") or task_payload.get("object_name", ""))
        review_viewpoint = str(
            getattr(task, "refinement_viewpoint", "") or task_payload.get("refinement_viewpoint", "front")
        )
        task_id = str(getattr(task, "task_id", "") or task_payload.get("task_id", ""))
        effective_review_bundle = review_bundle or {
            "captures": [
                {
                    "path": capture_path,
                    "viewpoint": review_viewpoint,
                    "stage": "part",
                    "task_id": task_id,
                    "object_name": default_object_name,
                    "description": f"{review_viewpoint} orthographic review image for {default_object_name}.",
                }
            ]
        }
        payload = self._request_valid_json(
            system_prompt=read_markdown_prompt("decision/modeling_coordinator/part_review_system.md"),
            user_prompt=json.dumps(
                {
                    "task": task_payload,
                    "review_bundle": effective_review_bundle,
                    "object_state": object_state,
                    "context": {
                        "current_mode": context.current_mode,
                        "active_object_name": context.active_object_name,
                        "active_element_mode": context.active_element_mode,
                    },
                    "round_index": round_index,
                },
                ensure_ascii=False,
            ),
            image_inputs=self._build_image_inputs_from_review_bundle(effective_review_bundle),
            validator=self._validate_part_feedback_payload,
            max_retries=self.config.review_max_retries,
            prompt_stage="part_review",
            prompt_label=f"part_review:{task_id or default_object_name}",
        )
        action_data = payload.get("action")
        return PartFeedback(
            approved=bool(payload.get("approved", False)),
            summary=str(payload.get("summary", "")),
            action=self._action_from_dict(
                action_data,
                default_object_name=default_object_name,
                object_state=object_state,
            )
            if isinstance(action_data, dict)
            else None,
        )

    def review_assembly(
        self,
        plan: ModelingPlan,
        capture_path: str,
        context: BlenderContext,
        round_index: int,
        object_states: List[Dict[str, Any]],
        assembly_state: Dict[str, Any],
        review_bundle: Optional[Dict[str, Any]] = None,
    ) -> AssemblyFeedback:
        effective_review_bundle = review_bundle or {
            "captures": [
                {
                    "path": capture_path,
                    "viewpoint": "front",
                    "stage": "assembly",
                    "task_id": str(assembly_state.get("current_task_id", "")),
                    "description": "Front assembly review image for the current step.",
                }
            ]
        }
        payload = self._request_valid_json(
            system_prompt=read_markdown_prompt("decision/modeling_coordinator/assembly_review_system.md"),
            user_prompt=json.dumps(
                {
                    "plan": plan.to_dict(),
                    "review_bundle": effective_review_bundle,
                    "assembly_state": assembly_state,
                    "object_states": object_states,
                    "context": {
                        "current_mode": context.current_mode,
                        "active_object_name": context.active_object_name,
                        "active_element_mode": context.active_element_mode,
                    },
                    "round_index": round_index,
                },
                ensure_ascii=False,
            ),
            image_inputs=self._build_image_inputs_from_review_bundle(effective_review_bundle),
            validator=self._validate_assembly_feedback_payload,
            max_retries=self.config.review_max_retries,
            prompt_stage="assembly_review",
            prompt_label=f"assembly_review:{assembly_state.get('current_task_id', '')}",
        )
        return AssemblyFeedback(
            approved=bool(payload.get("approved", False)),
            summary=str(payload.get("summary", "")),
            actions=[
                self._action_from_dict(
                    item,
                    default_object_name=str(context.active_object_name or ""),
                    object_state=self._find_object_state_for_action(
                        item,
                        object_states,
                        str(context.active_object_name or ""),
                    ),
                )
                for item in payload.get("actions", [])
                if isinstance(item, dict)
            ],
        )

    def _request_task_detail(
        self,
        request: ModelingRequest,
        reasoning: str,
        task_data: Dict[str, Any],
        index: int,
    ) -> ModelingTask:
        payload = self._request_valid_json(
            system_prompt=read_markdown_prompt("decision/modeling_coordinator/task_detail_system.md"),
            user_prompt=json.dumps(
                {
                    "request": request.to_dict(),
                    "reasoning": reasoning,
                    "task_index": index,
                    "task_skeleton": task_data,
                },
                ensure_ascii=False,
            ),
            validator=self._validate_task_detail_payload,
            max_retries=self.config.plan_stage_max_retries,
            prompt_stage="planning",
            prompt_label=f"task_detail:{str(task_data.get('task_id', '')).strip() or index}",
        )
        return ModelingTask(
            task_id=str(payload["task_id"]),
            title=str(payload["title"]),
            object_name=str(payload["object_name"]),
            description=str(payload["description"]),
            preferred_primitive=self._normalize_primitive(payload["preferred_primitive"]),
            refinement_viewpoint=self._normalize_viewpoint(payload.get("refinement_viewpoint", "front")),
            target_bbox=self._coerce_bbox(payload.get("target_bbox")),
            anchor_points=self._coerce_anchor_points(payload.get("anchor_points")),
            structural_spec=self._coerce_structural_spec(payload.get("structural_spec")),
            assembly_location=self._coerce_xyz_with_default(
                payload.get("assembly_location"),
                "assembly_location",
                [0.0, 0.0, 0.0],
            ),
            assembly_rotation_degrees=self._coerce_xyz_with_default(
                payload.get("assembly_rotation_degrees"),
                "assembly_rotation_degrees",
                [0.0, 0.0, 0.0],
            ),
        )

    def _request_valid_json(
        self,
        system_prompt: str,
        user_prompt: str,
        validator: Callable[[Dict[str, Any]], None],
        max_retries: int,
        image_inputs: Optional[List[Dict[str, str]]] = None,
        prompt_stage: str = "",
        prompt_label: str = "",
    ) -> Dict[str, Any]:
        repair_note = ""
        last_error = ""
        repeated_error_count = 0
        previous_error = ""
        deadline = time.monotonic() + max(30.0, self.config.retry_timeout_seconds)
        while True:
            effective_user_prompt = user_prompt
            if repair_note:
                effective_user_prompt = (
                    f"{user_prompt}\n\n"
                    "The previous response was invalid. "
                    f"Validation error: {repair_note}\n"
                    "Retry and return corrected JSON only."
                )
            prompt_preview = self._build_prompt_preview(system_prompt, effective_user_prompt, image_inputs)
            if image_inputs:
                raw_response = self.client.create_multimodal_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=effective_user_prompt,
                    image_inputs=image_inputs,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            else:
                raw_response = self.client.create_chat_completion(
                    system_prompt=system_prompt,
                    user_prompt=effective_user_prompt,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
            try:
                payload = extract_json_from_llm(raw_response, context_label="ModelingCoordinator")
                validator(payload)
                self._record_prompt_event(
                    prompt_stage=prompt_stage,
                    prompt_label=prompt_label,
                    prompt_preview=prompt_preview,
                    response_preview=str(raw_response).strip(),
                    validation_error="",
                    image_inputs=image_inputs,
                )
                return payload
            except Exception as exc:
                last_error = str(exc)
                repair_note = last_error
                repeated_error_count = (
                    repeated_error_count + 1 if last_error == previous_error else 1
                )
                previous_error = last_error
                self._record_prompt_event(
                    prompt_stage=prompt_stage,
                    prompt_label=prompt_label,
                    prompt_preview=prompt_preview,
                    response_preview=str(raw_response).strip(),
                    validation_error=last_error,
                    image_inputs=image_inputs,
                )
                if repeated_error_count >= self.config.max_identical_invalid_response_repeats:
                    raise ValueError(
                        "Modeling coordinator became stuck on the same invalid response pattern: "
                        f"{last_error}"
                    )
                if time.monotonic() >= deadline:
                    raise ValueError(
                        "Modeling coordinator retry window expired while waiting for a valid response: "
                        f"{last_error}"
                    )

    def _record_prompt_event(
        self,
        prompt_stage: str,
        prompt_label: str,
        prompt_preview: str,
        response_preview: str,
        validation_error: str,
        image_inputs: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if self.prompt_observer is None:
            return
        self.prompt_observer(
            {
                "stage": prompt_stage,
                "label": prompt_label,
                "prompt_preview": prompt_preview,
                "response_preview": response_preview,
                "validation_error": validation_error,
                "has_images": bool(image_inputs),
                "image_count": len(image_inputs or []),
            }
        )

    @staticmethod
    def _build_prompt_preview(
        system_prompt: str,
        user_prompt: str,
        image_inputs: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        preview_parts = [
            f"[System]\n{system_prompt.strip()}",
            f"[User]\n{user_prompt.strip()}",
        ]
        if image_inputs:
            image_lines = [
                f"- {str(item.get('viewpoint', '')).strip() or 'image'} | {str(item.get('label', '')).strip()}"
                for item in image_inputs
            ]
            preview_parts.append("[Images]\n" + "\n".join(image_lines))
        return "\n\n".join(part for part in preview_parts if part).strip()

    @staticmethod
    def _action_from_dict(
        data: Dict[str, Any],
        default_object_name: str = "",
        object_state: Optional[Dict[str, Any]] = None,
    ) -> Action:
        raw_parameters = data.get("parameters", {})
        parameters = dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
        action_type = str(data["action_type"])
        if (
            action_type
            in {
                "select_object",
                "scale_uniform",
                "scale_axis_x",
                "scale_axis_y",
                "scale_axis_z",
                "move_object",
                "set_object_scale",
                "rotate_object",
                "show_object",
                "hide_object",
            }
            and "name" not in parameters
            and default_object_name
        ):
            parameters["name"] = default_object_name
        if action_type == "set_object_scale" and "scale" not in parameters:
            repaired_scale = EndpointModelingCoordinator._derive_scale_from_object_state(object_state)
            if repaired_scale is not None:
                parameters["scale"] = repaired_scale
        if action_type in {"scale_uniform", "scale_axis_x", "scale_axis_y", "scale_axis_z"} and "factor" not in parameters:
            repaired_factor = EndpointModelingCoordinator._derive_scale_factor_from_object_state(
                action_type,
                object_state,
            )
            if repaired_factor is not None:
                parameters["factor"] = repaired_factor
        return Action(
            action_type=action_type,
            parameters=parameters,
            reason=str(data.get("reason", "")),
        )

    @staticmethod
    def _find_object_state_for_action(
        action_data: Dict[str, Any],
        object_states: List[Dict[str, Any]],
        default_object_name: str,
    ) -> Optional[Dict[str, Any]]:
        parameters = action_data.get("parameters", {})
        requested_name = ""
        if isinstance(parameters, dict):
            requested_name = str(parameters.get("name", "")).strip()
        target_name = requested_name or default_object_name
        if not target_name:
            return object_states[0] if object_states else None
        for item in object_states:
            if str(item.get("object_name", "")).strip() == target_name:
                return item
        return object_states[0] if object_states else None

    @staticmethod
    def _derive_scale_from_object_state(object_state: Optional[Dict[str, Any]]) -> Optional[List[float]]:
        if not isinstance(object_state, dict):
            return None
        current_scale = object_state.get("current_scale")
        current_dimensions = object_state.get("current_dimensions")
        target_bbox = object_state.get("target_bbox")
        if (
            not isinstance(current_scale, list)
            or len(current_scale) != 3
            or not isinstance(current_dimensions, list)
            or len(current_dimensions) != 3
            or not isinstance(target_bbox, dict)
        ):
            return None
        target_dimensions = [
            target_bbox.get("width"),
            target_bbox.get("depth"),
            target_bbox.get("height"),
        ]
        repaired_scale: List[float] = []
        try:
            for index in range(3):
                current_scale_value = float(current_scale[index])
                current_dimension = float(current_dimensions[index])
                target_dimension = float(target_dimensions[index])
                if current_dimension <= 0.0001:
                    repaired_scale.append(round(max(target_dimension, 0.0001), 4))
                    continue
                repaired_scale.append(round(current_scale_value * (target_dimension / current_dimension), 4))
        except (TypeError, ValueError):
            return None
        return repaired_scale

    @staticmethod
    def _derive_scale_factor_from_object_state(
        action_type: str,
        object_state: Optional[Dict[str, Any]],
    ) -> Optional[float]:
        if not isinstance(object_state, dict):
            return None
        current_dimensions = object_state.get("current_dimensions")
        target_bbox = object_state.get("target_bbox")
        if (
            not isinstance(current_dimensions, list)
            or len(current_dimensions) != 3
            or not isinstance(target_bbox, dict)
        ):
            return None
        target_dimensions = [
            target_bbox.get("width"),
            target_bbox.get("depth"),
            target_bbox.get("height"),
        ]
        try:
            ratios = []
            for index in range(3):
                current_dimension = float(current_dimensions[index])
                target_dimension = float(target_dimensions[index])
                if current_dimension <= 0.0001:
                    continue
                ratios.append(target_dimension / current_dimension)
        except (TypeError, ValueError):
            return None
        if not ratios:
            return None
        axis_index_map = {
            "scale_axis_x": 0,
            "scale_axis_y": 1,
            "scale_axis_z": 2,
        }
        if action_type in axis_index_map:
            axis_index = axis_index_map[action_type]
            try:
                current_dimension = float(current_dimensions[axis_index])
                target_dimension = float(target_dimensions[axis_index])
            except (TypeError, ValueError):
                return None
            if current_dimension <= 0.0001:
                return None
            return round(target_dimension / current_dimension, 4)
        return round(sum(ratios) / len(ratios), 4)

    def _validate_plan_skeleton_payload(self, data: Dict[str, Any]) -> None:
        if not isinstance(data.get("reasoning"), str) or not str(data.get("reasoning", "")).strip():
            raise ValueError("Plan skeleton is missing non-empty reasoning.")
        tasks = data.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("Plan skeleton must contain a non-empty tasks list.")
        for index, item in enumerate(tasks, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Task skeleton {index} must be an object.")
            for key in ("task_id", "title", "object_name", "description"):
                if not str(item.get(key, "")).strip():
                    raise ValueError(f"Task skeleton {index} is missing {key}.")
            self._validate_not_assembly_task(item, f"Task skeleton {index}")
        task_ids = [str(item.get("task_id", "")).strip() for item in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Plan skeleton contains duplicate task_id values.")
        self._normalize_unique_object_names(tasks)

    def _validate_task_detail_payload(self, data: Dict[str, Any]) -> None:
        for key in ("task_id", "title", "object_name", "description", "preferred_primitive"):
            if not str(data.get(key, "")).strip():
                raise ValueError(f"Task detail is missing {key}.")
        self._validate_not_assembly_task(data, "Task detail")
        self._normalize_primitive(data.get("preferred_primitive", ""))
        self._normalize_viewpoint(data.get("refinement_viewpoint", "front"))
        self._coerce_bbox(data.get("target_bbox"))
        self._coerce_anchor_points(data.get("anchor_points"))
        self._coerce_structural_spec(data.get("structural_spec"))
        self._coerce_xyz_with_default(data.get("assembly_location"), "assembly_location", [0.0, 0.0, 0.0])
        self._coerce_xyz_with_default(
            data.get("assembly_rotation_degrees"),
            "assembly_rotation_degrees",
            [0.0, 0.0, 0.0],
        )

    def _validate_task_objects_payload(self, data: Dict[str, Any], tasks: List[ModelingTask]) -> None:
        task_objects = data.get("task_objects")
        if not isinstance(task_objects, list) or not task_objects:
            raise ValueError("task_objects must be a non-empty list.")
        task_ids = {item.task_id for item in tasks}
        for index, item in enumerate(task_objects, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"task_object {index} must be an object.")
            for key in ("name", "role", "task_id"):
                if not str(item.get(key, "")).strip():
                    raise ValueError(f"task_object {index} is missing {key}.")
            if str(item.get("task_id", "")) not in task_ids:
                raise ValueError(f"task_object {index} references unknown task_id.")
            allowed_count = int(item.get("allowed_count", 1))
            if allowed_count < 1:
                raise ValueError(f"task_object {index} allowed_count must be >= 1.")
            creation_policy = str(item.get("creation_policy", "create_if_missing")).strip()
            if creation_policy not in {"create_if_missing", "duplicate_from_source", "assemble_only"}:
                raise ValueError(f"task_object {index} has unsupported creation_policy.")

    def _validate_part_feedback_payload(self, data: Dict[str, Any]) -> None:
        if "approved" not in data:
            raise ValueError("Part feedback must include approved.")
        if not str(data.get("summary", "")).strip():
            raise ValueError("Part feedback must include non-empty summary.")
        if bool(data.get("approved", False)):
            return
        action = data.get("action")
        if not isinstance(action, dict):
            raise ValueError("Part feedback must include action when approved is false.")
        self._normalize_action_payload(action)
        self._validate_action_payload(action)

    def _validate_assembly_feedback_payload(self, data: Dict[str, Any]) -> None:
        if "approved" not in data:
            raise ValueError("Assembly feedback must include approved.")
        if not str(data.get("summary", "")).strip():
            raise ValueError("Assembly feedback must include non-empty summary.")
        if bool(data.get("approved", False)):
            return
        actions = data.get("actions", [])
        if not isinstance(actions, list) or not actions:
            raise ValueError("Assembly feedback must include actions when approved is false.")
        if len(actions) != 1:
            raise ValueError("Assembly feedback must include exactly one action per round.")
        for item in actions:
            if not isinstance(item, dict):
                raise ValueError("Assembly feedback actions must be objects.")
            self._normalize_action_payload(item)
            self._validate_action_payload(item)

    def _validate_action_payload(self, data: Dict[str, Any]) -> None:
        supported = {
            "select_object",
            "scale_uniform",
            "scale_axis_x",
            "scale_axis_y",
            "scale_axis_z",
            "set_object_scale",
            "move_object",
            "rotate_object",
            "show_object",
            "hide_object",
            "finish",
        }
        action_type = str(data.get("action_type", "")).strip()
        if action_type not in supported:
            raise ValueError(f"Unsupported action_type: {action_type!r}.")
        if not isinstance(data.get("parameters", {}), dict):
            raise ValueError("Action parameters must be an object.")
        if not str(data.get("reason", "")).strip():
            raise ValueError("Action reason must be non-empty.")

    @staticmethod
    def _normalize_action_payload(data: Dict[str, Any]) -> None:
        if not isinstance(data.get("parameters"), dict):
            data["parameters"] = {}

    @classmethod
    def _normalize_unique_object_names(cls, tasks: List[Dict[str, Any]]) -> None:
        used_names = set()
        for index, item in enumerate(tasks, start=1):
            raw_name = str(item.get("object_name", "")).strip()
            task_id = str(item.get("task_id", "")).strip()
            title = str(item.get("title", "")).strip()
            normalized = cls._slugify_identifier(raw_name)
            if not normalized:
                normalized = cls._slugify_identifier(task_id) or cls._slugify_identifier(title)
            if not normalized:
                normalized = f"part_{index}"
            unique_name = normalized
            suffix = 2
            while unique_name.lower() in used_names:
                unique_name = f"{normalized}_{suffix}"
                suffix += 1
            item["object_name"] = unique_name
            used_names.add(unique_name.lower())

    @staticmethod
    def _slugify_identifier(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_")

    @staticmethod
    def _build_image_inputs(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        image_inputs: List[Dict[str, str]] = []
        for item in items:
            image_path = Path(str(item.get("path", "")).strip())
            if not image_path.exists():
                continue
            image_inputs.append(
                {
                    "path": str(image_path),
                    "label": str(item.get("label", "")).strip(),
                    "viewpoint": str(item.get("viewpoint", "")).strip(),
                }
            )
        return image_inputs

    @classmethod
    def _build_image_inputs_from_review_bundle(cls, review_bundle: Dict[str, Any]) -> List[Dict[str, str]]:
        captures = review_bundle.get("captures", []) if isinstance(review_bundle, dict) else []
        items: List[Dict[str, str]] = []
        for item in captures:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "path": str(item.get("path", "")).strip(),
                    "label": str(item.get("description", "")).strip()
                    or f"{item.get('stage', 'review')} for {item.get('task_id', '')}".strip(),
                    "viewpoint": str(item.get("viewpoint", "")).strip(),
                }
            )
        return cls._build_image_inputs(items)

    @staticmethod
    def _normalize_primitive(value: Any) -> str:
        normalized = str(value or "uv_sphere").strip().lower().replace("-", "_").replace(" ", "_")
        primitive_map = {
            "uv_sphere": "uv_sphere",
            "sphere": "uv_sphere",
            "cube": "cube",
            "cylinder": "cylinder",
            "plane": "plane",
        }
        try:
            return primitive_map[normalized]
        except KeyError as exc:
            raise ValueError(
                "preferred_primitive must be one of: uv_sphere, cube, cylinder, plane."
            ) from exc

    @staticmethod
    def _normalize_viewpoint(value: Any) -> str:
        normalized = str(value or "front").strip().lower().replace("\\", "/")
        normalized = normalized.replace("-", " ").replace("_", " ")
        if "/" in normalized:
            normalized = normalized.split("/", 1)[0].strip()
        normalized = " ".join(normalized.split())
        viewpoint_map = {
            "front": "front",
            "front orthographic view": "front",
            "back": "back",
            "back orthographic view": "back",
            "left": "left",
            "left orthographic view": "left",
            "right": "right",
            "right orthographic view": "right",
            "side": "side",
            "top": "top",
            "top orthographic view": "top",
            "bottom": "bottom",
            "bottom orthographic view": "bottom",
            "isometric": "front",
        }
        try:
            return viewpoint_map[normalized]
        except KeyError as exc:
            raise ValueError(
                "refinement_viewpoint must be one of: front, back, left, right, side, top, bottom."
            ) from exc

    @staticmethod
    def _coerce_xyz(value: Any, field_name: str) -> List[float]:
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError(f"{field_name} must be an array of exactly 3 numbers.")
        try:
            return [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must contain only numeric values.") from exc

    @classmethod
    def _coerce_xyz_with_default(
        cls,
        value: Any,
        field_name: str,
        default: List[float],
    ) -> List[float]:
        if value in (None, "", "null"):
            return list(default)
        if isinstance(value, list) and len(value) == 3:
            try:
                return [float(item) for item in value]
            except (TypeError, ValueError):
                return list(default)
        return list(default)

    @staticmethod
    def _coerce_bbox(value: Any) -> BoundingBoxSpec:
        if not isinstance(value, dict):
            raise ValueError("target_bbox must be an object.")
        try:
            return BoundingBoxSpec(
                width=float(value["width"]),
                depth=float(value["depth"]),
                height=float(value["height"]),
            )
        except KeyError as exc:
            raise ValueError("target_bbox must include width, depth, and height.") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError("target_bbox values must be numeric.") from exc

    def _coerce_anchor_points(self, value: Any) -> List[AnchorPointSpec]:
        if not isinstance(value, list) or not value:
            raise ValueError("anchor_points must be a non-empty list.")
        anchor_points: List[AnchorPointSpec] = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"anchor_points[{index}] must be an object.")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError(f"anchor_points[{index}] is missing name.")
            anchor_points.append(
                AnchorPointSpec(
                    name=name,
                    position=self._coerce_xyz(item.get("position"), f"anchor_points[{index}].position"),
                    description=str(item.get("description", "")).strip(),
                )
            )
        return anchor_points

    @staticmethod
    def _coerce_structural_spec(value: Any) -> StructuralSpec:
        if not isinstance(value, dict):
            raise ValueError("structural_spec must be an object.")
        return StructuralSpec(
            parent_task_id=str(value.get("parent_task_id", "")).strip(),
            attach_to=str(value.get("attach_to", "")).strip(),
            symmetry_group=str(value.get("symmetry_group", "")).strip(),
            sizing_notes=str(value.get("sizing_notes", "")).strip(),
            placement_notes=str(value.get("placement_notes", "")).strip(),
        )

    @staticmethod
    def _validate_not_assembly_task(data: Dict[str, Any], label: str) -> None:
        combined = " ".join(
            [
                str(data.get("title", "")),
                str(data.get("object_name", "")),
                str(data.get("description", "")),
            ]
        ).strip().lower()
        blocked_terms = (
            "assemble",
            "assembly",
            "final assembly",
            "whole chair",
            "whole object",
            "final object",
            "complete chair",
            "review task",
            "scene task",
        )
        if any(term in combined for term in blocked_terms):
            raise ValueError(f"{label} must describe one physical part, not an assembly-only step.")

