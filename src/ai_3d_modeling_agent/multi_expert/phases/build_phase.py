"""BuildPhase builds geometry for each part family (process-driven)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from ai_3d_modeling_agent.memory.session_paths import (
    ensure_session_runtime_dir,
    session_build_execution_plan_path,
)
from ai_3d_modeling_agent.multi_expert.artifacts import BuildArtifact, PlanArtifact, SpecArtifact
from ai_3d_modeling_agent.multi_expert.core.action_plan import (
    AgentActionPlan,
    BUILD_ACTIONS,
    fallback_json_payload,
    parse_agent_action_plan,
)
from ai_3d_modeling_agent.multi_expert.core.convener import ProcessConvener
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.builder_intent import BuilderIntent, parse_builder_intent
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import append_build_log, build_builder_todos_from_plan, write_todo_markdown
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.planning import normalize_build_execution_plan, validate_plan_structure
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.multi_expert.core.tool_logging import append_session_tool_call, format_tool_calls_markdown
from ai_3d_modeling_agent.schemas.part import SCALE_NORMALIZATION

logger = logging.getLogger(__name__)


class BuildPhase(Phase):
    """Build geometry for each part family in the plan."""

    def __init__(self) -> None:
        super().__init__(
            name="build",
            goal="Build geometry for each part family",
            participants=[],
            convener=ProcessConvener(participants=[]),
            termination=TerminationPolicy(max_rounds=1, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=BuildArtifact,
        )

    def run(
        self,
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact,
        context: Any = None,
        object_ops: Any = None,
        executor: Any = None,
        llm: Any = None,
        event_emitter: Callable | None = None,
    ) -> list[BuildArtifact]:
        """Build all parts defined in the execution plan."""
        from ai_3d_modeling_agent.schemas.actions import Action

        _emit = event_emitter or self._emit_event
        structural_issues = validate_plan_structure(plan_artifact, spec_artifact)
        if structural_issues:
            return self._fail_fast_on_invalid_plan(
                plan_artifact=plan_artifact,
                spec_artifact=spec_artifact,
                issues=structural_issues,
                emit=_emit,
            )
        execution_plan = normalize_build_execution_plan(plan_artifact, spec_artifact)
        self._persist_execution_plan(context, execution_plan.to_dict())

        if _emit:
            _emit(
                "build",
                "phase_open",
                f"Build {len(execution_plan.items)} planned part families.",
                role="builder",
                speaker="Builder",
                round=0,
                summary=f"Build {len(execution_plan.items)} planned part families.",
                full_content=f"Build {len(execution_plan.items)} planned part families.",
            )

        if llm is not None:
            return self._run_builder_todo_intents(
                plan_artifact=plan_artifact,
                spec_artifact=spec_artifact,
                normalized_plan=execution_plan.to_dict(),
                context=context,
                object_ops=object_ops,
                executor=executor,
                llm=llm,
                emit=_emit,
            )

        results: list[BuildArtifact] = []
        for item in execution_plan.items:
            source_name = f"{item.family}_source"
            instance_names: list[str] = []
            action_history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            planning_warnings = list(item.planning_warnings)
            scale = [round(axis * SCALE_NORMALIZATION, 4) for axis in item.scale]

            try:
                if object_ops is not None and executor is not None:
                    object_ops.create_primitive(item.primitive_type, source_name)
                    build_action = {
                        "action_type": "create_primitive",
                        "parameters": {"primitive_type": item.primitive_type, "name": source_name},
                    }
                    action_history.append(build_action)
                    tool_calls.append(
                        append_session_tool_call(
                            context,
                            tool_name="create_primitive",
                            arguments={"primitive_type": item.primitive_type, "name": source_name},
                            result={"part_family": item.family},
                        )
                    )

                    executor.execute(
                        Action(
                            action_type="set_object_scale",
                            parameters={"name": source_name, "scale": scale},
                            reason=f"Scale {item.family} to target bbox",
                        )
                    )
                    scale_action = {
                        "action_type": "set_object_scale",
                        "parameters": {"name": source_name, "scale": scale},
                    }
                    action_history.append(scale_action)
                    tool_calls.append(
                        append_session_tool_call(
                            context,
                            tool_name="set_object_scale",
                            arguments={"name": source_name, "scale": scale},
                            result={"part_family": item.family},
                        )
                    )

                    for index in range(1, item.instance_count + 1):
                        instance_name = f"{item.family}_{index:02d}"
                        object_ops.duplicate_object(source_name, instance_name)
                        instance_names.append(instance_name)
                        duplicate_action = {
                            "action_type": "duplicate_object",
                            "parameters": {"name": source_name, "new_name": instance_name},
                        }
                        action_history.append(duplicate_action)
                        tool_calls.append(
                            append_session_tool_call(
                                context,
                                tool_name="duplicate_object",
                                arguments={"name": source_name, "new_name": instance_name},
                                result={"part_family": item.family},
                            )
                        )

                    deleted = object_ops.delete_object(source_name)
                    delete_action = {
                        "action_type": "delete_object",
                        "parameters": {"name": source_name},
                        "result": {"deleted": bool(deleted)},
                    }
                    action_history.append(delete_action)
                    tool_calls.append(
                        append_session_tool_call(
                            context,
                            tool_name="delete_object",
                            arguments={"name": source_name},
                            result={"deleted": bool(deleted), "part_family": item.family},
                            is_error=not deleted,
                        )
                    )
                    if not deleted:
                        planning_warnings.append(
                            f"Builder template object {source_name} could not be deleted after instancing."
                        )

                artifact = BuildArtifact(
                    part_name=item.family,
                    source_object_name=source_name,
                    instance_names=instance_names,
                    status="built",
                    action_history=action_history,
                    responsibility_refs=list(item.responsibility_refs),
                    planning_warnings=planning_warnings,
                )
            except Exception as exc:
                logger.exception("Build failed for part '%s'", item.family)
                artifact = BuildArtifact(
                    part_name=item.family,
                    source_object_name=source_name,
                    instance_names=instance_names,
                    status="failed",
                    responsibility_refs=list(item.responsibility_refs),
                    planning_warnings=planning_warnings,
                    failure_notes=[str(exc)],
                )

            results.append(artifact)
            append_build_log(
                context,
                title=f"Build {artifact.part_name}",
                body=f"Status: {artifact.status}\nInstances: {', '.join(artifact.instance_names) or 'none'}",
                validation={"status": artifact.status, "instances": list(artifact.instance_names)},
            )

            if _emit:
                _emit(
                    "build",
                    "build_step",
                    f"Build {item.family} as {item.primitive_type} with scale={scale} and {item.instance_count} instances.",
                    role="builder",
                    speaker="Builder",
                    round=item.step_index + 1,
                    summary=f"Build {item.family} as {item.primitive_type} with scale={scale} and {item.instance_count} instances.",
                    full_content=format_tool_calls_markdown(tool_calls) or f"Build {item.family} as {item.primitive_type} with scale={scale} and {item.instance_count} instances.",
                    tool_calls=tool_calls,
                )

        if _emit:
            _emit(
                "build",
                "phase_close",
                f"Completed build planning for {len(results)} part families.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Completed build planning for {len(results)} part families.",
                full_content=f"Completed build planning for {len(results)} part families.",
            )

        return results

    def _run_builder_todo_intents(
        self,
        *,
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact,
        normalized_plan: dict[str, Any],
        context: Any,
        object_ops: Any,
        executor: Any,
        llm: Any,
        emit: Callable | None,
    ) -> list[BuildArtifact]:
        """Ask Builder for one Markdown intent per build todo, then execute in Python."""
        if object_ops is None or executor is None:
            return [
                BuildArtifact(
                    part_name="build",
                    status="blocked",
                    failure_notes=["Builder intent execution requires object_ops and executor."],
                )
            ]

        todos = build_builder_todos_from_plan(plan_artifact)
        item_by_family = {
            str(item.get("family", "")).strip(): item
            for item in list(normalized_plan.get("items", []) or [])
            if str(item.get("family", "")).strip()
        }
        build_todos = [todo for todo in todos if str(todo.get("id", "")).startswith("build:")]
        results: list[BuildArtifact] = []
        for index, todo in enumerate(build_todos, start=1):
            todo_id = str(todo.get("id", "")).strip()
            family = todo_id.split(":", 1)[1] if ":" in todo_id else str(todo.get("target", "")).strip()
            item = item_by_family.get(family, {})
            write_todo_markdown(context, todos=todos, current_todo=todo_id)
            raw_intent = self._request_builder_intent(
                llm=llm,
                context=context,
                todo=todo,
                family=family,
                normalized_item=item,
                spec=spec_artifact.parts.get(family, {}) if isinstance(spec_artifact.parts, dict) else {},
            )
            fallback_warning = ""
            try:
                try:
                    parse_builder_intent(raw_intent, expected_intent="create")
                except ValueError as parse_exc:
                    if not _should_use_python_intent_fallback(raw_intent, parse_exc):
                        raise
                    intent = self._fallback_create_intent(family, item)
                    fallback_warning = (
                        "Builder returned malformed Markdown intent; "
                        f"used Python normalized build plan fallback: {parse_exc}"
                    )
                    artifact, tool_calls = self._execute_create_intent(
                        intent=intent,
                        family=family,
                        normalized_item=item,
                        context=context,
                        object_ops=object_ops,
                        executor=executor,
                    )
                else:
                    raw_action_json, action_plan = self._extract_build_action_plan_from_markdown(
                        llm=llm,
                        context=context,
                        todo=todo,
                        family=family,
                        normalized_item=item,
                        builder_markdown=raw_intent,
                    )
                    artifacts, tool_calls = self._execute_build_action_plan(
                        action_plan=action_plan,
                        context=context,
                        executor=executor,
                    )
                    artifact = artifacts[0] if artifacts else BuildArtifact(part_name=family, status="failed", failure_notes=["No build artifact was produced from extracted action JSON."])
                    if raw_action_json:
                        artifact.action_history.append({"extracted_action_json": raw_action_json})
                if fallback_warning:
                    artifact.planning_warnings.append(fallback_warning)
                todo["status"] = "done" if artifact.status == "built" else "blocked"
            except Exception as exc:
                logger.exception("Builder Markdown intent failed for '%s'", family)
                artifact = BuildArtifact(
                    part_name=family or "build",
                    status="failed",
                    failure_notes=[str(exc)],
                    action_history=[{"raw_builder_intent": raw_intent}],
                )
                tool_calls = []
                todo["status"] = "blocked"
            results.append(artifact)
            validation = {
                "todo_id": todo_id,
                "status": artifact.status,
                "instances": list(artifact.instance_names),
                "failure_notes": list(artifact.failure_notes),
            }
            append_build_log(
                context,
                title=f"Builder todo {todo_id}",
                body=(
                    f"Builder operation:\n\n{raw_intent}\n\n"
                    + (f"Python fallback:\n\n{fallback_warning}\n\n" if fallback_warning else "")
                    + f"Result: {artifact.status}"
                ),
                validation=validation,
            )
            write_todo_markdown(context, todos=todos, current_todo="")
            if emit:
                summary = f"Builder completed {todo_id}" if artifact.status == "built" else f"Builder failed {todo_id}"
                emit(
                    "build",
                    "build_step",
                    summary,
                    role="builder",
                    speaker="Builder",
                    round=index,
                    summary=summary,
                    full_content=format_tool_calls_markdown(tool_calls) or raw_intent,
                    tool_calls=tool_calls,
                    current_todo=todo_id,
                    validation=validation,
                )
        if emit:
            emit(
                "build",
                "phase_close",
                f"Completed Builder todo execution for {len(results)} build todos.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Completed Builder todo execution for {len(results)} build todos.",
                full_content=f"Completed Builder todo execution for {len(results)} build todos.",
            )
        return results

    def _request_builder_intent(
        self,
        *,
        llm: Any,
        context: Any,
        todo: dict[str, Any],
        family: str,
        normalized_item: dict[str, Any],
        spec: Any,
    ) -> str:
        prompt = {
            "task": (
                "Produce exactly one executable Builder Markdown operation for the current todo. "
                "You may read docs/blender_build_capabilities.md before answering. "
                "The final answer must start with '## Operation' and must not include tool-call narration, "
                "delegation narration, code fences, JSON, or self-correction text. "
                "If Task Tool delegation is unavailable, write the intent directly from normalized_build_item."
            ),
            "ao_route": "moderator",
            "delegation_required": True,
            "delegated_agent": "builder",
            "strict_final_answer_contract": [
                "First non-whitespace characters must be: ## Operation",
                "Required sections: ## Operation, ## Target, ## Parameters, ## Validation",
                "Operation may be a short natural-language create/build statement.",
                "No preface, no explanation, no code fence, no Task Tool transcript",
            ],
            "current_todo": todo,
            "target_family": family,
            "normalized_build_item": normalized_item,
            "part_spec": spec,
            "required_markdown_shape": {
                "Operation": "Natural-language one-step create/build operation using documented Blender tools",
                "Target": family,
                "Parameters": [
                    "primitive_type: cube | cylinder | uv_sphere | plane",
                    "source_name: <temporary source object>",
                    "instance_count: <integer>",
                    "scale: [x, y, z]",
                ],
                "Validation": "object existence and scale will be checked by Python",
            },
            "rules": [
                "Handle only current_todo.",
                "Use docs/blender_build_capabilities.md as the tool reference when you need available function names or parameters.",
                "Do not create or mention extra parts.",
                "Do not return JSON.",
                "Do not call Blender or MCP yourself.",
                "If using a subagent fails, still return the Markdown operation from normalized_build_item.",
            ],
        }
        messages = [{"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)}]
        return str(
            llm.call(
                system_prompt="",
                messages=messages,
                agent="moderator",
                label=f"build.todo.{family}",
                skill="",
                context={
                    **(context or {}),
                    "phase_name": "build",
                    "agent_role": "builder",
                    "delegated_agent": "builder",
                    "meeting_turn_kind": "builder_todo",
                    "current_todo": str(todo.get("id", "")),
                }
                if isinstance(context, dict)
                else {
                    "phase_name": "build",
                    "agent_role": "builder",
                    "delegated_agent": "builder",
                    "meeting_turn_kind": "builder_todo",
                    "current_todo": str(todo.get("id", "")),
                },
            )
        )

    def _fallback_create_intent(self, family: str, normalized_item: dict[str, Any]) -> BuilderIntent:
        if not normalized_item:
            raise ValueError(f"Cannot fallback builder intent for {family!r}; normalized build item is missing.")
        return BuilderIntent(
            intent="create",
            target=family,
            parameters={
                "primitive_type": normalized_item.get("primitive_type", "cube"),
                "source_name": f"{family}_source",
                "instance_count": normalized_item.get("instance_count", 1),
                "scale": normalized_item.get("scale", [1.0, 1.0, 1.0]),
            },
            validation="Python normalized build plan fallback.",
            raw_markdown="",
        )

    def _extract_build_action_plan_from_markdown(
        self,
        *,
        llm: Any,
        context: Any,
        todo: dict[str, Any],
        family: str,
        normalized_item: dict[str, Any],
        builder_markdown: str,
    ) -> tuple[str, AgentActionPlan]:
        prompt = {
            "task": "Extract Python-executable Blender build action JSON from the completed Builder Markdown operation.",
            "source_documents": {
                "builder_markdown": builder_markdown,
                "capability_reference": "docs/blender_build_capabilities.md",
            },
            "current_todo": todo,
            "target_family": family,
            "normalized_build_item": normalized_item,
            "required_ready_shape": {
                "status": "ready",
                "parts": [
                    {
                        "part_name": family,
                        "source_object_name": f"{family}_source",
                        "instance_names": [f"{family}_01"],
                        "actions": [
                            {
                                "action_type": "create_primitive",
                                "parameters": {"primitive_type": "cube", "name": f"{family}_source"},
                            },
                            {
                                "action_type": "set_object_scale",
                                "parameters": {"name": f"{family}_source", "scale": [1.0, 1.0, 1.0]},
                            },
                            {
                                "action_type": "duplicate_object",
                                "parameters": {"name": f"{family}_source", "new_name": f"{family}_01"},
                            },
                            {
                                "action_type": "delete_object",
                                "parameters": {"name": f"{family}_source"},
                            },
                        ],
                    }
                ],
            },
            "rules": [
                "Do not modify the Builder Markdown.",
                "Extract JSON only from Builder Markdown, normalized_build_item, and the capability reference.",
                "Use only action types and parameter names from docs/blender_build_capabilities.md.",
                "If required values are missing from Markdown but present in normalized_build_item, use normalized_build_item.",
                "If the operation is unsupported by the capability reference, return blocked.",
            ],
        }
        messages = [{"role": "user", "content": fallback_json_payload(prompt)}]
        last_raw = ""
        last_error = ""
        for attempt in range(2):
            raw = llm.call(
                system_prompt="",
                messages=messages,
                agent="moderator",
                label="build.markdown_to_actions" if attempt == 0 else "build.markdown_to_actions.repair",
                skill="blender-build-actions",
                context={**(context or {}), "phase_name": "build", "agent_role": "builder", "delegated_agent": "builder", "meeting_turn_kind": "builder_action_extraction"} if isinstance(context, dict) else {"phase_name": "build", "agent_role": "builder", "delegated_agent": "builder", "meeting_turn_kind": "builder_action_extraction"},
            )
            try:
                parsed = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build Markdown extraction")
                if parsed.status == "ready" and not parsed.parts:
                    raise ValueError("Build Markdown extraction is ready but contains no parts")
                if parsed.status == "ready":
                    _normalize_extracted_build_part_identity(parsed, family)
                    _normalize_extracted_build_instances(parsed, family, normalized_item)
                _normalize_build_action_scales(parsed, {"items": [normalized_item] if normalized_item else []})
                if parsed.status != "ready":
                    reason = parsed.reason or parsed.issue or "Builder Markdown extraction is not executable."
                    return raw, AgentActionPlan(status=parsed.status, reason=reason, missing_capability=parsed.missing_capability, issue=parsed.issue, route_to=parsed.route_to, requested_clarification=parsed.requested_clarification)
                return raw, parsed
            except Exception as exc:
                last_raw = raw
                last_error = str(exc)
                messages = [
                    {
                        "role": "user",
                        "content": fallback_json_payload(
                            {
                                "task": "Repair the previous Markdown-to-JSON extraction. Do not change the Builder Markdown; extract valid JSON only.",
                                "format_or_validation_error": last_error,
                                "previous_response_preview": last_raw[:1600],
                                "builder_markdown": builder_markdown,
                                "current_todo": todo,
                                "target_family": family,
                                "normalized_build_item": normalized_item,
                                "required_ready_shape": prompt["required_ready_shape"],
                            }
                        ),
                    }
                ]
        raise ValueError(f"Builder Markdown action extraction failed: {last_error}")

    def _execute_build_action_plan(
        self,
        *,
        action_plan: AgentActionPlan,
        context: Any,
        executor: Any,
    ) -> tuple[list[BuildArtifact], list[dict[str, Any]]]:
        from ai_3d_modeling_agent.schemas.actions import Action

        if action_plan.status != "ready":
            reason = action_plan.reason or action_plan.issue or "Builder Markdown extraction is not executable."
            return [BuildArtifact(part_name="build", status="blocked" if action_plan.status == "blocked" else "needs_revision", failure_notes=[reason])], []

        results: list[BuildArtifact] = []
        all_tool_calls: list[dict[str, Any]] = []
        for index, part in enumerate(action_plan.parts, start=1):
            part_name = str(part.get("part_name", f"part_{index}")).strip() or f"part_{index}"
            source_name = str(part.get("source_object_name", "")).strip()
            instance_names = [str(name) for name in part.get("instance_names", []) or []]
            action_history: list[dict[str, Any]] = []
            failure_notes: list[str] = []
            try:
                for action_payload in list(part.get("actions", []) or []):
                    action = Action(
                        action_type=str(action_payload.get("action_type", "")),
                        parameters=dict(action_payload.get("parameters", {}) or {}),
                        reason=str(action_payload.get("reason", "Builder Markdown extraction")),
                    )
                    executor.execute(action)
                    action_history.append({"action_type": action.action_type, "parameters": dict(action.parameters), "reason": action.reason})
                    all_tool_calls.append(
                        append_session_tool_call(
                            context,
                            tool_name=action.action_type,
                            arguments=dict(action.parameters),
                            result={"part_family": part_name},
                        )
                    )
            except Exception as exc:
                logger.exception("Extracted Builder action JSON failed for part '%s'", part_name)
                failure_notes.append(str(exc))
            results.append(
                BuildArtifact(
                    part_name=part_name,
                    source_object_name=source_name,
                    instance_names=instance_names,
                    status="failed" if failure_notes else "built",
                    action_history=action_history,
                    failure_notes=failure_notes,
                )
            )
        return results, all_tool_calls

    def _execute_create_intent(
        self,
        *,
        intent: BuilderIntent,
        family: str,
        normalized_item: dict[str, Any],
        context: Any,
        object_ops: Any,
        executor: Any,
    ) -> tuple[BuildArtifact, list[dict[str, Any]]]:
        from ai_3d_modeling_agent.schemas.actions import Action

        if intent.intent != "create":
            raise ValueError(f"Build todo requires create intent, got {intent.intent}")
        target = intent.target.strip()
        if family and target and target.lower() not in {family.lower(), f"build:{family}".lower()}:
            raise ValueError(f"Builder target {target!r} does not match current family {family!r}")
        primitive = str(
            intent.parameters.get("primitive_type")
            or intent.parameters.get("primitive")
            or normalized_item.get("primitive_type")
            or "cube"
        ).strip()
        source_name = str(intent.parameters.get("source_name") or intent.parameters.get("name") or f"{family}_source").strip()
        instance_count = max(1, int(intent.parameters.get("instance_count") or normalized_item.get("instance_count") or 1))
        raw_scale = intent.parameters.get("scale") or normalized_item.get("scale") or [1.0, 1.0, 1.0]
        scale = _blender_scale(raw_scale)
        action_history: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []

        actions = [
            Action("create_primitive", {"primitive_type": primitive, "name": source_name}, reason="Builder create intent"),
            Action("set_object_scale", {"name": source_name, "scale": scale}, reason="Builder create intent scale"),
        ]
        instance_names = [f"{family}_{index:02d}" for index in range(1, instance_count + 1)]
        actions.extend(
            Action("duplicate_object", {"name": source_name, "new_name": instance_name}, reason="Builder create intent instance")
            for instance_name in instance_names
        )
        actions.append(Action("delete_object", {"name": source_name}, reason="Remove temporary source object"))

        for action in actions:
            executor.execute(action)
            action_history.append({"action_type": action.action_type, "parameters": dict(action.parameters), "reason": action.reason})
            tool_calls.append(
                append_session_tool_call(
                    context,
                    tool_name=action.action_type,
                    arguments=dict(action.parameters),
                    result={"part_family": family},
                )
            )

        missing = [name for name in instance_names if not object_ops.object_exists(name)]
        if missing:
            raise RuntimeError(f"Builder create validation failed; missing instances: {', '.join(missing)}")
        validation_scales = {name: object_ops.get_object_scale(name) for name in instance_names}
        artifact = BuildArtifact(
            part_name=family,
            source_object_name=source_name,
            instance_names=instance_names,
            status="built",
            action_history=action_history,
            planning_warnings=[],
        )
        tool_calls.append(
            append_session_tool_call(
                context,
                tool_name="scene_validation",
                arguments={"instances": instance_names},
                result={"exists": True, "scales": validation_scales},
            )
        )
        return artifact, tool_calls

    def _run_agent_action_plan(
        self,
        *,
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact,
        normalized_plan: dict[str, Any],
        context: Any,
        object_ops: Any,
        executor: Any,
        llm: Any,
        emit: Callable | None,
    ) -> list[BuildArtifact]:
        from ai_3d_modeling_agent.schemas.actions import Action

        prompt = {
            "task": "Deprecated compatibility path: ask the builder for one-step Markdown intent. Active runtime uses Python process execution.",
            "ao_route": "moderator",
            "delegation_required": True,
            "delegated_agent": "builder",
            "python_selected_structured_output": "markdown-builder-intent",
            "output_rules": [
                "Return Markdown builder intent, not JSON.",
                "Do not mention Task Tool usage, routing, child sessions, or delegation.",
                "Do not return a skill_name/input wrapper.",
                "Use only documented action_type values.",
                "For each normalized item, create source geometry, scale it, duplicate requested instances, then delete the source.",
            ],
            "status_contract": ["ready", "blocked", "needs_revision"],
            "required_ready_shape": {
                "status": "ready",
                "parts": [
                    {
                        "part_name": "main_body",
                        "source_object_name": "main_body_source",
                        "instance_names": ["main_body_01"],
                        "actions": [
                            {
                                "action_type": "create_primitive",
                                "parameters": {"primitive_type": "cube", "name": "main_body_source"},
                            },
                            {
                                "action_type": "set_object_scale",
                                "parameters": {"name": "main_body_source", "scale": [1.0, 1.0, 1.0]},
                            },
                            {
                                "action_type": "duplicate_object",
                                "parameters": {"name": "main_body_source", "new_name": "main_body_01"},
                            },
                            {
                                "action_type": "delete_object",
                                "parameters": {"name": "main_body_source"},
                            },
                        ],
                    }
                ],
            },
            "normalized_build_plan": normalized_plan,
        }
        raw, action_plan = self._request_action_plan(
            llm=llm,
            prompt=prompt,
            context=context,
        )
        _normalize_build_action_scales(action_plan, normalized_plan)
        if action_plan.status != "ready":
            reason = action_plan.reason or action_plan.issue or "Builder action plan is not executable."
            if emit:
                emit(
                    "build",
                    action_plan.status,
                    reason,
                    role="builder",
                    speaker="Builder",
                    round=1,
                    summary=reason,
                    full_content=raw,
                    missing_capability=action_plan.missing_capability,
                    route_to=action_plan.route_to,
                    requested_clarification=action_plan.requested_clarification,
                )
            return [
                BuildArtifact(
                    part_name="build",
                    status="blocked" if action_plan.status == "blocked" else "needs_revision",
                    failure_notes=[reason],
                    planning_warnings=[action_plan.missing_capability] if action_plan.missing_capability else [],
                )
            ]

        results: list[BuildArtifact] = []
        for index, part in enumerate(action_plan.parts, start=1):
            part_name = str(part.get("part_name", f"part_{index}")).strip() or f"part_{index}"
            source_name = str(part.get("source_object_name", "")).strip()
            instance_names = [str(name) for name in part.get("instance_names", []) or []]
            actions = list(part.get("actions", []) or [])
            action_history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            failure_notes: list[str] = []
            try:
                if object_ops is not None and executor is not None:
                    for action_payload in actions:
                        action = Action(
                            action_type=str(action_payload.get("action_type", "")),
                            parameters=dict(action_payload.get("parameters", {}) or {}),
                            reason=str(action_payload.get("reason", "")),
                        )
                        executor.execute(action)
                        action_history.append({"action_type": action.action_type, "parameters": dict(action.parameters)})
                        tool_calls.append(
                            append_session_tool_call(
                                context,
                                tool_name=action.action_type,
                                arguments=dict(action.parameters),
                                result={"part_family": part_name},
                            )
                        )
            except Exception as exc:
                logger.exception("Builder action JSON failed for part '%s'", part_name)
                failure_notes.append(str(exc))
            artifact = BuildArtifact(
                part_name=part_name,
                source_object_name=source_name,
                instance_names=instance_names,
                status="failed" if failure_notes else "built",
                action_history=action_history,
                failure_notes=failure_notes,
            )
            results.append(artifact)
            if emit:
                summary = f"Build {part_name} from builder action JSON."
                emit(
                    "build",
                    "build_step",
                    summary,
                    role="builder",
                    speaker="Builder",
                    round=index,
                    summary=summary,
                    full_content=format_tool_calls_markdown(tool_calls) or fallback_json_payload(actions),
                    tool_calls=tool_calls,
                )
        return results

    def _request_action_plan(self, *, llm: Any, prompt: dict[str, Any], context: Any) -> tuple[str, Any]:
        messages = [{"role": "user", "content": fallback_json_payload(prompt)}]
        last_raw = ""
        last_error = ""
        for attempt in range(2):
            raw = llm.call(
                system_prompt="",
                messages=messages,
                agent="moderator",
                label="build.action_plan" if attempt == 0 else "build.action_plan.repair",
                skill="",
                context={**(context or {}), "phase_name": "build", "agent_role": "builder", "delegated_agent": "builder"} if isinstance(context, dict) else {"phase_name": "build", "agent_role": "builder", "delegated_agent": "builder"},
            )
            try:
                parsed = parse_agent_action_plan(raw, allowed_actions=BUILD_ACTIONS, context_label="Build")
                if parsed.status == "ready" and not parsed.parts:
                    raise ValueError("Build action plan is ready but contains no parts")
                return raw, parsed
            except Exception as exc:
                last_raw = raw
                last_error = str(exc)
                messages = [
                    {
                        "role": "user",
                        "content": fallback_json_payload(
                            {
                                "task": "Repair the previous builder response into the required build action JSON.",
                                "format_error": last_error,
                                "previous_response_preview": last_raw[:1600],
                                "required_ready_shape": prompt["required_ready_shape"],
                                "normalized_build_plan": prompt["normalized_build_plan"],
                                "output_rules": prompt["output_rules"],
                            }
                        ),
                    }
                ]
        fallback = _fallback_build_action_plan(prompt["normalized_build_plan"])
        parse_agent_action_plan(
            fallback_json_payload(fallback.__dict__),
            allowed_actions=BUILD_ACTIONS,
            context_label="Build fallback",
        )
        return fallback_json_payload(fallback.__dict__), fallback

    def _fail_fast_on_invalid_plan(
        self,
        *,
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact,
        issues: list[dict[str, Any]],
        emit: Callable | None,
    ) -> list[BuildArtifact]:
        summaries = [str(issue.get("summary", "")).strip() for issue in issues if str(issue.get("summary", "")).strip()]
        families = self._ordered_build_families(plan_artifact, spec_artifact)
        if emit:
            emit(
                "build",
                "phase_open",
                f"Build aborted: planning contract is invalid for {len(families)} families.",
                role="builder",
                speaker="Builder",
                round=0,
                summary=f"Build aborted: planning contract is invalid for {len(families)} families.",
                full_content="\n".join(summaries) or "Planning contract is invalid.",
            )
        results: list[BuildArtifact] = []
        for index, family in enumerate(families, start=1):
            relevant = [summary for summary in summaries if family in summary] or summaries
            artifact = BuildArtifact(
                part_name=family,
                status="failed",
                planning_warnings=[],
                failure_notes=list(relevant),
            )
            results.append(artifact)
            if emit:
                emit(
                    "build",
                    "build_step",
                    f"Skipped build for {family} due to invalid planning contract.",
                    role="builder",
                    speaker="Builder",
                    round=index,
                    summary=f"Skipped build for {family} due to invalid planning contract.",
                    full_content="\n".join(relevant) or f"Skipped build for {family} due to invalid planning contract.",
                    skipped=True,
                    unresolved_planning_gap=True,
                    missing_contract_fields=[],
                    tool_calls=[],
                )
        if emit:
            emit(
                "build",
                "phase_close",
                f"Build stopped because the planning contract is invalid for {len(families)} families.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Build stopped because the planning contract is invalid for {len(families)} families.",
                full_content="\n".join(summaries) or "Planning contract is invalid.",
            )
        return results

    def _ordered_build_families(self, plan_artifact: PlanArtifact, spec_artifact: SpecArtifact) -> list[str]:
        families: list[str] = []
        for step in plan_artifact.steps:
            family = str(step.get("family", "")).strip()
            if family and family not in families:
                families.append(family)
        for item in plan_artifact.build_responsibilities:
            if not isinstance(item, dict):
                continue
            family = str(item.get("family", "")).strip()
            if family and family not in families:
                families.append(family)
        if isinstance(spec_artifact.parts, dict):
            for family in spec_artifact.parts.keys():
                text = str(family).strip()
                if text and text not in families:
                    families.append(text)
        return families

    def _persist_execution_plan(self, context: Any, payload: dict[str, Any]) -> None:
        state = context if isinstance(context, dict) else {}
        runtime_root_value = state.get("runtime_root")
        session_id = str(state.get("session_id", "")).strip()
        if not runtime_root_value or not session_id:
            return
        runtime_root = Path(str(runtime_root_value))
        ensure_session_runtime_dir(runtime_root, session_id)
        path = session_build_execution_plan_path(runtime_root, session_id)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)


def _fallback_build_action_plan(normalized_plan: dict[str, Any]) -> AgentActionPlan:
    parts: list[dict[str, Any]] = []
    for item in list(normalized_plan.get("items", []) or []):
        family = str(item.get("family", "")).strip()
        if not family:
            continue
        source_name = f"{family}_source"
        instance_count = max(1, int(item.get("instance_count", 1) or 1))
        instance_names = [f"{family}_{index:02d}" for index in range(1, instance_count + 1)]
        actions: list[dict[str, Any]] = [
            {
                "action_type": "create_primitive",
                "parameters": {"primitive_type": str(item.get("primitive_type", "cube") or "cube"), "name": source_name},
            },
            {
                "action_type": "set_object_scale",
                "parameters": {"name": source_name, "scale": _blender_scale(item.get("scale", [1.0, 1.0, 1.0]))},
            },
        ]
        actions.extend(
            {
                "action_type": "duplicate_object",
                "parameters": {"name": source_name, "new_name": instance_name},
            }
            for instance_name in instance_names
        )
        actions.append({"action_type": "delete_object", "parameters": {"name": source_name}})
        parts.append(
            {
                "part_name": family,
                "source_object_name": source_name,
                "instance_names": instance_names,
                "actions": actions,
            }
        )
    if not parts:
        return AgentActionPlan(status="blocked", reason="No build items are available for fallback action planning.")
    return AgentActionPlan(status="ready", parts=parts)


def _normalize_build_action_scales(action_plan: AgentActionPlan, normalized_plan: dict[str, Any]) -> None:
    scale_by_family = {
        str(item.get("family", "")).strip(): _blender_scale(item.get("scale", [1.0, 1.0, 1.0]))
        for item in list(normalized_plan.get("items", []) or [])
        if str(item.get("family", "")).strip()
    }
    for part in action_plan.parts:
        if not isinstance(part, dict):
            continue
        family = str(part.get("part_name", "")).strip()
        source_name = str(part.get("source_object_name", "")).strip()
        target_scale = scale_by_family.get(family)
        if not target_scale:
            continue
        for action in list(part.get("actions", []) or []):
            if not isinstance(action, dict) or action.get("action_type") != "set_object_scale":
                continue
            parameters = action.setdefault("parameters", {})
            if isinstance(parameters, dict) and (not source_name or str(parameters.get("name", "")).strip() == source_name):
                parameters["scale"] = list(target_scale)


def _normalize_extracted_build_part_identity(action_plan: AgentActionPlan, family: str) -> None:
    canonical = str(family or "").strip()
    if not canonical:
        return
    for part in action_plan.parts:
        if isinstance(part, dict):
            part["part_name"] = canonical


def _normalize_extracted_build_instances(action_plan: AgentActionPlan, family: str, normalized_item: dict[str, Any]) -> None:
    canonical = str(family or "").strip()
    if not canonical:
        return
    try:
        expected_count = int((normalized_item or {}).get("instance_count", 1) or 1)
    except (TypeError, ValueError):
        expected_count = 1
    expected_count = max(1, expected_count)
    expected_names = [f"{canonical}_{index:02d}" for index in range(1, expected_count + 1)]
    for part in action_plan.parts:
        if not isinstance(part, dict):
            continue
        actions = list(part.get("actions", []) or [])
        source_name = str(part.get("source_object_name", "") or "").strip() or _source_name_from_actions(actions) or f"{canonical}_source"
        part["source_object_name"] = source_name
        existing_names = [
            str(name).replace("\\_", "_").strip()
            for name in list(part.get("instance_names", []) or [])
            if str(name).strip()
        ]
        for action in actions:
            if not isinstance(action, dict) or str(action.get("action_type", "")).strip() != "duplicate_object":
                continue
            parameters = action.get("parameters", {})
            if isinstance(parameters, dict):
                new_name = str(parameters.get("new_name", "") or "").replace("\\_", "_").strip()
                if new_name and new_name not in existing_names:
                    existing_names.append(new_name)
        missing_names = [name for name in expected_names if name not in existing_names]
        target_scale = _blender_scale((normalized_item or {}).get("scale", [1.0, 1.0, 1.0]))
        if not any(
            isinstance(action, dict)
            and str(action.get("action_type", "")).strip() == "set_object_scale"
            and isinstance(action.get("parameters"), dict)
            and str(action["parameters"].get("name", "")).replace("\\_", "_").strip() == source_name
            for action in actions
        ):
            insert_at = next(
                (index for index, action in enumerate(actions) if isinstance(action, dict) and str(action.get("action_type", "")).strip() == "duplicate_object"),
                len(actions),
            )
            actions.insert(
                insert_at,
                {
                    "action_type": "set_object_scale",
                    "parameters": {"name": source_name, "scale": list(target_scale)},
                    "reason": "Python normalized target bbox scale before instancing",
                },
            )
        if missing_names:
            insert_at = next(
                (index for index, action in enumerate(actions) if isinstance(action, dict) and str(action.get("action_type", "")).strip() == "delete_object"),
                len(actions),
            )
            generated = [
                {
                    "action_type": "duplicate_object",
                    "parameters": {"name": source_name, "new_name": name},
                    "reason": "Python normalized missing instance count",
                }
                for name in missing_names
            ]
            actions[insert_at:insert_at] = generated
        source_is_final_instance = source_name in expected_names
        has_duplicate_from_source = any(
            isinstance(action, dict)
            and str(action.get("action_type", "")).strip() == "duplicate_object"
            and isinstance(action.get("parameters"), dict)
            and str(action["parameters"].get("name", "")).replace("\\_", "_").strip() == source_name
            for action in actions
        )
        has_delete_source = any(
            isinstance(action, dict)
            and str(action.get("action_type", "")).strip() == "delete_object"
            and isinstance(action.get("parameters"), dict)
            and str(action["parameters"].get("name", "")).replace("\\_", "_").strip() == source_name
            for action in actions
        )
        if source_name and not source_is_final_instance and has_duplicate_from_source and not has_delete_source:
            actions.append(
                {
                    "action_type": "delete_object",
                    "parameters": {"name": source_name},
                    "reason": "Python normalized removal of temporary source object",
                }
            )
        part["actions"] = actions
        part["instance_names"] = expected_names


def _source_name_from_actions(actions: list[dict[str, Any]]) -> str:
    for action in actions:
        if not isinstance(action, dict) or str(action.get("action_type", "")).strip() != "create_primitive":
            continue
        parameters = action.get("parameters", {})
        if isinstance(parameters, dict):
            name = str(parameters.get("name", "") or "").strip()
            if name:
                return name
    return ""


def _blender_scale(value: Any) -> list[float]:
    raw = list(value or [1.0, 1.0, 1.0])
    padded = [float(item) for item in raw[:3]] + [1.0] * max(0, 3 - len(raw))
    return [round(axis * SCALE_NORMALIZATION, 4) for axis in padded[:3]]


def _should_use_python_intent_fallback(raw_intent: str, exc: Exception) -> bool:
    text = str(raw_intent or "")
    if "## Intent" in text or "## Operation" in text:
        return False
    return "(missing)" in str(exc)
