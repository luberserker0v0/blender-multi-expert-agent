"""Design phase with moderated proposal/challenge/response/resolution flow."""

from __future__ import annotations

from typing import Any, Callable

from ai_3d_modeling_agent.multi_expert.artifacts import DesignArtifact
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.markdown_artifacts import (
    build_design_artifact_from_markdown_state,
    write_design_markdown,
)
from ai_3d_modeling_agent.multi_expert.core.meeting import (
    DEFAULT_MULTI_EXPERT_SAMPLING_POLICY,
    create_phase_meeting_state,
    create_seed_message,
    meeting_state_to_dict,
    recent_conversation_excerpt,
    run_moderated_phase,
)
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry


class DesignPhase(Phase):
    def __init__(self) -> None:
        participants = ["designer", "reviewer"]
        super().__init__(
            name="design",
            goal="Decompose the user's task into logical part families and a high-level assembly concept.",
            participants=participants,
            convener=None,
            termination=TerminationPolicy(max_rounds=2, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=DesignArtifact,
        )

    def run(
        self,
        registry: ExpertRegistry,
        context: Any,
        llm: Any,
        task_prompt: str,
        event_emitter: Callable | None = None,
    ) -> DesignArtifact:
        emit = event_emitter or self._emit_event
        phase_context = dict(context or {})
        phase_context.setdefault("allowed_families", [])
        conversation = Conversation(phase_name=self.name, context=phase_context)
        conversation.append(
            create_seed_message(
                self.name,
                (
                    "User task:\n"
                    f"{task_prompt}\n\n"
                    "Design goal:\nIdentify logical part families, the root part, repeated families, symmetry assumptions, "
                    "and the coarse parent-child structure."
                ),
            )
        )

        state = create_phase_meeting_state(self.name, self.goal, "designer", "reviewer")
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

        result = build_design_artifact_from_markdown_state(task_prompt, state, conversation=conversation)
        if not result.summary:
            result.summary = state.last_resolution_summary
        if state.open_issues and not result.unresolved_issues:
            result.unresolved_issues = [issue.summary for issue in state.open_issues]
        write_design_markdown(phase_context, result, meeting_state=state)
        return result
