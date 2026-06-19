"""BuilderExecutionPhase places built parts into the final model."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from ai_3d_modeling_agent.memory.session_paths import (
    ensure_session_runtime_dir,
    session_assembly_execution_plan_path,
)
from ai_3d_modeling_agent.multi_expert.artifacts import (
    AssemblyArtifact,
    BuildArtifact,
    PlanArtifact,
    SpecArtifact,
)
from ai_3d_modeling_agent.multi_expert.core.convener import ProcessConvener
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.action_plan import (
    ASSEMBLY_ACTIONS,
    BUILD_ACTIONS,
    AgentActionPlan,
    fallback_json_payload,
    parse_agent_action_plan,
)
from ai_3d_modeling_agent.multi_expert.core.builder_intent import BuilderIntent, parse_builder_intent
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import append_build_log, build_builder_todos_from_plan, write_todo_markdown
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.planning import normalize_assembly_execution_plan, validate_plan_structure
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.multi_expert.core.tool_logging import append_session_tool_call, format_tool_calls_markdown

logger = logging.getLogger(__name__)


class BuilderExecutionPhase(Phase):
    """Execute Builder placement todos for the final 3D model.

    The public phase wire name remains ``assemble`` for UI/progress
    compatibility, but ownership now belongs to the single Builder role.
    """

    def __init__(self) -> None:
        super().__init__(
            name="assemble",
            goal="Execute Builder placement todos",
            participants=[],
            convener=ProcessConvener(participants=[]),
            termination=TerminationPolicy(max_rounds=1, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=AssemblyArtifact,
        )

    def run(
        self,
        build_artifacts: list[BuildArtifact],
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact | None = None,
        context: Any = None,
        object_ops: Any = None,
        executor: Any = None,
        llm: Any = None,
        event_emitter: Callable | None = None,
    ) -> list[AssemblyArtifact]:
        """Place each built part according to the execution plan."""
        from ai_3d_modeling_agent.schemas.actions import Action

        _emit = event_emitter or self._emit_event
        structural_issues = validate_plan_structure(plan_artifact, spec_artifact)
        if structural_issues:
            return self._fail_fast_on_invalid_plan(
                build_artifacts=build_artifacts,
                plan_artifact=plan_artifact,
                spec_artifact=spec_artifact,
                issues=structural_issues,
                emit=_emit,
            )
        execution_plan = normalize_assembly_execution_plan(plan_artifact, spec_artifact)
        self._persist_execution_plan(context, execution_plan.to_dict())

        if _emit:
            _emit(
                "assemble",
                "phase_open",
                f"Assemble {len(execution_plan.items)} planned placements.",
                role="builder",
                speaker="Builder",
                round=0,
                summary=f"Assemble {len(execution_plan.items)} planned placements.",
                full_content=f"Assemble {len(execution_plan.items)} planned placements.",
            )

        if llm is not None:
            return self._run_builder_place_todo_intents(
                build_artifacts=build_artifacts,
                plan_artifact=plan_artifact,
                spec_artifact=spec_artifact,
                normalized_plan=execution_plan.to_dict(),
                context=context,
                object_ops=object_ops,
                executor=executor,
                llm=llm,
                emit=_emit,
            )

        results: list[AssemblyArtifact] = []
        build_by_name: dict[str, BuildArtifact] = {artifact.part_name: artifact for artifact in build_artifacts}

        for item in execution_plan.items:
            build_artifact = build_by_name.get(item.family)
            instance_names = build_artifact.instance_names if build_artifact else []
            placements: list[dict[str, Any]] = []
            action_history: list[dict[str, Any]] = []
            tool_calls: list[dict[str, Any]] = []
            planning_warnings = list(item.planning_warnings)
            planning_failures: list[str] = []
            failure_notes: list[str] = []
            skipped = bool(item.unresolved_planning_gap)

            if build_artifact is None or build_artifact.status != "built":
                failure_notes.append(f"Build output for {item.family} is unavailable for assembly.")
            parent_name = item.resolved_parent or item.parent_name
            if parent_name:
                parent_build = build_by_name.get(parent_name)
                if parent_build is None or parent_build.status != "built" or not parent_build.instance_names:
                    failure_notes.append(f"Ordering constraint violated: parent {parent_name} is not ready before assembling {item.family}.")
            if item.unresolved_planning_gap:
                planning_failures.append(
                    f"Unresolved planning gap for {item.family}: missing contract fields {', '.join(item.missing_contract_fields)}."
                )

            try:
                if failure_notes or planning_failures:
                    raise RuntimeError("; ".join(failure_notes))

                if object_ops is not None and executor is not None:
                    for instance_name in instance_names:
                        object_ops.set_object_hidden(instance_name, False)
                        show_action = {
                            "action_type": "show_object",
                            "parameters": {"name": instance_name},
                        }
                        action_history.append(show_action)
                        tool_calls.append(
                            append_session_tool_call(
                                context,
                                tool_name="show_object",
                                arguments={"name": instance_name},
                                result={"part_family": item.family},
                            )
                        )
                        executor.execute(
                            Action(
                                action_type="move_object",
                                parameters={
                                    "name": instance_name,
                                    "location": list(item.resolved_world_position or item.world_position),
                                },
                                reason=f"Position {item.family} at world position",
                            )
                        )
                        move_action = {
                            "action_type": "move_object",
                            "parameters": {
                                "name": instance_name,
                                "location": list(item.resolved_world_position or item.world_position),
                            },
                        }
                        action_history.append(move_action)
                        tool_calls.append(
                            append_session_tool_call(
                                context,
                                tool_name="move_object",
                                arguments=move_action["parameters"],
                                result={"part_family": item.family},
                            )
                        )
                        if any(rotation != 0.0 for rotation in item.world_rotation):
                            executor.execute(
                                Action(
                                    action_type="rotate_object",
                                    parameters={
                                        "name": instance_name,
                                        "rotation_degrees": list(item.world_rotation),
                                    },
                                    reason=f"Rotate {item.family}",
                                )
                            )
                            rotate_action = {
                                "action_type": "rotate_object",
                                "parameters": {
                                    "name": instance_name,
                                    "rotation_degrees": list(item.world_rotation),
                                },
                            }
                            action_history.append(rotate_action)
                            tool_calls.append(
                                append_session_tool_call(
                                    context,
                                    tool_name="rotate_object",
                                    arguments=rotate_action["parameters"],
                                    result={"part_family": item.family},
                                )
                            )
                        if parent_name:
                            parent_instance = build_by_name[parent_name].instance_names[0]
                            object_ops.set_parent(instance_name, parent_instance)
                            parent_action = {
                                "action_type": "set_parent",
                                "parameters": {"child_name": instance_name, "parent_name": parent_instance},
                            }
                            action_history.append(parent_action)
                            tool_calls.append(
                                append_session_tool_call(
                                    context,
                                    tool_name="set_parent",
                                    arguments=parent_action["parameters"],
                                    result={"part_family": item.family},
                                )
                            )

                    placements.append(
                        {
                            "part": item.family,
                            "parent": parent_name,
                            "world_position": list(item.resolved_world_position or item.world_position),
                            "world_rotation": list(item.world_rotation),
                            "instances": list(instance_names),
                        }
                    )
                else:
                    placements.append(
                        {
                            "part": item.family,
                            "parent": parent_name,
                            "world_position": list(item.resolved_world_position or item.world_position),
                            "world_rotation": list(item.world_rotation),
                        }
                    )

                artifact = AssemblyArtifact(
                    step_index=item.step_index,
                    placements=placements,
                    responsibility_refs=list(item.responsibility_refs),
                    constraint_refs=list(item.constraint_refs),
                    planning_warnings=planning_warnings,
                    planning_failures=planning_failures,
                    resolved_parent=None if skipped else parent_name,
                    resolved_world_position=None if skipped else list(item.resolved_world_position or item.world_position),
                    skipped=skipped,
                    unresolved_planning_gap=item.unresolved_planning_gap,
                    missing_contract_fields=list(item.missing_contract_fields),
                    fallback_used=item.used_step_fallback,
                    action_history=action_history,
                    review_verdict="approved",
                )
            except Exception as exc:
                logger.exception("Assembly failed for step '%s'", item.family)
                artifact = AssemblyArtifact(
                    step_index=item.step_index,
                    placements=placements,
                    responsibility_refs=list(item.responsibility_refs),
                    constraint_refs=list(item.constraint_refs),
                    planning_warnings=planning_warnings,
                    planning_failures=planning_failures,
                    resolved_parent=None if skipped else parent_name,
                    resolved_world_position=None if skipped else (
                        list(item.resolved_world_position or item.world_position)
                        if (item.resolved_world_position or item.world_position)
                        else None
                    ),
                    skipped=skipped,
                    unresolved_planning_gap=item.unresolved_planning_gap,
                    missing_contract_fields=list(item.missing_contract_fields),
                    fallback_used=item.used_step_fallback,
                    action_history=action_history,
                    review_verdict="failed",
                    failure_notes=failure_notes or planning_failures or [str(exc)],
                )

            results.append(artifact)
            append_build_log(
                context,
                title=f"Place {item.family}",
                body=f"Status: {artifact.review_verdict}\nPlacements: {artifact.placements}",
                validation={"status": artifact.review_verdict, "placements": list(artifact.placements)},
            )

            if _emit:
                resolved_position = item.resolved_world_position or item.world_position
                position_text = str([round(coord, 3) for coord in resolved_position])
                parent_suffix = f" with parent={parent_name}" if parent_name else ""
                if artifact.skipped:
                    missing_fields = ", ".join(item.missing_contract_fields) or "unknown contract fields"
                    summary = f"Skipped assembly for {item.family} due to unresolved contract fields."
                    full_content = (
                        f"{summary}\n\n"
                        f"Missing contract fields: {missing_fields}\n"
                        f"Planning gap: true"
                    )
                elif artifact.review_verdict == "failed":
                    summary = f"Failed assembly for {item.family}."
                    full_content = "\n".join(artifact.failure_notes or [summary])
                else:
                    summary = f"Assemble {item.family} at {position_text}{parent_suffix}."
                    full_content = format_tool_calls_markdown(tool_calls) or summary
                _emit(
                    "assemble",
                    "assemble_step",
                    summary,
                    role="builder",
                    speaker="Builder",
                    round=item.step_index + 1,
                    summary=summary,
                    full_content=full_content,
                    missing_contract_fields=list(item.missing_contract_fields),
                    clarification_scope="assembly_contract" if item.resolved_from_clarification or item.unresolved_planning_gap else "",
                    target_family=item.family,
                    skipped=artifact.skipped,
                    unresolved_planning_gap=item.unresolved_planning_gap,
                    tool_calls=tool_calls,
                )

        if _emit:
            _emit(
                "assemble",
                "phase_close",
                f"Completed assembly planning for {len(results)} steps.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Completed assembly planning for {len(results)} steps.",
                full_content=f"Completed assembly planning for {len(results)} steps.",
            )

        return results

    def _run_builder_place_todo_intents(
        self,
        *,
        build_artifacts: list[BuildArtifact],
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact | None,
        normalized_plan: dict[str, Any],
        context: Any,
        object_ops: Any,
        executor: Any,
        llm: Any,
        emit: Callable | None,
    ) -> list[AssemblyArtifact]:
        """Ask Builder for one Markdown intent per placement todo, then execute in Python."""
        if object_ops is None or executor is None:
            return [
                AssemblyArtifact(
                    step_index=0,
                    review_verdict="blocked",
                    failure_notes=["Builder placement intent execution requires object_ops and executor."],
                )
            ]

        todos = build_builder_todos_from_plan(plan_artifact)
        build_by_name = {artifact.part_name: artifact for artifact in build_artifacts}
        for todo in todos:
            if str(todo.get("id", "")).startswith("build:"):
                family = str(todo.get("id", "")).split(":", 1)[1]
                if build_by_name.get(family) and build_by_name[family].status == "built":
                    todo["status"] = "done"
        item_by_family = {
            str(item.get("family", "")).strip(): item
            for item in list(normalized_plan.get("items", []) or [])
            if str(item.get("family", "")).strip()
        }
        place_todos = [todo for todo in todos if str(todo.get("id", "")).startswith("place:")]
        results: list[AssemblyArtifact] = []
        for index, todo in enumerate(place_todos, start=1):
            todo_id = str(todo.get("id", "")).strip()
            family = todo_id.split(":", 1)[1] if ":" in todo_id else str(todo.get("target", "")).strip()
            item = item_by_family.get(family, {})
            write_todo_markdown(context, todos=todos, current_todo=todo_id)
            raw_intent = self._request_builder_place_intent(
                llm=llm,
                context=context,
                todo=todo,
                family=family,
                normalized_item=item,
                build_artifact=build_by_name.get(family),
            )
            fallback_warning = ""
            try:
                try:
                    parse_builder_intent(raw_intent, expected_intent="place")
                except ValueError as parse_exc:
                    if not _should_use_python_intent_fallback(raw_intent, parse_exc):
                        raise
                    intent = self._fallback_place_intent(family, item, build_by_name.get(family))
                    fallback_warning = (
                        "Builder returned malformed Markdown placement intent; "
                        f"used Python normalized assembly plan fallback: {parse_exc}"
                    )
                    artifact, tool_calls = self._execute_place_intent(
                        intent=intent,
                        family=family,
                        item=item,
                        build_by_name=build_by_name,
                        context=context,
                        object_ops=object_ops,
                        executor=executor,
                        step_index=index - 1,
                    )
                else:
                    raw_action_json, action_plan = self._extract_assembly_action_plan_from_markdown(
                        llm=llm,
                        context=context,
                        todo=todo,
                        family=family,
                        normalized_item=item,
                        build_artifact=build_by_name.get(family),
                        builder_markdown=raw_intent,
                        step_index=index - 1,
                    )
                    artifacts, tool_calls = self._execute_assembly_action_plan(
                        action_plan=action_plan,
                        family=family,
                        item=item,
                        build_by_name=build_by_name,
                        context=context,
                        object_ops=object_ops,
                        executor=executor,
                        step_index=index - 1,
                    )
                    artifact = artifacts[0] if artifacts else AssemblyArtifact(step_index=index - 1, review_verdict="failed", failure_notes=["No assembly artifact was produced from extracted action JSON."])
                    if raw_action_json:
                        artifact.action_history.append({"extracted_action_json": raw_action_json})
                if fallback_warning:
                    artifact.planning_warnings.append(fallback_warning)
                todo["status"] = "done" if artifact.review_verdict == "approved" else "blocked"
            except Exception as exc:
                logger.exception("Builder placement Markdown intent failed for '%s'", family)
                artifact = AssemblyArtifact(
                    step_index=index - 1,
                    review_verdict="failed",
                    failure_notes=[str(exc)],
                    action_history=[{"raw_builder_intent": raw_intent}],
                )
                tool_calls = []
                todo["status"] = "blocked"
            results.append(artifact)
            validation = {
                "todo_id": todo_id,
                "status": artifact.review_verdict,
                "placements": list(artifact.placements),
                "failure_notes": list(artifact.failure_notes),
            }
            append_build_log(
                context,
                title=f"Builder todo {todo_id}",
                body=(
                    f"Builder operation:\n\n{raw_intent}\n\n"
                    + (f"Python fallback:\n\n{fallback_warning}\n\n" if fallback_warning else "")
                    + f"Result: {artifact.review_verdict}"
                ),
                validation=validation,
            )
            write_todo_markdown(context, todos=todos, current_todo="")
            if emit:
                summary = f"Builder completed {todo_id}" if artifact.review_verdict == "approved" else f"Builder failed {todo_id}"
                emit(
                    "assemble",
                    "assemble_step",
                    summary,
                    role="builder",
                    speaker="Builder",
                    round=index,
                    summary=summary,
                    full_content=format_tool_calls_markdown(tool_calls) or raw_intent,
                    tool_calls=tool_calls,
                    current_todo=todo_id,
                    validation=validation,
                    target_family=family,
                    skipped=artifact.skipped,
                    unresolved_planning_gap=artifact.unresolved_planning_gap,
                )
        if emit:
            emit(
                "assemble",
                "phase_close",
                f"Completed Builder todo execution for {len(results)} placement todos.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Completed Builder todo execution for {len(results)} placement todos.",
                full_content=f"Completed Builder todo execution for {len(results)} placement todos.",
            )
        return results

    def _request_builder_place_intent(
        self,
        *,
        llm: Any,
        context: Any,
        todo: dict[str, Any],
        family: str,
        normalized_item: dict[str, Any],
        build_artifact: BuildArtifact | None,
    ) -> str:
        prompt = {
            "task": (
                "Produce exactly one executable Builder Markdown placement operation for the current todo. "
                "You may read docs/blender_build_capabilities.md before answering. "
                "The final answer must start with '## Operation' and must not include tool-call narration, "
                "delegation narration, code fences, JSON, or self-correction text. "
                "If Task Tool delegation is unavailable, write the intent directly from normalized_assembly_item."
            ),
            "ao_route": "moderator",
            "delegation_required": True,
            "delegated_agent": "builder",
            "strict_final_answer_contract": [
                "First non-whitespace characters must be: ## Operation",
                "Required sections: ## Operation, ## Target, ## Parameters, ## Validation",
                "Operation may be a short natural-language place/move statement.",
                "No preface, no explanation, no code fence, no Task Tool transcript",
            ],
            "current_todo": todo,
            "target_family": family,
            "available_instances": list(build_artifact.instance_names) if build_artifact else [],
            "normalized_assembly_item": normalized_item,
            "required_markdown_shape": {
                "Operation": "Natural-language one-step place/move operation using documented Blender tools",
                "Target": family,
                "Parameters": [
                    "instances: <comma-separated built instance names>",
                    "location: [x, y, z]",
                    "instance_locations: <optional per-instance [x, y, z] list from normalized_assembly_item>",
                    "rotation_degrees: [x, y, z]",
                    "parent: <optional parent family or object>",
                ],
                "Validation": "object location and parent will be checked by Python",
            },
            "rules": [
                "Handle only current_todo.",
                "Use docs/blender_build_capabilities.md as the tool reference when you need available function names or parameters.",
                "Do not create geometry.",
                "Do not return JSON.",
                "Do not call Blender or MCP yourself.",
                "Use the normalized assembly item; do not invent new coordinates or parents.",
                "If normalized_assembly_item has instance_world_positions, preserve those per-instance positions.",
                "If using a subagent fails, still return the Markdown operation from normalized_assembly_item.",
            ],
        }
        return str(
            llm.call(
                system_prompt="",
                messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)}],
                agent="moderator",
                label=f"assemble.todo.{family}",
                skill="",
                context={
                    **(context or {}),
                    "phase_name": "assemble",
                    "agent_role": "builder",
                    "delegated_agent": "builder",
                    "meeting_turn_kind": "builder_place_todo",
                    "current_todo": str(todo.get("id", "")),
                }
                if isinstance(context, dict)
                else {
                    "phase_name": "assemble",
                    "agent_role": "builder",
                    "delegated_agent": "builder",
                    "meeting_turn_kind": "builder_place_todo",
                    "current_todo": str(todo.get("id", "")),
                },
            )
        )

    def _fallback_place_intent(
        self,
        family: str,
        normalized_item: dict[str, Any],
        build_artifact: BuildArtifact | None,
    ) -> BuilderIntent:
        if not normalized_item:
            raise ValueError(f"Cannot fallback placement intent for {family!r}; normalized assembly item is missing.")
        return BuilderIntent(
            intent="place",
            target=family,
            parameters={
                "instances": list(build_artifact.instance_names) if build_artifact else [],
                "location": normalized_item.get("world_position", [0.0, 0.0, 0.0]),
                "instance_locations": normalized_item.get("instance_world_positions", []),
                "rotation_degrees": normalized_item.get("world_rotation", [0.0, 0.0, 0.0]),
                "parent": normalized_item.get("parent_name"),
            },
            validation="Python normalized assembly plan fallback.",
            raw_markdown="",
        )

    def _extract_assembly_action_plan_from_markdown(
        self,
        *,
        llm: Any,
        context: Any,
        todo: dict[str, Any],
        family: str,
        normalized_item: dict[str, Any],
        build_artifact: BuildArtifact | None,
        builder_markdown: str,
        step_index: int,
    ) -> tuple[str, AgentActionPlan]:
        prompt = {
            "task": "Extract Python-executable Blender placement action JSON from the completed Builder Markdown operation.",
            "source_documents": {
                "builder_markdown": builder_markdown,
                "capability_references": [
                    "docs/blender_assembly_capabilities.md",
                    "docs/blender_build_capabilities.md",
                ],
            },
            "current_todo": todo,
            "target_family": family,
            "available_instances": list(build_artifact.instance_names) if build_artifact else [],
            "normalized_assembly_item": normalized_item,
            "required_ready_shape": {
                "status": "ready",
                "steps": [
                    {
                        "step_index": step_index,
                        "placements": [
                            {
                                "part": family,
                                "instances": list(build_artifact.instance_names) if build_artifact else [],
                            }
                        ],
                        "actions": [
                            {"action_type": "show_object", "parameters": {"name": f"{family}_01"}},
                            {"action_type": "move_object", "parameters": {"name": f"{family}_01", "location": [0.0, 0.0, 0.0]}},
                        ],
                    }
                ],
            },
            "rules": [
                "Do not modify the Builder Markdown.",
                "Extract JSON only from Builder Markdown, normalized_assembly_item, build_artifact, and capability references.",
                "Use only action types and parameter names from the capability docs.",
                "If required placement values are missing from Markdown but present in normalized_assembly_item, use normalized_assembly_item.",
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
                label="assemble.markdown_to_actions" if attempt == 0 else "assemble.markdown_to_actions.repair",
                skill="blender-assembly-actions",
                context={**(context or {}), "phase_name": "assemble", "agent_role": "builder", "delegated_agent": "builder", "meeting_turn_kind": "builder_placement_extraction"} if isinstance(context, dict) else {"phase_name": "assemble", "agent_role": "builder", "delegated_agent": "builder", "meeting_turn_kind": "builder_placement_extraction"},
            )
            try:
                parsed = parse_agent_action_plan(raw, allowed_actions=ASSEMBLY_ACTIONS | BUILD_ACTIONS, context_label="Assembly Markdown extraction")
                if parsed.status == "ready" and not parsed.steps:
                    raise ValueError("Assembly Markdown extraction is ready but contains no steps")
                if parsed.status != "ready":
                    reason = parsed.reason or parsed.issue or "Builder placement Markdown extraction is not executable."
                    return raw, AgentActionPlan(status=parsed.status, reason=reason, missing_capability=parsed.missing_capability, issue=parsed.issue, route_to=parsed.route_to, requested_clarification=parsed.requested_clarification)
                _normalize_extracted_assembly_steps(parsed, family, normalized_item, build_artifact)
                return raw, parsed
            except Exception as exc:
                last_raw = raw
                last_error = str(exc)
                messages = [
                    {
                        "role": "user",
                        "content": fallback_json_payload(
                            {
                                "task": "Repair the previous placement Markdown-to-JSON extraction. Do not change the Builder Markdown; extract valid JSON only.",
                                "format_or_validation_error": last_error,
                                "previous_response_preview": last_raw[:1600],
                                "builder_markdown": builder_markdown,
                                "current_todo": todo,
                                "target_family": family,
                                "available_instances": list(build_artifact.instance_names) if build_artifact else [],
                                "normalized_assembly_item": normalized_item,
                                "required_ready_shape": prompt["required_ready_shape"],
                            }
                        ),
                    }
                ]
        raise ValueError(f"Builder placement Markdown action extraction failed: {last_error}")

    def _execute_assembly_action_plan(
        self,
        *,
        action_plan: AgentActionPlan,
        family: str,
        item: dict[str, Any],
        build_by_name: dict[str, BuildArtifact],
        context: Any,
        object_ops: Any,
        executor: Any,
        step_index: int,
    ) -> tuple[list[AssemblyArtifact], list[dict[str, Any]]]:
        from ai_3d_modeling_agent.schemas.actions import Action

        if action_plan.status != "ready":
            reason = action_plan.reason or action_plan.issue or "Builder placement Markdown extraction is not executable."
            return [AssemblyArtifact(step_index=step_index, review_verdict="failed", failure_notes=[reason])], []

        build_artifact = build_by_name.get(family)
        if build_artifact is None or build_artifact.status != "built" or not build_artifact.instance_names:
            raise RuntimeError(f"Build output for {family} is unavailable for placement.")

        position = _float_vector(item.get("resolved_world_position") or item.get("world_position") or [0.0, 0.0, 0.0])
        expected_positions = _instance_positions_for_item(
            item.get("instance_world_positions"),
            len(build_artifact.instance_names),
            position,
        )
        rotation = _float_vector(item.get("world_rotation") or [0.0, 0.0, 0.0])
        parent_family = str(item.get("resolved_parent") or item.get("parent_name") or "").strip()
        parent_instance = ""
        if parent_family:
            parent_build = build_by_name.get(parent_family)
            if parent_build is None or parent_build.status != "built" or not parent_build.instance_names:
                raise RuntimeError(f"Parent build output for {parent_family} is unavailable for placement.")
            parent_instance = parent_build.instance_names[0]

        action_history: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        failure_notes: list[str] = []
        try:
            for step in action_plan.steps:
                for action_payload in list(step.get("actions", []) or []):
                    action = Action(
                        action_type=str(action_payload.get("action_type", "")),
                        parameters=dict(action_payload.get("parameters", {}) or {}),
                        reason=str(action_payload.get("reason", "Builder placement Markdown extraction")),
                    )
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
            for instance_name, expected_position in zip(build_artifact.instance_names, expected_positions):
                actual_location = _float_vector(object_ops.get_object_location(instance_name))
                if actual_location != expected_position:
                    raise RuntimeError(f"Placement validation failed for {instance_name}: expected {expected_position}, got {actual_location}")
                if parent_instance and object_ops.get_object_parent(instance_name) != parent_instance:
                    raise RuntimeError(f"Placement validation failed for {instance_name}: parent was not set to {parent_instance}")
        except Exception as exc:
            logger.exception("Extracted Builder placement action JSON failed for '%s'", family)
            failure_notes.append(str(exc))

        placements = [
            {
                "part": family,
                "parent": parent_family or None,
                "world_position": list(expected_position),
                "world_rotation": list(rotation),
                "instances": [instance_name],
            }
            for instance_name, expected_position in zip(build_artifact.instance_names, expected_positions)
        ]
        if not failure_notes:
            tool_calls.append(
                append_session_tool_call(
                    context,
                    tool_name="scene_validation",
                    arguments={"instances": list(build_artifact.instance_names), "expected_locations": expected_positions, "expected_parent": parent_instance},
                    result={"passed": True},
                )
            )
        return [
            AssemblyArtifact(
                step_index=step_index,
                placements=placements if not failure_notes else [],
                resolved_parent=parent_family or None,
                resolved_world_position=list(position),
                action_history=action_history,
                review_verdict="failed" if failure_notes else "approved",
                failure_notes=failure_notes,
            )
        ], tool_calls

    def _execute_place_intent(
        self,
        *,
        intent: BuilderIntent,
        family: str,
        item: dict[str, Any],
        build_by_name: dict[str, BuildArtifact],
        context: Any,
        object_ops: Any,
        executor: Any,
        step_index: int,
    ) -> tuple[AssemblyArtifact, list[dict[str, Any]]]:
        from ai_3d_modeling_agent.schemas.actions import Action

        if intent.intent != "place":
            raise ValueError(f"Placement todo requires place intent, got {intent.intent}")
        target = intent.target.strip()
        if family and target and target.lower() not in {family.lower(), f"place:{family}".lower()}:
            raise ValueError(f"Builder target {target!r} does not match current family {family!r}")
        build_artifact = build_by_name.get(family)
        if build_artifact is None or build_artifact.status != "built" or not build_artifact.instance_names:
            raise RuntimeError(f"Build output for {family} is unavailable for placement.")
        position = _float_vector(item.get("resolved_world_position") or item.get("world_position") or intent.parameters.get("location") or [0.0, 0.0, 0.0])
        instance_positions = _instance_positions_for_item(
            item.get("instance_world_positions") or intent.parameters.get("instance_locations"),
            len(build_artifact.instance_names),
            position,
        )
        rotation = _float_vector(item.get("world_rotation") or intent.parameters.get("rotation_degrees") or [0.0, 0.0, 0.0])
        parent_family = str(item.get("resolved_parent") or item.get("parent_name") or "").strip()
        parent_instance = ""
        if parent_family:
            parent_build = build_by_name.get(parent_family)
            if parent_build is None or parent_build.status != "built" or not parent_build.instance_names:
                raise RuntimeError(f"Parent build output for {parent_family} is unavailable for placement.")
            parent_instance = parent_build.instance_names[0]

        action_history: list[dict[str, Any]] = []
        tool_calls: list[dict[str, Any]] = []
        placements: list[dict[str, Any]] = []
        for instance_name, instance_position in zip(build_artifact.instance_names, instance_positions):
            actions = [
                Action("show_object", {"name": instance_name}, reason="Builder place intent"),
                Action("move_object", {"name": instance_name, "location": instance_position}, reason="Builder place intent"),
            ]
            if any(float(value or 0.0) != 0.0 for value in rotation):
                actions.append(Action("rotate_object", {"name": instance_name, "rotation_degrees": rotation}, reason="Builder place intent"))
            if parent_instance:
                actions.append(Action("set_parent", {"child_name": instance_name, "parent_name": parent_instance}, reason="Builder place intent"))
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
            actual_location = _float_vector(object_ops.get_object_location(instance_name))
            if actual_location != instance_position:
                raise RuntimeError(f"Placement validation failed for {instance_name}: expected {instance_position}, got {actual_location}")
            if parent_instance and object_ops.get_object_parent(instance_name) != parent_instance:
                raise RuntimeError(f"Placement validation failed for {instance_name}: parent was not set to {parent_instance}")
            placements.append(
                {
                    "part": family,
                    "parent": parent_family or None,
                    "world_position": list(instance_position),
                    "world_rotation": list(rotation),
                    "instances": [instance_name],
                }
            )
        tool_calls.append(
            append_session_tool_call(
                context,
                tool_name="scene_validation",
                arguments={"instances": list(build_artifact.instance_names), "expected_locations": instance_positions, "expected_parent": parent_instance},
                result={"passed": True},
            )
        )
        artifact = AssemblyArtifact(
            step_index=step_index,
            placements=placements,
            resolved_parent=parent_family or None,
            resolved_world_position=list(position),
            action_history=action_history,
            review_verdict="approved",
        )
        return artifact, tool_calls

    def _fail_fast_on_invalid_plan(
        self,
        *,
        build_artifacts: list[BuildArtifact],
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact | None,
        issues: list[dict[str, Any]],
        emit: Callable | None,
    ) -> list[AssemblyArtifact]:
        summaries = [str(issue.get("summary", "")).strip() for issue in issues if str(issue.get("summary", "")).strip()]
        families = self._ordered_assembly_families(build_artifacts, plan_artifact, spec_artifact)
        if emit:
            emit(
                "assemble",
                "phase_open",
                f"Assembly aborted: planning contract is invalid for {len(families)} families.",
                role="builder",
                speaker="Builder",
                round=0,
                summary=f"Assembly aborted: planning contract is invalid for {len(families)} families.",
                full_content="\n".join(summaries) or "Planning contract is invalid.",
            )
        results: list[AssemblyArtifact] = []
        for index, family in enumerate(families, start=1):
            relevant = [summary for summary in summaries if family in summary] or summaries
            artifact = AssemblyArtifact(
                step_index=index - 1,
                placements=[],
                planning_failures=list(relevant),
                skipped=True,
                unresolved_planning_gap=True,
                review_verdict="failed",
                failure_notes=list(relevant),
            )
            results.append(artifact)
            if emit:
                emit(
                    "assemble",
                    "assemble_step",
                    f"Skipped assembly for {family} due to invalid planning contract.",
                    role="builder",
                    speaker="Builder",
                    round=index,
                    summary=f"Skipped assembly for {family} due to invalid planning contract.",
                    full_content="\n".join(relevant) or f"Skipped assembly for {family} due to invalid planning contract.",
                    missing_contract_fields=[],
                    clarification_scope="assembly_contract",
                    target_family=family,
                    skipped=True,
                    unresolved_planning_gap=True,
                    tool_calls=[],
                )
        if emit:
            emit(
                "assemble",
                "phase_close",
                f"Assembly stopped because the planning contract is invalid for {len(families)} families.",
                role="builder",
                speaker="Builder",
                rounds=len(results),
                round=len(results),
                summary=f"Assembly stopped because the planning contract is invalid for {len(families)} families.",
                full_content="\n".join(summaries) or "Planning contract is invalid.",
            )
        return results

    def _ordered_assembly_families(
        self,
        build_artifacts: list[BuildArtifact],
        plan_artifact: PlanArtifact,
        spec_artifact: SpecArtifact | None,
    ) -> list[str]:
        families: list[str] = []
        for artifact in build_artifacts:
            family = str(artifact.part_name).strip()
            if family and family not in families:
                families.append(family)
        for step in plan_artifact.steps:
            family = str(step.get("family", "")).strip()
            if family and family not in families:
                families.append(family)
        for item in plan_artifact.assembly_responsibilities:
            if not isinstance(item, dict):
                continue
            family = str(item.get("family", "")).strip()
            if family and family not in families:
                families.append(family)
        if isinstance(spec_artifact, SpecArtifact) and isinstance(spec_artifact.parts, dict):
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
        path = session_assembly_execution_plan_path(runtime_root, session_id)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)


def _float_vector(value: Any) -> list[float]:
    raw = list(value or [0.0, 0.0, 0.0])
    padded = [float(item) for item in raw[:3]] + [0.0] * max(0, 3 - len(raw))
    return [round(item, 4) for item in padded[:3]]


def _instance_positions_for_item(value: Any, count: int, default_position: list[float]) -> list[list[float]]:
    if isinstance(value, list) and value and all(isinstance(item, list) for item in value):
        positions = [_float_vector(item) for item in value]
        if len(positions) >= count:
            return positions[:count]
    return [list(default_position) for _ in range(max(0, count))]


def _normalize_extracted_assembly_steps(
    action_plan: AgentActionPlan,
    family: str,
    normalized_item: dict[str, Any],
    build_artifact: BuildArtifact | None,
) -> None:
    if build_artifact is None or not build_artifact.instance_names:
        return
    position = _float_vector((normalized_item or {}).get("resolved_world_position") or (normalized_item or {}).get("world_position") or [0.0, 0.0, 0.0])
    positions = _instance_positions_for_item(
        (normalized_item or {}).get("instance_world_positions"),
        len(build_artifact.instance_names),
        position,
    )
    rotation = _float_vector((normalized_item or {}).get("world_rotation") or [0.0, 0.0, 0.0])
    parent = str((normalized_item or {}).get("resolved_parent") or (normalized_item or {}).get("parent_name") or "").strip()
    actions: list[dict[str, Any]] = []
    for instance_name, instance_position in zip(build_artifact.instance_names, positions):
        actions.append({"action_type": "show_object", "parameters": {"name": instance_name}})
        actions.append({"action_type": "move_object", "parameters": {"name": instance_name, "location": list(instance_position)}})
        if any(float(value or 0.0) != 0.0 for value in rotation):
            actions.append({"action_type": "rotate_object", "parameters": {"name": instance_name, "rotation_degrees": list(rotation)}})
        if parent:
            actions.append({"action_type": "set_parent", "parameters": {"child_name": instance_name, "parent_name": parent}})
    action_plan.steps = [
        {
            "step_index": int((normalized_item or {}).get("step_index", 0) or 0),
            "target_family": family,
            "placements": [
                {"part": family, "instances": [name], "world_position": list(pos), "world_rotation": list(rotation)}
                for name, pos in zip(build_artifact.instance_names, positions)
            ],
            "actions": actions,
        }
    ]


def _should_use_python_intent_fallback(raw_intent: str, exc: Exception) -> bool:
    text = str(raw_intent or "")
    if "## Intent" in text or "## Operation" in text:
        return False
    return "(missing)" in str(exc)


class AssemblePhase(BuilderExecutionPhase):
    """Backward-compatible name for the Builder placement execution phase."""
