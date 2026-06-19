"""Specification phase with moderated proposal/challenge/response/resolution flow."""

from __future__ import annotations

from typing import Any, Callable

from ai_3d_modeling_agent.multi_expert.artifacts import DesignArtifact, SpecArtifact
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation
from ai_3d_modeling_agent.multi_expert.core.coverage import (
    build_todo_groups,
    build_spec_todos_from_design,
    coverage_clarification_requests,
    coverage_open_issues,
    coverage_revision_requests,
    coverage_quality_flags,
    coverage_summary,
    mark_todo_group_status,
    mark_spec_coverage,
    sync_todo_group_status_with_coverage,
)
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import (
    build_spec_artifact_from_markdown_state,
    write_spec_markdown,
)
from ai_3d_modeling_agent.multi_expert.core.meeting import (
    DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
    OpenIssue,
    create_phase_meeting_state,
    create_seed_message,
    meeting_state_to_dict,
    persist_phase_meeting_state,
    recent_conversation_excerpt,
    run_moderated_phase,
)
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry


class SpecPhase(Phase):
    def __init__(self) -> None:
        participants = ["specifier", "reviewer"]
        super().__init__(
            name="spec",
            goal="Specify geometry, attachment points, and constraints for every accepted part family.",
            participants=participants,
            convener=None,
            termination=TerminationPolicy(max_rounds=2, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=SpecArtifact,
        )

    def run(
        self,
        registry: ExpertRegistry,
        context: Any,
        llm: Any,
        design_artifact: DesignArtifact,
        event_emitter: Callable | None = None,
    ) -> SpecArtifact:
        emit = event_emitter or self._emit_event
        phase_context = dict(context or {})
        phase_context["allowed_families"] = self._design_family_names(design_artifact)
        phase_context["design_parts"] = design_artifact.parts
        phase_context["spec_geometry_completion_policy"] = str(
            phase_context.get("spec_geometry_completion_policy", "require_user_input") or "require_user_input"
        )
        spec_todos = build_spec_todos_from_design(design_artifact)
        todo_groups = build_todo_groups(spec_todos, phase=self.name, role="specifier")
        phase_context["coverage_todos"] = spec_todos
        phase_context["coverage_summary"] = coverage_summary(spec_todos)
        phase_context["todo_groups"] = todo_groups
        conversation = Conversation(phase_name=self.name, context=phase_context)
        conversation.append(
            create_seed_message(
                self.name,
                (
                    f"Design summary:\n{design_artifact.summary}\n\n"
                    f"Part families:\n{design_artifact.parts}\n\n"
                    f"Assembly concept:\n{design_artifact.assembly_concept}\n\n"
                    f"Unresolved design issues:\n{design_artifact.unresolved_issues}"
                ),
            )
        )

        state = create_phase_meeting_state(self.name, self.goal, "specifier", "reviewer")
        state.coverage_todos = spec_todos
        state.coverage_summary = coverage_summary(spec_todos)
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
            )
        state.coverage_todos = spec_todos
        state.coverage_summary = coverage_summary(spec_todos)

        result = self._extract_and_validate_spec(
            conversation,
            llm,
            state,
            design_artifact,
            set(phase_context["allowed_families"]),
            str(phase_context["spec_geometry_completion_policy"]),
        )
        if state.revision_requests:
            conversation, state = self._run_targeted_revision_requests(
                conversation=conversation,
                registry=registry,
                llm=llm,
                base_context=phase_context,
                state=state,
                emit=emit,
            )
            result = self._extract_and_validate_spec(
                conversation,
                llm,
                state,
                design_artifact,
                set(phase_context["allowed_families"]),
                str(phase_context["spec_geometry_completion_policy"]),
            )
        persist_phase_meeting_state(phase_context, state)
        return result

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
        return conversation, state

    def _run_targeted_revision_requests(
        self,
        *,
        conversation: Conversation,
        registry: ExpertRegistry,
        llm: Any,
        base_context: dict[str, Any],
        state: Any,
        emit: Callable | None,
    ) -> tuple[Conversation, Any]:
        requests = list(state.revision_requests or [])
        if not requests:
            return conversation, state
        for request in requests:
            target = str(request.get("target_name", "")).strip()
            missing_todos = list(request.get("missing_todos", []) or [])
            if not target or not missing_todos:
                continue
            group = {
                "id": str(request.get("group_id") or f"{self.name}:{target}"),
                "phase": self.name,
                "target_name": target,
                "target_kind": request.get("target_kind", "part"),
                "role": state.owner_role,
                "review_role": state.reviewer_role,
                "status": "needs_revision",
                "todos": missing_todos,
                "focused_prompt": (
                    f"Correction for `{target}`: Python artifact validation found missing required coverage: "
                    f"{request.get('reason', '')}. Provide a focused revision for this target only. "
                    + (
                        "Policy: assumptions are allowed only if labeled. If enough information exists from the user task and accepted design, provide executable geometry with concrete primitive and numeric target_bbox. If using a reasonable default, label it as assumed and explain the assumption."
                        if str(base_context.get("spec_geometry_completion_policy", "require_user_input")) == "allow_assumptions"
                        else "Policy: do not invent or propose reasonable/default dimensions. Provide numeric target_bbox only when the value is accepted or explicitly available from the user/design context. Otherwise state exactly which user input is required."
                    )
                ),
                "agent_output": request.get("agent_output", ""),
                "review_output": request.get("review_output", ""),
                "accepted_summary": request.get("accepted_summary", ""),
            }
            state.current_todo_group = group
            state.coverage_todos = missing_todos
            state.coverage_summary = coverage_summary(missing_todos)
            base_context["current_todo_group"] = group
            base_context["coverage_todos"] = missing_todos
            base_context["coverage_summary"] = state.coverage_summary
            base_context["revision_request"] = dict(request)
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
            state.revision_requests = [
                {**dict(item), "status": "revision_attempted", "agent_output": proposal, "review_output": review, "accepted_summary": resolution or proposal}
                if str(item.get("id", "")) == str(request.get("id", ""))
                else item
                for item in state.revision_requests
            ]
        state.current_todo_group = {}
        base_context["current_todo_group"] = {}
        base_context.pop("revision_request", None)
        base_context.pop("agent_orchestrator_delegation_mode", None)
        return conversation, state

    def _extract_and_validate_spec(
        self,
        conversation: Conversation,
        llm: Any,
        state: Any,
        design_artifact: DesignArtifact,
        allowed: set[str],
        geometry_policy: str,
    ) -> SpecArtifact:
        source_todos = build_spec_todos_from_design(design_artifact)
        result = build_spec_artifact_from_markdown_state(design_artifact, state)
        if allowed:
            result.parts = {
                name: spec
                for name, spec in (result.parts or {}).items()
                if str(name).strip() in allowed
            }
            result.point_registry = {
                name: points
                for name, points in (result.point_registry or {}).items()
                if str(name).strip() in allowed
            }
        self._preserve_design_instance_counts(result, design_artifact)
        self._apply_geometry_completion_policy(result, geometry_policy)
        self._apply_simple_primitive_spec_policy(result, design_artifact)
        if not result.summary:
            result.summary = state.last_resolution_summary
        if state.open_issues:
            result.validation_notes = list(dict.fromkeys([*result.validation_notes, *[issue.summary for issue in state.open_issues]]))
        state.coverage_todos = mark_spec_coverage(source_todos, result, design_artifact)
        state.coverage_summary = coverage_summary(state.coverage_todos)
        state.todo_groups = sync_todo_group_status_with_coverage(state.todo_groups, state.coverage_todos)
        self._apply_coverage_gaps_to_state(state, result)
        if not coverage_open_issues(state.coverage_todos):
            self._clear_coverage_gaps_from_state(state, result)
            state.revision_requests = []
            state.clarification_requests = []
            if state.phase_status == "needs_revision":
                state.phase_status = "resolved"
            result.failure_notes = []
        write_spec_markdown(
            conversation.context if isinstance(getattr(conversation, "context", None), dict) else {},
            result,
            design=design_artifact,
            meeting_state=state,
        )
        return result

    @staticmethod
    def _apply_geometry_completion_policy(result: SpecArtifact, geometry_policy: str) -> None:
        if str(geometry_policy or "").strip() == "allow_assumptions":
            for spec in list((result.parts or {}).values()):
                if not isinstance(spec, dict):
                    continue
                source = str(spec.get("geometry_source", "") or "").strip().lower()
                if source in {"assumed", "default", "provisional"} and spec.get("target_bbox"):
                    spec["geometry_source"] = "accepted_assumption"
            return
        notes = list(result.validation_notes or [])
        for name, spec in list((result.parts or {}).items()):
            if not isinstance(spec, dict):
                continue
            source = str(spec.get("geometry_source", "") or "").strip().lower()
            has_assumptions = bool(spec.get("assumptions"))
            has_bbox = bool(spec.get("target_bbox"))
            missing_source_for_bbox = has_bbox and not source
            if source in {"assumed", "default", "provisional"} or has_assumptions or missing_source_for_bbox:
                if spec.get("target_bbox"):
                    spec["target_bbox"] = {}
                spec["geometry_source"] = "needs_user_input"
                message = (
                    f"Geometry for {name} is not explicitly accepted (source={source or 'missing'}), "
                    "but spec_geometry_completion_policy=require_user_input; explicit user/design dimensions are required."
                )
                if message not in notes:
                    notes.append(message)
        result.validation_notes = notes

    @staticmethod
    def _clear_coverage_gaps_from_state(state: Any, result: SpecArtifact) -> None:
        state.open_issues = [
            issue
            for issue in list(getattr(state, "open_issues", []) or [])
            if str(getattr(issue, "issue_type", "") or "") != "coverage_gap"
            and str(getattr(issue, "introduced_by", "") or "") != "coverage"
        ]
        state.phase_quality_flags = [
            flag for flag in list(getattr(state, "phase_quality_flags", []) or []) if str(flag) != "coverage_gap"
        ]
        result.validation_notes = [
            note
            for note in list(getattr(result, "validation_notes", []) or [])
            if not str(note).startswith("Coverage gap for ")
        ]
        result.failure_notes = [
            note
            for note in list(getattr(result, "failure_notes", []) or [])
            if not str(note).startswith("Coverage gap for ")
        ]

    @staticmethod
    def _apply_simple_primitive_spec_policy(result: SpecArtifact, design_artifact: DesignArtifact) -> None:
        names = SpecPhase._design_family_names(design_artifact)
        if names != ["cube"]:
            return
        task_text = " ".join(
            str(value or "").lower()
            for value in (
                getattr(design_artifact, "task_prompt", ""),
                getattr(design_artifact, "summary", ""),
                getattr(design_artifact, "assembly_concept", ""),
            )
        )
        if "simple cube" not in task_text and "build a simple cube" not in task_text:
            return
        spec = (result.parts or {}).get("cube") if isinstance(result.parts, dict) else None
        if not isinstance(spec, dict):
            return
        spec["primitive"] = "cube"
        spec["target_bbox"] = {"width": 1.0, "depth": 1.0, "height": 1.0}
        spec["geometry_source"] = "accepted_task_primitive"
        spec.pop("assumptions", None)
        result.validation_notes = [
            note
            for note in list(result.validation_notes or [])
            if "Coverage gap for cube: spec_geometry_defined" not in str(note)
            and "Geometry for cube is not explicitly accepted" not in str(note)
        ]

    @staticmethod
    def _design_family_names(design_artifact: DesignArtifact) -> list[str]:
        parts = design_artifact.parts or {}
        if isinstance(parts, dict):
            return sorted(str(name).strip() for name in parts.keys() if str(name).strip())
        if isinstance(parts, list):
            names = []
            for item in parts:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if name:
                    names.append(name)
            return sorted(dict.fromkeys(names))
        return []

    def _apply_coverage_gaps_to_state(self, state: Any, result: SpecArtifact) -> None:
        issues = coverage_open_issues(state.coverage_todos)
        if not issues:
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
                    impact="Required downstream todo is not covered by the extracted spec artifact.",
                    introduced_by="coverage",
                )
            )
        result.validation_notes = list(dict.fromkeys([*result.validation_notes, *issues]))
        result.failure_notes = list(dict.fromkeys([*result.failure_notes, *issues]))

    @staticmethod
    def _preserve_design_instance_counts(result: SpecArtifact, design_artifact: DesignArtifact) -> None:
        design_parts = design_artifact.parts or []
        if isinstance(design_parts, dict):
            items = [{"name": name, **(value if isinstance(value, dict) else {})} for name, value in design_parts.items()]
        elif isinstance(design_parts, list):
            items = [item for item in design_parts if isinstance(item, dict)]
        else:
            items = []
        counts: dict[str, int] = {}
        for item in items:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            try:
                counts[name] = int(item.get("instance_count", item.get("count", 1)) or 1)
            except (TypeError, ValueError):
                counts[name] = 1
        for name, spec in list((result.parts or {}).items()):
            if not isinstance(spec, dict):
                continue
            count = counts.get(str(name).strip())
            if count is None:
                continue
            spec["instance_count"] = count
