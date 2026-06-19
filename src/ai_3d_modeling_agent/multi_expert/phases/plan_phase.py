"""Planning phase with moderated meeting plus deterministic plan computation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ai_3d_modeling_agent.multi_expert.artifacts import PlanArtifact, SpecArtifact
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation, Message
from ai_3d_modeling_agent.multi_expert.core.coverage import (
    build_plan_todos_from_spec,
    build_todo_groups,
    coverage_clarification_requests,
    coverage_open_issues,
    coverage_revision_requests,
    coverage_quality_flags,
    coverage_summary,
    mark_todo_group_status,
    mark_plan_coverage,
    sync_todo_group_status_with_coverage,
)
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import write_plan_markdown
from ai_3d_modeling_agent.multi_expert.core.meeting import (
    DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
    OpenIssue,
    apply_resolution_to_state,
    create_phase_meeting_state,
    create_seed_message,
    emit_meeting_event,
    generate_resolution,
    meeting_state_to_dict,
    recent_conversation_excerpt,
    run_moderated_phase,
    summarize_turn_text,
    update_state_after_challenge,
)
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.planning import validate_assembly_contract
from ai_3d_modeling_agent.multi_expert.core.planning import validate_plan_structure
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.memory.session_paths import ensure_session_runtime_dir, session_plan_artifact_path
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry
from ai_3d_modeling_agent.pipelines.attachment_solver import solve_placement, solve_root_placement
from ai_3d_modeling_agent.pipelines.dag_scheduler import build_execution_dag
from ai_3d_modeling_agent.schemas.part import PartFamily, SymmetryGroup


class PlanPhase(Phase):
    def __init__(self) -> None:
        participants = ["planner", "reviewer"]
        super().__init__(
            name="plan",
            goal="Define execution order, assembly order, dependencies, and planning rationale.",
            participants=participants,
            convener=None,
            termination=TerminationPolicy(max_rounds=2, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=PlanArtifact,
        )

    def run(
        self,
        registry: ExpertRegistry,
        context: Any,
        llm: Any,
        spec_artifact: SpecArtifact,
        part_families: list[PartFamily],
        event_emitter: Callable | None = None,
    ) -> PlanArtifact:
        emit = event_emitter or self._emit_event
        phase_context = dict(context or {})
        allowed_families = sorted(
            {
                *(str(family.name).strip() for family in part_families if str(family.name).strip()),
            }
        )
        phase_context["allowed_families"] = allowed_families
        phase_context["spec_parts"] = spec_artifact.parts
        phase_context["part_families"] = [family.to_dict() for family in part_families]
        plan_todos = build_plan_todos_from_spec(spec_artifact, part_families)
        todo_groups = build_todo_groups(plan_todos, phase=self.name, role="planner")
        phase_context["coverage_todos"] = plan_todos
        phase_context["coverage_summary"] = coverage_summary(plan_todos)
        phase_context["todo_groups"] = todo_groups
        conversation = Conversation(phase_name=self.name, context=phase_context)
        conversation.append(
            create_seed_message(
                self.name,
                (
                    f"Specification summary:\n{spec_artifact.summary}\n\n"
                    f"Specified parts:\n{spec_artifact.parts}\n\n"
                    f"Part families:\n{[family.to_dict() for family in part_families]}\n\n"
                    "Planning goal:\nCreate a safe execution order for build and assembly."
                ),
            )
        )

        state = create_phase_meeting_state(self.name, self.goal, "planner", "reviewer")
        state.coverage_todos = plan_todos
        state.coverage_summary = coverage_summary(plan_todos)
        state.todo_groups = todo_groups
        if todo_groups:
            conversation, state = self._run_focused_todo_queue(
                conversation=conversation,
                registry=registry,
                llm=llm,
                base_context=phase_context,
                state=state,
                emit=emit,
            )
        else:
            conversation, state = run_moderated_phase(
                conversation=conversation,
                registry=registry,
                llm=llm,
                base_context=phase_context,
                state=state,
                emit=emit,
                max_rounds=self.termination.max_rounds,
                sampling_policy=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
                emit_phase_close=False,
            )
        state.coverage_todos = plan_todos
        state.coverage_summary = coverage_summary(plan_todos)

        artifact = self._compute_plan(spec_artifact, part_families)
        artifact.summary = state.last_resolution_summary or artifact.summary
        artifact.open_issues = [issue.summary for issue in state.open_issues]
        self._apply_coverage_to_state_and_artifact(state, artifact, part_families)

        draft_contract_issues = self._merge_validation_issues(
            validate_plan_structure(artifact, spec_artifact),
            validate_assembly_contract(artifact, spec_artifact),
        )
        if draft_contract_issues:
            conversation, state = self._run_contract_clarification(
                conversation=conversation,
                state=state,
                registry=registry,
                llm=llm,
                context=phase_context,
                spec_artifact=spec_artifact,
                missing_issues=draft_contract_issues,
                emit=emit,
            )
            state.missing_contract_fields = list(draft_contract_issues)
            state.clarification_attempted = True
            state.clarification_resolved = False
            artifact = self._compute_plan(spec_artifact, part_families)
            artifact.summary = state.last_resolution_summary or artifact.summary
            artifact.open_issues = [issue.summary for issue in state.open_issues]
            self._apply_coverage_to_state_and_artifact(state, artifact, part_families)

        final_contract_issues = self._merge_validation_issues(
            validate_plan_structure(artifact, spec_artifact),
            validate_assembly_contract(artifact, spec_artifact),
        )
        state.missing_contract_fields = list(final_contract_issues)
        state.clarification_resolved = bool(state.clarification_attempted and not final_contract_issues)
        if final_contract_issues:
            state.phase_quality_flags = sorted(set([*state.phase_quality_flags, "unresolved_planning_gap", "invalid_planning_structure"]))
            artifact.open_issues = self._merge_open_issues_with_contract_gaps(
                artifact.open_issues,
                final_contract_issues,
            )
            artifact.failure_notes = self._merge_failure_notes(
                artifact.failure_notes,
                [str(issue.get("summary", "")).strip() for issue in final_contract_issues if str(issue.get("summary", "")).strip()],
            )
        artifact.open_issues = self._clean_open_issues(artifact.open_issues, bool(final_contract_issues))
        artifact.summary = artifact.summary or state.last_resolution_summary
        self._persist_plan_artifact(phase_context, artifact)
        write_plan_markdown(phase_context, artifact, meeting_state=state)
        from ai_3d_modeling_agent.multi_expert.core.meeting import persist_phase_meeting_state
        if state.phase_status != "needs_revision":
            state.phase_status = "completed" if not state.open_issues else "completed_with_open_issues"
        persist_phase_meeting_state(phase_context, state)
        emit_meeting_event(
            emit,
            self.name,
            "phase_close",
            round_index=state.current_round,
            speaker="moderator",
            role="moderator",
            full_content=state.last_resolution_summary or artifact.summary,
            summary=state.last_resolution_summary or artifact.summary or "Plan meeting closed.",
            quality_flags=list(state.phase_quality_flags),
            change_summary=state.round_change_summary,
        )
        return artifact

    def _run_focused_todo_queue(
        self,
        *,
        conversation: Conversation,
        registry: ExpertRegistry,
        llm: Any,
        base_context: dict[str, Any],
        state: Any,
        emit: Callable | None,
    ) -> tuple[Conversation, Any]:
        for group in list(state.todo_groups or []):
            group_id = str(group.get("id", "")).strip()
            group_todos = list(group.get("todos", []) or [])
            if not group_id or not group_todos:
                continue
            state.current_todo_group = dict(group)
            state.coverage_todos = group_todos
            state.coverage_summary = coverage_summary(group_todos)
            base_context["current_todo_group"] = dict(group)
            base_context["coverage_todos"] = group_todos
            base_context["coverage_summary"] = state.coverage_summary
            max_round = state.current_round + 1
            before_count = len(conversation.messages)
            conversation, state = run_moderated_phase(
                conversation=conversation,
                registry=registry,
                llm=llm,
                base_context=base_context,
                state=state,
                emit=emit,
                max_rounds=max_round,
                sampling_policy=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
                emit_phase_close=False,
            )
            new_messages = conversation.messages[before_count:]
            proposal = next((msg.content for msg in new_messages if msg.speaker == state.owner_role), "")
            review = next((msg.content for msg in new_messages if msg.speaker == state.reviewer_role), "")
            resolution = next((msg.content for msg in reversed(new_messages) if msg.speaker == "moderator"), "")
            state.todo_groups = mark_todo_group_status(
                state.todo_groups,
                group_id,
                "accepted" if resolution else "needs_revision",
                agent_output=proposal,
                review_output=review,
                accepted_summary=resolution or proposal,
            )
            base_context["todo_groups"] = list(state.todo_groups)
        state.current_todo_group = {}
        base_context["current_todo_group"] = {}
        base_context.pop("agent_orchestrator_delegation_mode", None)
        return conversation, state

    def _apply_coverage_to_state_and_artifact(self, state: Any, artifact: PlanArtifact, part_families: list[PartFamily]) -> None:
        source_todos = state.coverage_todos or build_plan_todos_from_spec(None, part_families)
        state.coverage_todos = mark_plan_coverage(source_todos, artifact, part_families)
        state.coverage_summary = coverage_summary(state.coverage_todos)
        state.todo_groups = sync_todo_group_status_with_coverage(state.todo_groups, state.coverage_todos)
        issues = coverage_open_issues(state.coverage_todos)
        if not issues:
            state.revision_requests = []
            state.clarification_requests = []
            return
        state.phase_status = "needs_revision"
        state.revision_requests = coverage_revision_requests(
            state.coverage_todos,
            state.todo_groups,
            owner=state.owner_role,
            reviewer=state.reviewer_role,
        )
        state.clarification_requests = coverage_clarification_requests(state.revision_requests)
        state.phase_quality_flags = sorted(set([*state.phase_quality_flags, *coverage_quality_flags(state.coverage_todos)]))
        existing = {issue.summary for issue in state.open_issues}
        for index, summary in enumerate(issues, start=1):
            if summary in existing:
                continue
            state.open_issues.append(
                OpenIssue(
                    id=f"{state.phase_name}-coverage-{index}",
                    summary=summary,
                    owner=state.owner_role,
                    blocking=True,
                    issue_type="coverage_gap",
                    impact="Required downstream todo is not covered by the extracted plan artifact.",
                    introduced_by="coverage",
                )
            )
        artifact.open_issues = self._merge_failure_notes(artifact.open_issues, issues)
        artifact.failure_notes = self._merge_failure_notes(artifact.failure_notes, issues)

    def _compute_plan(self, spec_artifact: SpecArtifact, part_families: list[PartFamily]) -> PlanArtifact:
        layers: list[list[PartFamily]] = build_execution_dag(part_families)
        world_positions: dict[str, list[float]] = {}
        steps: list[dict[str, Any]] = []
        build_responsibilities: list[dict[str, Any]] = []
        assembly_responsibilities: list[dict[str, Any]] = []
        ordering_constraints: list[dict[str, Any]] = []
        dependency_summary: list[str] = []
        risk_hotspots: list[dict[str, Any]] = []
        step_index = 0
        spec_parts: dict[str, Any] = spec_artifact.parts

        def bbox_for(part_name: str) -> list[float]:
            entry = spec_parts.get(part_name, {})
            if isinstance(entry, dict):
                bbox = entry.get("target_bbox", {}) or {}
                return [
                    float(bbox.get("width", 1.0)),
                    float(bbox.get("depth", 1.0)),
                    float(bbox.get("height", 1.0)),
                ]
            return [1.0, 1.0, 1.0]

        for layer_index, layer in enumerate(layers):
            for family in layer:
                bbox = bbox_for(family.name)
                if family.parent_name is None:
                    pos, rot, scale = solve_root_placement(bbox)
                else:
                    parent_world_pos = world_positions.get(family.parent_name, [0.0, 0.0, 0.0])
                    parent_bbox = bbox_for(family.parent_name)
                    parent_entry = spec_parts.get(family.parent_name, {})
                    parent_attachment = [0.0, 0.0, 0.0]
                    if isinstance(parent_entry, dict):
                        attachment_points = parent_entry.get("attachment_points", []) or []
                        if attachment_points:
                            parent_attachment = list(attachment_points[0].get("local_offset", [0, 0, 0]))
                    symmetry = (
                        family.symmetry_group
                        if isinstance(family.symmetry_group, SymmetryGroup)
                        else SymmetryGroup.NONE
                    )
                    pos, rot, scale = solve_placement(
                        parent_world_position=parent_world_pos,
                        parent_world_rotation_degrees=[0.0, 0.0, 0.0],
                        parent_world_scale=parent_bbox,
                        parent_attachment_local=parent_attachment,
                        child_attachment_local=[0.0, 0.0, 0.0],
                        child_world_scale=bbox,
                        symmetry=symmetry,
                        instance_index=1,
                    )

                world_positions[family.name] = pos
                steps.append(
                    {
                        "step_index": step_index,
                        "type": "build",
                        "family": family.name,
                        "layer": layer_index,
                        "parent": family.parent_name,
                        "instance_count": family.instance_count,
                        "symmetry_group": (
                            family.symmetry_group.value
                            if isinstance(family.symmetry_group, SymmetryGroup)
                            else str(family.symmetry_group)
                        ),
                        "world_position": pos,
                        "world_rotation": rot,
                        "world_scale": scale,
                    }
                )
                build_responsibilities.append(
                    {
                        "id": f"build-{family.name}",
                        "family": family.name,
                        "summary": f"Builder creates the {family.name} geometry from the agreed primitive and bounding box.",
                        "geometry_assumptions": [
                            f"Use the {spec_parts.get(family.name, {}).get('primitive', 'cube')} primitive for {family.name}.",
                            f"Match the target bounding box for {family.name} before assembly.",
                        ],
                        "deferred_placement": [
                            "Final attachment, parenting, and mirrored placement are deferred to the Assembler.",
                        ],
                        "decision_refs": [f"plan.build_responsibilities.{family.name}"],
                    }
                )
                assembly_notes = []
                if family.parent_name:
                    assembly_notes.append(f"Attach {family.name} to parent {family.parent_name}.")
                    dependency_summary.append(f"{family.name} depends on {family.parent_name} being built before final placement.")
                    ordering_constraints.append(
                        {
                            "id": f"ordering-{family.parent_name}-before-{family.name}",
                            "summary": f"Build {family.parent_name} before assembling {family.name}.",
                            "depends_on": [f"build:{family.parent_name}"],
                            "responsibility": "builder",
                            "decision_refs": [f"plan.ordering_constraints.{family.parent_name}-before-{family.name}"],
                        }
                    )
                else:
                    dependency_summary.append(f"{family.name} is a root family and anchors later assembly steps.")
                    ordering_constraints.append(
                        {
                            "id": f"ordering-root-{family.name}",
                            "summary": f"Build root family {family.name} before dependent placement work.",
                            "depends_on": [],
                            "responsibility": "builder",
                            "decision_refs": [f"plan.ordering_constraints.root-{family.name}"],
                        }
                    )
                if family.instance_count > 1 or family.parent_name is not None:
                    symmetry_text = (
                        family.symmetry_group.value
                        if isinstance(family.symmetry_group, SymmetryGroup)
                        else str(family.symmetry_group)
                    )
                    assembly_notes.append(f"Assembler resolves symmetry group {symmetry_text} and final hierarchy for {family.name}.")
                assembly_responsibilities.append(
                    {
                        "id": f"assemble-{family.name}",
                        "family": family.name,
                        "summary": f"Assembler performs the final placement and hierarchy work for {family.name}.",
                        "placement_relations": assembly_notes or [f"Place {family.name} in its final world-space location during assembly."],
                        "hierarchy_notes": [
                            "Builder does not own the final assembly placement.",
                            f"Use {family.name}'s attachment and symmetry context during assembly.",
                        ],
                        "target_parent_family": family.parent_name,
                        "attachment_target_family": family.parent_name,
                        "attachment_target_point_id": self._first_attachment_point_id(spec_parts.get(family.parent_name, {})),
                        "local_anchor_point_id": self._first_attachment_point_id(spec_parts.get(family.name, {})),
                        "placement_rule": "align_local_anchor_to_target_point" if family.parent_name else "place_at_world_position",
                        "required_parenting": bool(family.parent_name),
                        "decision_refs": [f"plan.assembly_responsibilities.{family.name}"],
                    }
                )
                spec_entry = spec_parts.get(family.name, {})
                attachment_points = spec_entry.get("attachment_points", []) if isinstance(spec_entry, dict) else []
                if family.parent_name and not attachment_points:
                    risk_hotspots.append(
                        {
                            "id": f"risk-{family.name}-missing-attachment",
                            "summary": f"{family.name} relies on assembly placement but lacks explicit attachment points.",
                            "owner": "builder",
                            "issue_refs": [f"plan-open-{family.name}-attachment"],
                            "reason": "Missing attachment details could create assembly ambiguity.",
                        }
                    )
                if family.instance_count > 1 and family.symmetry_group == SymmetryGroup.NONE:
                    risk_hotspots.append(
                        {
                            "id": f"risk-{family.name}-symmetry",
                            "summary": f"{family.name} has multiple instances without an explicit symmetry plan.",
                            "owner": "builder",
                            "issue_refs": [f"plan-open-{family.name}-symmetry"],
                            "reason": "Instance placement may drift without a symmetry contract.",
                        }
                    )
                step_index += 1

        artifact = PlanArtifact()
        artifact.spec_id = spec_artifact.blueprint_id
        artifact.dag = layers
        artifact.steps = steps
        artifact.world_positions = world_positions
        artifact.build_responsibilities = build_responsibilities
        artifact.assembly_responsibilities = assembly_responsibilities
        artifact.dependency_summary = dependency_summary
        artifact.ordering_constraints = ordering_constraints
        artifact.risk_hotspots = risk_hotspots
        return artifact

    def _persist_plan_artifact(self, context: Any, artifact: PlanArtifact) -> None:
        payload = context if isinstance(context, dict) else {}
        runtime_root_value = payload.get("runtime_root")
        session_id = str(payload.get("session_id", "")).strip()
        if not runtime_root_value or not session_id:
            return
        runtime_root = Path(str(runtime_root_value))
        ensure_session_runtime_dir(runtime_root, session_id)
        path = session_plan_artifact_path(runtime_root, session_id)
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        temp_path.write_text(json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)

    def _overlay_extracted_plan(
        self,
        base_artifact: PlanArtifact,
        extraction_result: PlanArtifact,
        *,
        fallback_summary: str,
        fallback_open_issues: list[str],
        allowed_families: list[str] | None = None,
    ) -> PlanArtifact:
        allowed = {str(family).strip() for family in (allowed_families or []) if str(family).strip()}
        base_artifact.summary = extraction_result.summary or fallback_summary
        base_artifact.execution_rationale = extraction_result.execution_rationale
        extracted_build = self._filter_responsibilities_by_family(extraction_result.build_responsibilities, allowed)
        extracted_assembly = self._filter_responsibilities_by_family(extraction_result.assembly_responsibilities, allowed)
        base_artifact.build_responsibilities = extracted_build or base_artifact.build_responsibilities
        base_artifact.assembly_responsibilities = extracted_assembly or base_artifact.assembly_responsibilities
        base_artifact.dependency_summary = extraction_result.dependency_summary or base_artifact.dependency_summary
        base_artifact.ordering_constraints = self._filter_constraints_by_family(extraction_result.ordering_constraints, allowed) or base_artifact.ordering_constraints
        base_artifact.risk_hotspots = self._filter_responsibilities_by_family(extraction_result.risk_hotspots, allowed, owner_key="owner") or base_artifact.risk_hotspots
        base_artifact.open_issues = extraction_result.open_issues or fallback_open_issues
        return base_artifact

    def _filter_responsibilities_by_family(
        self,
        items: list[dict[str, Any]],
        allowed: set[str],
        *,
        owner_key: str = "family",
    ) -> list[dict[str, Any]]:
        if not allowed:
            return list(items)
        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            family = str(item.get(owner_key) or item.get("family") or "").strip()
            if family in allowed:
                result.append(item)
        return result

    def _filter_constraints_by_family(self, items: list[dict[str, Any]], allowed: set[str]) -> list[dict[str, Any]]:
        if not allowed:
            return list(items)
        result: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            text = json.dumps(item, ensure_ascii=False, default=str)
            if any(family in text for family in allowed) and not any(
                token in text for token in ("Conceptual_Extension", "Assembly_E2E", "Assembly")
            ):
                result.append(item)
        return result

    def _merge_validation_issues(self, *issue_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for group in issue_groups:
            for issue in group:
                code = str(issue.get("code", "")).strip()
                family = str(issue.get("family", "")).strip()
                summary = str(issue.get("summary", "")).strip()
                key = (code, family, summary)
                if not summary or key in seen:
                    continue
                seen.add(key)
                merged.append(issue)
        return merged

    def _merge_open_issues_with_contract_gaps(self, existing: list[str], contract_gaps: list[dict[str, Any]]) -> list[str]:
        merged = [str(item).strip() for item in existing if str(item).strip()]
        for issue in contract_gaps:
            summary = str(issue.get("summary", "")).strip()
            family = str(issue.get("family", "")).strip() or "unknown family"
            missing = ", ".join(str(item).strip() for item in issue.get("missing_contract_fields", []) if str(item).strip())
            note = summary or f"Assembly contract for {family} is still missing: {missing}."
            if note not in merged:
                merged.append(note)
        return merged

    def _merge_failure_notes(self, existing: list[str], additions: list[str]) -> list[str]:
        merged = [str(item).strip() for item in existing if str(item).strip()]
        for note in additions:
            text = str(note).strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    def _clean_open_issues(self, issues: list[str], has_real_issues: bool) -> list[str]:
        cleaned = [str(item).strip() for item in issues if str(item).strip()]
        if has_real_issues:
            cleaned = [item for item in cleaned if not item.lower().startswith("none remaining")]
        elif cleaned and all(item.lower().startswith("none remaining") for item in cleaned):
            return []
        return cleaned

    def _first_attachment_point_id(self, spec_entry: Any) -> str | None:
        if not isinstance(spec_entry, dict):
            return None
        attachment_points = spec_entry.get("attachment_points", [])
        if not isinstance(attachment_points, list) or not attachment_points:
            return None
        first = attachment_points[0]
        if not isinstance(first, dict):
            return None
        name = str(first.get("name", "")).strip()
        return name or None

    def _run_contract_clarification(
        self,
        *,
        conversation: Conversation,
        state: Any,
        registry: ExpertRegistry,
        llm: Any,
        context: Any,
        spec_artifact: SpecArtifact,
        missing_issues: list[dict[str, Any]],
        emit: Callable | None,
    ) -> tuple[Conversation, Any]:
        from ai_3d_modeling_agent.multi_expert.core.meeting import persist_phase_meeting_state

        reviewer = registry.get("reviewer")
        planner = registry.get("planner")
        _ = reviewer
        _ = planner
        state.clarification_attempted = True
        state.missing_contract_fields = list(missing_issues)
        state.current_round += 1
        clarification_round = state.current_round
        persist_phase_meeting_state(context, state)

        challenge_content = self._build_clarification_challenge(missing_issues)
        challenge = Message(
            speaker="reviewer",
            turn=len(conversation.messages) + 1,
            phase=self.name,
            content=challenge_content,
            structured={"kind": "challenge", "clarification_scope": "assembly_contract"},
        )
        conversation.append(challenge)
        challenge_id = update_state_after_challenge(state, clarification_round, challenge)
        emit_meeting_event(
            emit,
            self.name,
            "challenge",
            round_index=clarification_round,
            speaker=challenge.speaker,
            role="reviewer",
            full_content=challenge.content,
            summary=summarize_turn_text(challenge.content, ["concern"]),
            open_issue_refs=[challenge_id],
            clarification_scope="assembly_contract",
            missing_contract_fields=list(missing_issues),
            target_family=",".join(sorted({str(item.get('family', '')).strip() for item in missing_issues if str(item.get('family', '')).strip()})),
        )
        persist_phase_meeting_state(context, state)

        clarification_messages = [
            {"role": "user", "content": self._build_clarification_prompt(state, spec_artifact, missing_issues, conversation)}
        ]
        clarification_context = {
            **(context or {}),
            "phase_name": self.name,
            "agent_role": "planner",
            "meeting_turn_kind": "response",
            "meeting_state": meeting_state_to_dict(state),
            "missing_contract_fields": list(missing_issues),
        } if isinstance(context, dict) else {
            "phase_name": self.name,
            "agent_role": "planner",
            "meeting_turn_kind": "response",
            "meeting_state": meeting_state_to_dict(state),
            "missing_contract_fields": list(missing_issues),
        }
        try:
            response_text = llm.call(
                system_prompt="",
                messages=clarification_messages,
                sampling=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.for_turn("planner", "response"),
                agent="moderator",
                label="plan.clarification_response",
                context=clarification_context,
            )
        except TypeError as exc:
            if "unexpected keyword" not in str(exc):
                raise
            response_text = llm.call(
                system_prompt="",
                messages=clarification_messages,
                sampling=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.for_turn("planner", "response"),
            )
        response = Message(
            speaker="planner",
            turn=len(conversation.messages) + 1,
            phase=self.name,
            content=response_text,
            structured={"kind": "response", "clarification_scope": "assembly_contract"},
        )
        conversation.append(response)
        emit_meeting_event(
            emit,
            self.name,
            "response",
            round_index=clarification_round,
            speaker=response.speaker,
            role="planner",
            full_content=response.content,
            summary=summarize_turn_text(response.content, ["response"]),
            open_issue_refs=[challenge_id],
            clarification_scope="assembly_contract",
            missing_contract_fields=list(missing_issues),
            target_family=",".join(sorted({str(item.get('family', '')).strip() for item in missing_issues if str(item.get('family', '')).strip()})),
        )
        persist_phase_meeting_state(context, state)

        proposal = Message(
            speaker="planner",
            turn=max(1, len(conversation.messages) - 1),
            phase=self.name,
            content="Proposal: Clarify the missing assembly contract fields using the accepted planning decisions and specification attachment ids.",
        )
        resolution_text = generate_resolution(
            llm,
            state,
            proposal,
            challenge,
            response,
            sampling=DEFAULT_MULTI_EXPERT_SAMPLING_POLICY.for_turn("moderator", "resolution"),
        )
        resolution = Message(
            speaker="moderator",
            turn=len(conversation.messages) + 1,
            phase=self.name,
            content=resolution_text,
            structured={"kind": "resolution", "clarification_scope": "assembly_contract"},
        )
        conversation.append(resolution)
        apply_resolution_to_state(
            state,
            clarification_round,
            resolution_text,
            challenge_id,
            proposal_message=proposal,
            challenge_message=challenge,
            response_message=response,
        )
        emit_meeting_event(
            emit,
            self.name,
            "resolution",
            round_index=clarification_round,
            speaker=resolution.speaker,
            role="moderator",
            full_content=resolution.content,
            summary=state.last_resolution_summary or summarize_turn_text(resolution.content, ["decision"]),
            decision_refs=[item.id for item in state.accepted_decisions if item.source_round == clarification_round],
            open_issue_refs=[issue.id for issue in state.open_issues],
            quality_flags=list(state.phase_quality_flags),
            change_summary=state.round_change_summary,
            clarification_scope="assembly_contract",
            missing_contract_fields=list(missing_issues),
            target_family=",".join(sorted({str(item.get('family', '')).strip() for item in missing_issues if str(item.get('family', '')).strip()})),
        )
        persist_phase_meeting_state(context, state)
        return conversation, state

    def _build_clarification_challenge(self, missing_issues: list[dict[str, Any]]) -> str:
        lines = ["Concern: The draft assembly contract is missing blocking fields needed for faithful placement."]
        impacts: list[str] = []
        missing_lines: list[str] = []
        for issue in missing_issues:
            family = str(issue.get("family", "")).strip() or "unknown family"
            missing = [str(item).strip() for item in issue.get("missing_contract_fields", []) if str(item).strip()]
            if not missing:
                continue
            missing_lines.append(f"- {family}: {', '.join(missing)}")
            impacts.append(f"{family} could silently fall back to a default/origin placement without these fields.")
        if impacts:
            lines.append("Impact:")
            lines.extend(f"- {item}" for item in impacts)
        if missing_lines:
            lines.append("Missing Constraint:")
            lines.extend(missing_lines)
        return "\n".join(lines)

    def _build_clarification_prompt(
        self,
        state: Any,
        spec_artifact: SpecArtifact,
        missing_issues: list[dict[str, Any]],
        conversation: Conversation,
    ) -> str:
        relevant_spec: dict[str, Any] = {}
        referenced_families = {
            str(issue.get("family", "")).strip()
            for issue in missing_issues
            if str(issue.get("family", "")).strip()
        }
        for family in sorted(referenced_families):
            entry = spec_artifact.parts.get(family, {}) if isinstance(spec_artifact.parts, dict) else {}
            if isinstance(entry, dict):
                relevant_spec[family] = entry
        return (
            "Task: Provide a targeted assembly contract clarification response.\n"
            "Return plain meeting text with Response and Revision sections.\n\n"
            f"Accepted decisions:\n{json.dumps([item.summary for item in state.accepted_decisions], ensure_ascii=False, indent=2)}\n\n"
            f"Last resolution summary:\n{state.last_resolution_summary}\n\n"
            f"Relevant spec entries:\n{json.dumps(relevant_spec, ensure_ascii=False, indent=2)}\n\n"
            f"Recent conversation excerpt:\n{json.dumps(recent_conversation_excerpt(conversation), ensure_ascii=False, indent=2)}\n\n"
            f"Missing contract fields:\n{json.dumps(missing_issues, ensure_ascii=False, indent=2)}\n\n"
            "Provide only the missing assembly contract information needed to make placement executable."
        )
