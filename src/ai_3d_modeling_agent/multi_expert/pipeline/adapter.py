"""Adapter: FinalArtifact → MultiStageProgressSnapshot conversion.

Domain: transforms the aggregate pipeline output into the GUI-facing
progress snapshot format, bridging the multi-expert pipeline to the
session progress display layer.
"""

from __future__ import annotations

from typing import Any

from ai_3d_modeling_agent.multi_expert.artifacts.final import (
    FinalArtifact,
    PipelineStatus,
)
from ai_3d_modeling_agent.schemas.modeling_plan import ModelingRequest
from ai_3d_modeling_agent.schemas.session_progress import (
    AssemblyProgress,
    AssemblyRoundRecord,
    FinalValidationSummary,
    MultiStageProgressSnapshot,
    PartRefinementRoundRecord,
    PartTaskProgress,
    ProgressActionRecord,
    ProgressContextRecord,
)

# Phase execution order — used to determine the current stage from
# phase_statuses when the pipeline has failed.
PHASE_ORDER = [
    "design",
    "specs",
    "plan",
    "build",
    "assembly",
    "validation",
]

# PipelineStatus → stage_status string
_STATUS_MAP: dict[PipelineStatus, str] = {
    PipelineStatus.SUCCESS: "completed",
    PipelineStatus.SUCCESS_WITH_WARNINGS: "completed_with_warnings",
    PipelineStatus.DEGRADED: "degraded",
    PipelineStatus.PARTIAL: "partial",
    PipelineStatus.FAILED: "failed",
}

# BuildArtifact.status → PartTaskProgress.status
_BUILD_STATUS_MAP: dict[str, str] = {
    "built": "approved",
    "failed": "failed",
    "skipped": "skipped",
}


def final_artifact_to_snapshot(
    artifact: FinalArtifact,
    task_prompt: str,
    session_id: str = "",
) -> MultiStageProgressSnapshot:
    """Convert a FinalArtifact to a MultiStageProgressSnapshot.

    Maps all pipeline phase outputs (build, assembly, validation) into
    the GUI-facing progress snapshot format.  Handles optional / missing
    fields gracefully by falling back to sensible defaults.

    Args:
        artifact: The pipeline final artifact to convert.
        task_prompt: The original task prompt text (stored in ``task``
            and ``request.task_prompt``).
        session_id: Optional session identifier used to set
            ``active_task_id``.

    Returns:
        A fully populated ``MultiStageProgressSnapshot``.
    """
    stage = _determine_current_stage(artifact.phase_statuses, artifact.status)
    stage_status = _STATUS_MAP.get(artifact.status, "unknown")
    overall_status = _map_overall_status(artifact.status)

    return MultiStageProgressSnapshot(
        workflow_type="multi_stage_modeling",
        status=overall_status,
        task=task_prompt,
        stage=stage,
        stage_status=stage_status,
        request=ModelingRequest(task_prompt=task_prompt, references=[]),
        required_objects=[],
        plan=None,
        multi_expert_mode=True,
        planning_llm_prompt_preview="",
        llm_prompt_events=[],
        active_task_id=session_id,
        completed_task_ids=_build_completed_ids(artifact.build_results),
        part_tasks=_build_part_tasks(artifact.build_results),
        assembly=_build_assembly(artifact.assembly_results),
        final_validation=_build_final_validation(artifact.validation),
        stop_reason=_build_stop_reason(artifact),
        max_part_refinement_rounds=0,
        max_assembly_rounds=0,
        dnc_mode=False,
        checkpoint_version=0,
        dnc_part_progress=[],
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _map_overall_status(status: PipelineStatus) -> str:
    """Map PipelineStatus to the snapshot-level ``status`` string.

    ``SUCCESS`` and ``SUCCESS_WITH_WARNINGS`` both resolve to
    ``"completed"`` at the snapshot level because the pipeline did run
    to completion in both cases.
    """
    if status == PipelineStatus.SUCCESS:
        return "completed"
    if status == PipelineStatus.SUCCESS_WITH_WARNINGS:
        return "completed"
    if status == PipelineStatus.DEGRADED:
        return "degraded"
    if status == PipelineStatus.PARTIAL:
        return "partial"
    if status == PipelineStatus.FAILED:
        return "failed"
    return "unknown"


def _determine_current_stage(
    phase_statuses: dict[str, PipelineStatus],
    pipeline_status: PipelineStatus,
) -> str:
    """Determine the current (or last-executed) pipeline stage.

    For every status except ``FAILED`` the stage is simply
    ``"completed"`` because all configured phases ran.  For
    ``FAILED`` we scan *phase_statuses* in execution order to
    find the first phase that has a ``FAILED`` status.
    """
    if pipeline_status == PipelineStatus.FAILED:
        for phase in PHASE_ORDER:
            ps = phase_statuses.get(phase)
            if ps == PipelineStatus.FAILED:
                return phase
        # Fallback: return the last phase that has an entry
        for phase in reversed(PHASE_ORDER):
            if phase in phase_statuses:
                return phase
        return "unknown"

    return "completed"


def _build_completed_ids(
    build_results: dict[str, Any],
) -> list[str]:
    """Extract the list of part names that built successfully."""
    return [
        part_name
        for part_name, ba in build_results.items()
        if getattr(ba, "status", None) == "built"
    ]


def _build_part_tasks(
    build_results: dict[str, Any],
) -> list[PartTaskProgress]:
    """Map ``build_results`` (keyed by part name) to ``PartTaskProgress``.

    Each ``BuildArtifact`` in the dict becomes one ``PartTaskProgress``.
    Refinement rounds are created from ``refinement_rounds``,
    ``capture_paths``, and ``action_history``.
    """
    tasks: list[PartTaskProgress] = []
    for part_name, ba in build_results.items():
        bstatus = getattr(ba, "status", "built")
        task_status = _BUILD_STATUS_MAP.get(bstatus, "pending")
        source_obj = getattr(ba, "source_object_name", "") or part_name
        refinement_rounds = getattr(ba, "refinement_rounds", 0)
        capture_paths = list(getattr(ba, "capture_paths", []))
        action_history = list(getattr(ba, "action_history", []))

        rounds = _build_rounds(
            refinement_rounds, capture_paths, action_history, bstatus
        )

        tasks.append(
            PartTaskProgress(
                task_id=part_name,
                title=part_name,
                object_name=source_obj,
                status=task_status,
                current_round=refinement_rounds,
                approved=(bstatus == "built"),
                rounds=rounds,
            )
        )
    return tasks


def _build_rounds(
    refinement_rounds: int,
    capture_paths: list[str],
    action_history: list[dict[str, Any]],
    build_status: str,
) -> list[PartRefinementRoundRecord]:
    """Build refinement-round records for a single part build."""
    num_rounds = max(refinement_rounds, 1)
    rounds: list[PartRefinementRoundRecord] = []
    for i in range(num_rounds):
        cap = capture_paths[i] if i < len(capture_paths) else ""
        action = action_history[i] if i < len(action_history) else None

        requested_action: ProgressActionRecord | None = None
        if action is not None:
            requested_action = ProgressActionRecord(
                action_type=action.get("action_type", ""),
                parameters=dict(action.get("parameters", {})),
                reason=action.get("reason", ""),
                execution_status="completed",
            )

        rounds.append(
            PartRefinementRoundRecord(
                round_index=i,
                capture_path=cap,
                capture_paths=list(capture_paths),
                approved=(build_status == "built"),
                requested_action=requested_action,
            )
        )
    return rounds


def _build_assembly(
    assembly_results: list[Any],
) -> AssemblyProgress:
    """Map ``assembly_results`` (list of ``AssemblyArtifact``) to ``AssemblyProgress``.

    Each artifact becomes one ``AssemblyRoundRecord``.
    """
    if not assembly_results:
        return AssemblyProgress()

    rounds: list[AssemblyRoundRecord] = []
    all_approved = True

    for i, art in enumerate(assembly_results):
        step_index = getattr(art, "step_index", i)
        review_verdict = getattr(art, "review_verdict", None)

        if review_verdict is not None and review_verdict != "approved":
            all_approved = False

        rounds.append(
            AssemblyRoundRecord(
                round_index=i,
                assembly_step_index=step_index,
            )
        )

    return AssemblyProgress(
        status="completed" if all_approved else "pending",
        current_round=len(assembly_results) - 1,
        approved=all_approved,
        rounds=rounds,
    )


def _build_final_validation(
    validation: Any,
) -> FinalValidationSummary:
    """Map ``ValidationArtifact`` to ``FinalValidationSummary``.

    Returns a default (all-empty) summary when *validation* is ``None``.
    """
    if validation is None:
        return FinalValidationSummary()

    passed = getattr(validation, "passed", False)
    errors = list(getattr(validation, "errors", []))

    return FinalValidationSummary(
        status="completed" if passed else "failed",
        missing_critical_parts=errors,
        quantitative_metrics=list(getattr(validation, "comparisons", [])),
    )


def _build_stop_reason(artifact: FinalArtifact) -> str:
    """Derive a human-readable stop reason from the artifact status."""
    status = artifact.status
    degraded = artifact.degraded_parts

    if status == PipelineStatus.SUCCESS:
        return ""
    if status == PipelineStatus.FAILED:
        detail = _first_failure_detail(artifact)
        if detail:
            return f"Pipeline failed: {detail}"
        return f"Pipeline failed: {artifact.status.value}"
    if status == PipelineStatus.DEGRADED and degraded:
        return f"Pipeline degraded on parts: {', '.join(degraded)}"
    if status == PipelineStatus.PARTIAL:
        return "Pipeline completed with partial artifacts"
    if status == PipelineStatus.SUCCESS_WITH_WARNINGS:
        return "Pipeline completed with overridden warnings"
    return ""


def _first_failure_detail(artifact: FinalArtifact) -> str:
    candidates: list[Any] = []
    validation = getattr(artifact, "validation", None)
    candidates.extend(list(getattr(validation, "errors", []) or []))
    candidates.extend(list(getattr(validation, "failure_notes", []) or []))
    for phase_artifact in (
        getattr(artifact, "specs", None),
        getattr(artifact, "plan", None),
        getattr(artifact, "validation", None),
    ):
        candidates.extend(list(getattr(phase_artifact, "failure_notes", []) or []))
        candidates.extend(list(getattr(phase_artifact, "open_issues", []) or []))
    for build_result in dict(getattr(artifact, "build_results", {}) or {}).values():
        candidates.extend(list(getattr(build_result, "failure_notes", []) or []))
    for assembly_result in list(getattr(artifact, "assembly_results", []) or []):
        candidates.extend(list(getattr(assembly_result, "failure_notes", []) or []))
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""
