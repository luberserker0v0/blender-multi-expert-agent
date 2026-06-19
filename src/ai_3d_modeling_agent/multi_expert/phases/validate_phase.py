"""Validate final assembly against specification and planning truth."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ai_3d_modeling_agent.blender.object_ops import BlenderObjectOps
from ai_3d_modeling_agent.multi_expert.artifacts import (
    AssemblyArtifact,
    BuildArtifact,
    PlanArtifact,
    SpecArtifact,
    ValidationArtifact,
)
from ai_3d_modeling_agent.multi_expert.core.convener import ProcessConvener
from ai_3d_modeling_agent.multi_expert.core.conversation import Conversation, Message
from ai_3d_modeling_agent.multi_expert.core.failure import FailurePolicy
from ai_3d_modeling_agent.multi_expert.core.phase import Phase
from ai_3d_modeling_agent.multi_expert.core.planning import validate_plan_structure
from ai_3d_modeling_agent.multi_expert.core.termination import TerminationPolicy
from ai_3d_modeling_agent.multi_expert.core.validator import ProgrammaticValidator
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry

logger = logging.getLogger(__name__)


class ValidatePhase(Phase):
    """Validate the assembled model against the specification."""

    def __init__(self) -> None:
        participants = ["inspector"]
        super().__init__(
            name="validate",
            goal="Validate final assembly against specification",
            participants=participants,
            convener=ProcessConvener(participants=list(participants)),
            termination=TerminationPolicy(max_rounds=3, early_consensus=False),
            failure_policy=FailurePolicy.RETRYABLE,
            artifact_type=ValidationArtifact,
        )

    def run(
        self,
        registry: ExpertRegistry,
        context: Any,
        llm: Any,
        spec_artifact: SpecArtifact,
        assembly_artifacts: list[AssemblyArtifact],
        build_artifacts: list[BuildArtifact] | None = None,
        plan_artifact: PlanArtifact | None = None,
        build_execution_plan: dict[str, Any] | None = None,
        assembly_execution_plan: dict[str, Any] | None = None,
        object_ops: BlenderObjectOps | None = None,
        event_emitter: Callable | None = None,
    ) -> ValidationArtifact:
        """Validate the assembled model against spec and planning diagnostics."""
        _emit = event_emitter or self._emit_event

        if _emit:
            _emit(
                "validate",
                "phase_open",
                "Validator started final inspection.",
                role="validator",
                speaker="Validator",
                round=0,
                summary="Validator started final inspection.",
                full_content="Validator started final inspection.",
            )

        prog_result: ValidationArtifact | None = None
        if build_artifacts and object_ops:
            validator = ProgrammaticValidator()
            prog_result = validator.validate(
                spec_artifact,
                build_artifacts,
                assembly_artifacts,
                object_ops,
            )
            logger.warning(
                "[VALIDATE] programmatic result: passed=%s, errors=%d, warnings=%d, comparisons=%d",
                prog_result.passed,
                len(prog_result.errors),
                len(prog_result.warnings),
                len(prog_result.comparisons),
            )

        planning_context = self._collect_planning_context(
            plan_artifact=plan_artifact,
            spec_artifact=spec_artifact,
            build_artifacts=build_artifacts or [],
            assembly_artifacts=assembly_artifacts,
            build_execution_plan=build_execution_plan or {},
            assembly_execution_plan=assembly_execution_plan or {},
        )

        conversation = Conversation(phase_name=self.name, context=context)
        seed = Message(
            speaker="system",
            turn=0,
            phase=self.name,
            content=self._build_seed_content(
                spec_artifact=spec_artifact,
                assembly_artifacts=assembly_artifacts,
                programmatic_result=prog_result,
                planning_context=planning_context,
            ),
        )
        conversation.append(seed)

        self.convener.current_index = 0
        while not self.convener.check_termination(conversation, self.termination):
            speaker_role = self.convener.choose_next(conversation, context)
            expert = registry.get(speaker_role)
            if expert is None:
                break
            message = expert.speak(conversation, context, llm)
            conversation.append(message)
            self.termination.current_rounds += 1

        result = self._build_validation_artifact(
            conversation=conversation,
            programmatic_result=prog_result,
            planning_context=planning_context,
        )

        result.planning_warnings = list(planning_context["warnings"])
        result.planning_failures = list(planning_context["failures"])
        result.planning_constraint_refs = list(planning_context["constraint_refs"])
        result.planning_responsibility_refs = list(planning_context["responsibility_refs"])

        result.warnings = _merge_unique(result.warnings, result.planning_warnings)
        result.failure_notes = _merge_unique(result.failure_notes, result.planning_failures)
        result.errors = _merge_unique(result.errors, result.planning_failures)
        if result.planning_failures:
            result.passed = False

        if _emit:
            status_text = "Validation passed." if result.passed else f"Validation failed with {len(result.errors)} issues."
            _emit(
                "validate",
                "validation_result",
                status_text,
                role="validator",
                speaker="Validator",
                round=self.termination.current_rounds,
                summary=status_text,
                full_content=status_text,
            )
            _emit(
                "validate",
                "phase_close",
                f"Validator completed inspection in {self.termination.current_rounds} rounds.",
                role="validator",
                speaker="Validator",
                rounds=self.termination.current_rounds,
                round=self.termination.current_rounds,
                summary=f"Validator completed inspection in {self.termination.current_rounds} rounds.",
                full_content=f"Validator completed inspection in {self.termination.current_rounds} rounds.",
            )

        return result

    def _build_validation_artifact(
        self,
        *,
        conversation: Conversation,
        programmatic_result: ValidationArtifact | None,
        planning_context: dict[str, list[str]],
    ) -> ValidationArtifact:
        inspector_notes = [
            message.content.strip()
            for message in conversation.messages
            if message.speaker == "inspector" and message.content.strip()
        ]
        if programmatic_result is not None:
            result = ValidationArtifact(
                passed=programmatic_result.passed,
                errors=list(programmatic_result.errors),
                warnings=list(programmatic_result.warnings),
                comparisons=list(programmatic_result.comparisons),
                failure_notes=list(programmatic_result.failure_notes),
            )
        else:
            result = ValidationArtifact(passed=not planning_context["failures"])
        if inspector_notes:
            result.warnings = _merge_unique(
                result.warnings,
                [f"Inspector note: {inspector_notes[-1][:500]}"],
            )
        if planning_context["failures"]:
            result.passed = False
        return result

    def _build_seed_content(
        self,
        *,
        spec_artifact: SpecArtifact,
        assembly_artifacts: list[AssemblyArtifact],
        programmatic_result: ValidationArtifact | None,
        planning_context: dict[str, list[str]],
    ) -> str:
        placement_summary = []
        for artifact in assembly_artifacts:
            for placement in artifact.placements:
                placement_summary.append(
                    f"  - step {artifact.step_index}: {placement.get('part')} @ {placement.get('world_position')}"
                )

        seed_content = (
            f"Validate against spec: blueprint_id={spec_artifact.blueprint_id}\n"
            f"Spec parts: {list(spec_artifact.parts.keys())}\n"
            f"Spec validation notes: {spec_artifact.validation_notes}\n"
            "Assembly placements:\n"
            + "\n".join(placement_summary)
        )

        if programmatic_result:
            seed_content += "\n\n--- Programmatic validation results ---"
            seed_content += f"\nOverall: {'PASS' if programmatic_result.passed else 'FAIL'}"
            if programmatic_result.errors:
                seed_content += "\nErrors:"
                for item in programmatic_result.errors:
                    seed_content += f"\n  - {item}"
            if programmatic_result.warnings:
                seed_content += "\nWarnings:"
                for item in programmatic_result.warnings:
                    seed_content += f"\n  - {item}"
            if programmatic_result.comparisons:
                seed_content += "\nDetailed comparisons:"
                for item in programmatic_result.comparisons:
                    seed_content += (
                        f"\n  - {item['part_name']}.{item['check']}: expected={item['expected']}, "
                        f"actual={item['actual']}, status={item['status']}"
                    )

        if planning_context["warnings"] or planning_context["failures"]:
            seed_content += "\n\n--- Planning diagnostics ---"
            if planning_context["warnings"]:
                seed_content += "\nWarnings:"
                for item in planning_context["warnings"]:
                    seed_content += f"\n  - {item}"
            if planning_context["failures"]:
                seed_content += "\nFailures:"
                for item in planning_context["failures"]:
                    seed_content += f"\n  - {item}"
            if planning_context["constraint_refs"]:
                seed_content += "\nConstraint refs: " + ", ".join(planning_context["constraint_refs"])
            if planning_context["responsibility_refs"]:
                seed_content += "\nResponsibility refs: " + ", ".join(planning_context["responsibility_refs"])

        seed_content += (
            "\n\nPlease review both the geometric outcome and the planning diagnostics. "
            "Call out whether any failure is fundamentally a planning violation, an execution failure, "
            "or a final validation mismatch."
        )
        return seed_content

    def _collect_planning_context(
        self,
        *,
        plan_artifact: PlanArtifact | None,
        spec_artifact: SpecArtifact | None,
        build_artifacts: list[BuildArtifact],
        assembly_artifacts: list[AssemblyArtifact],
        build_execution_plan: dict[str, Any],
        assembly_execution_plan: dict[str, Any],
    ) -> dict[str, list[str]]:
        warnings: list[str] = []
        failures: list[str] = []
        constraint_refs: list[str] = []
        responsibility_refs: list[str] = []

        if plan_artifact is not None:
            plan_structure_issues = validate_plan_structure(plan_artifact, spec_artifact)
            failures = _merge_unique(
                failures,
                [str(issue.get("summary", "")).strip() for issue in plan_structure_issues if str(issue.get("summary", "")).strip()],
            )

        for artifact in build_artifacts:
            warnings = _merge_unique(warnings, [str(item).strip() for item in artifact.planning_warnings if str(item).strip()])
            responsibility_refs = _merge_unique(
                responsibility_refs,
                [str(item).strip() for item in artifact.responsibility_refs if str(item).strip()],
            )
            constraint_refs = _merge_unique(
                constraint_refs,
                [str(item).strip() for item in artifact.constraint_refs if str(item).strip()],
            )

        for artifact in assembly_artifacts:
            warnings = _merge_unique(warnings, [str(item).strip() for item in artifact.planning_warnings if str(item).strip()])
            failures = _merge_unique(failures, [str(item).strip() for item in artifact.planning_failures if str(item).strip()])
            responsibility_refs = _merge_unique(
                responsibility_refs,
                [str(item).strip() for item in artifact.responsibility_refs if str(item).strip()],
            )
            constraint_refs = _merge_unique(
                constraint_refs,
                [str(item).strip() for item in artifact.constraint_refs if str(item).strip()],
            )
            for note in artifact.failure_notes:
                text = str(note).strip()
                if not text:
                    continue
                lowered = text.lower()
                if "ordering constraint" in lowered or "parent" in lowered:
                    failures = _merge_unique(failures, [text])
            if getattr(artifact, "skipped", False) and getattr(artifact, "unresolved_planning_gap", False):
                missing_fields = ", ".join(getattr(artifact, "missing_contract_fields", []) or []) or "unknown contract fields"
                failures = _merge_unique(
                    failures,
                    [f"Assembly step {artifact.step_index} was skipped due to unresolved contract fields: {missing_fields}."],
                )

        warnings, responsibility_refs, constraint_refs = self._merge_execution_plan_diagnostics(
            build_execution_plan,
            warnings,
            responsibility_refs,
            constraint_refs,
        )
        warnings, responsibility_refs, constraint_refs = self._merge_execution_plan_diagnostics(
            assembly_execution_plan,
            warnings,
            responsibility_refs,
            constraint_refs,
        )

        if plan_artifact:
            warnings = _merge_unique(
                warnings,
                [
                    f"Planning risk hotspot remains active: {self._summarize_planning_item(item)}"
                    for item in plan_artifact.risk_hotspots
                    if self._summarize_planning_item(item)
                ],
            )
            warnings = _merge_unique(
                warnings,
                [
                    f"Unresolved planning issue remains: {str(item).strip()}"
                    for item in plan_artifact.open_issues
                    if str(item).strip()
                ],
            )

        return {
            "warnings": warnings,
            "failures": failures,
            "constraint_refs": constraint_refs,
            "responsibility_refs": responsibility_refs,
        }

    def _summarize_planning_item(self, item: Any) -> str:
        if isinstance(item, dict):
            summary = str(item.get("summary", "")).strip()
            if summary:
                return summary
        return str(item).strip()

    def _merge_execution_plan_diagnostics(
        self,
        execution_plan: dict[str, Any],
        warnings: list[str],
        responsibility_refs: list[str],
        constraint_refs: list[str],
    ) -> tuple[list[str], list[str], list[str]]:
        if not isinstance(execution_plan, dict):
            return warnings, responsibility_refs, constraint_refs
        diagnostics = execution_plan.get("diagnostics", [])
        if not isinstance(diagnostics, list):
            return warnings, responsibility_refs, constraint_refs
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            summary = str(diagnostic.get("summary", "")).strip()
            if summary:
                warnings = _merge_unique(warnings, [summary])
            ref = str(diagnostic.get("responsibility_ref", "")).strip()
            if ref:
                responsibility_refs = _merge_unique(responsibility_refs, [ref])
            constraint_ref = str(diagnostic.get("constraint_ref", "")).strip()
            if constraint_ref:
                constraint_refs = _merge_unique(constraint_refs, [constraint_ref])
        return warnings, responsibility_refs, constraint_refs


def _merge_unique(existing: list[Any], incoming: list[Any]) -> list[str]:
    merged = [_normalize_merge_item(item) for item in existing]
    seen = {item for item in merged if item}
    for item in incoming:
        normalized = _normalize_merge_item(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    return merged


def _normalize_merge_item(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, (dict, list, tuple)):
        try:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(item).strip()
    return str(item).strip()
