"""Pipeline orchestrator — coordinates all 6 phases sequentially.

Each phase produces a typed artifact that becomes input to the next phase.
Artifact flow: Design → Spec → Plan → Build → Assemble → Validate → Final.

Error handling: if any phase fails, the pipeline continues best-effort
through remaining phases and reports the overall status as DEGRADED or
PARTIAL rather than aborting.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import logging

from ai_3d_modeling_agent.multi_expert.artifacts import (
    AssemblyArtifact,
    BuildArtifact,
    DesignArtifact,
    FinalArtifact,
    PipelineStatus,
    PlanArtifact,
    SpecArtifact,
    ValidationArtifact,
)
from ai_3d_modeling_agent.multi_expert.core.meeting import MEETING_SCHEMA_VERSION
from ai_3d_modeling_agent.multi_expert.core.planning import (
    normalize_assembly_execution_plan,
    normalize_build_execution_plan,
)
from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry
from ai_3d_modeling_agent.multi_expert.pipeline.rejection import (
    CorrectionRequest,
    Rejection,
    RejectionReason,
)


class Pipeline:
    """Orchestrates the complete multi-expert pipeline through 6 sequential phases.

    Each phase produces a typed artifact that becomes input to the next phase.
    Artifact flow: Design → Spec → Plan → Build → Assemble → Validate → Final.
    """

    def __init__(
        self,
        registry: ExpertRegistry,
        llm: Any,
        context: Any | None = None,
        progress_callback: Callable | None = None,
        prompt_observer: Callable | None = None,
        object_ops: Any | None = None,
        executor: Any | None = None,
        event_callback: Callable | None = None,
        event_buffer: Any | None = None,
    ) -> None:
        """Initialize pipeline with expert registry and shared resources.

        Parameters
        ----------
        registry:
            Expert registry providing access to domain experts.
        llm:
            LLM interface used across all phases.
        context:
            Shared context dict passed to each phase. Defaults to empty dict.
        progress_callback:
            Optional callback invoked as ``progress_callback(phase, checkpoint)``
            at start and end of each pipeline phase.
        prompt_observer:
            Optional callback invoked as ``prompt_observer(payload)`` before each
            LLM-driven phase, receiving a dict with phase metadata.
        object_ops:
            BlenderObjectOps instance for creating geometry in Build/Assemble.
        executor:
            ActionExecutor instance for executing Blender transform actions.
        event_callback:
            Optional callback invoked as ``event_callback(event_dict)`` for
            every meeting event. Used for real-time WebSocket push.
        event_buffer:
            Optional BufferedWriter for persisting meeting events to disk.
        """
        self.registry = registry
        self.llm = llm
        self.context = context or {}
        self._progress_callback = progress_callback
        self._prompt_observer = prompt_observer
        self.object_ops = object_ops
        self.executor = executor
        self._event_callback = event_callback
        self._event_buffer = event_buffer
        self._phase_start_times: dict[str, float] = {}
        self._phase_rounds: dict[str, int] = {}
        self._event_counter: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit_progress(self, phase: str, checkpoint: str) -> None:
        """Invoke progress_callback if one was provided."""
        if self._progress_callback is not None:
            try:
                self._progress_callback(phase, checkpoint)
            except Exception:
                pass  # callback failure must not crash the pipeline

    def _observe_prompt(self, payload: dict) -> None:
        """Forward a prompt-observation payload to prompt_observer."""
        if self._prompt_observer is not None:
            try:
                self._prompt_observer(payload)
            except Exception:
                pass  # callback failure must not crash the pipeline

    def _emit_event(self, phase: str, kind: str, message: str, **extra: Any) -> None:
        """Emit a meeting event for real-time push + persistence.

        Parameters
        ----------
        phase:
            Phase name (e.g. "design", "build").
        kind:
            Event kind (e.g. "phase_open", "proposal", "build_step").
        message:
            Human-readable event description.
        **extra:
            Additional fields (speaker, turn, content_preview, etc.).
        """
        # Track phase timing
        if kind in {"phase_start", "phase_open"}:
            self._phase_start_times[phase] = time.time()
        if kind in {"phase_end", "phase_close"} and phase in self._phase_start_times:
            extra.setdefault("duration_seconds", time.time() - self._phase_start_times[phase])
        if "rounds" in extra:
            self._phase_rounds[phase] = extra["rounds"]
        elif kind in {"phase_end", "phase_close"} and phase in self._phase_rounds:
            extra.setdefault("rounds", self._phase_rounds[phase])

        role_defaults = {
            "proposal": ("owner", "Agent"),
            "challenge": ("reviewer", "Reviewer"),
            "response": ("owner", "Agent"),
            "resolution": ("moderator", "Moderator"),
            "phase_open": ("moderator", "Moderator"),
            "phase_close": ("moderator", "Moderator"),
            "build_step": ("builder", "Builder"),
            "assemble_step": ("builder", "Builder"),
            "validation_result": ("validator", "Validator"),
        }
        default_role, default_speaker = role_defaults.get(kind, ("system", "System"))
        event = {
            "schema_version": MEETING_SCHEMA_VERSION,
            "event_id": f"{phase}:{kind}:{int(time.time() * 1000)}:{self._event_counter}",
            "phase": phase,
            "kind": kind,
            "message": message,
            "speaker": extra.get("speaker", default_speaker),
            "role": extra.get("role", default_role),
            "round": int(extra.get("round", extra.get("turn", 0)) or 0),
            "summary": str(extra.get("summary", message)),
            "full_content": str(extra.get("full_content", message)),
            "timestamp": str(extra.get("timestamp", time.strftime("%H:%M"))),
            **extra,
        }
        self._event_counter += 1
        # 1. Real-time WebSocket push
        if self._event_callback is not None:
            try:
                self._safe_print(f"[PIPELINE] Emitting event: {phase}/{kind}")
                self._event_callback(event)
            except Exception:
                pass
        # 2. Runtime log
        self._safe_print(f"[{phase}] {message}")
        # 3. Buffer for persistence
        if self._event_buffer is not None:
            self._event_buffer.append(event)

    @staticmethod
    def _safe_print(message: str) -> None:
        try:
            print(message, flush=True)
        except OSError:
            pass

    def _flush_events(self) -> None:
        """Flush event buffer to disk (called at phase boundaries)."""
        if self._event_buffer is not None:
            self._event_buffer.flush()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task_prompt: str) -> FinalArtifact:
        """Run ALL 6 phases sequentially and return the final result.

        Steps
        -----
        1. DesignPhase   → DesignArtifact
        2. SpecPhase     → SpecArtifact
        3. PlanPhase     → PlanArtifact
        4. BuildPhase    → list[BuildArtifact]   (converted to dict)
        5. BuilderExecutionPhase → list[AssemblyArtifact]
        6. ValidatePhase → ValidationArtifact
        7. Aggregate into FinalArtifact

        Error handling
        --------------
        If any phase fails, its status is set to FAILED and an empty/default
        artifact is used in its place. Remaining phases still execute. The
        overall status is set to DEGRADED if any phase failed, PARTIAL if all
        phases had issues, or SUCCESS otherwise.

        Parameters
        ----------
        task_prompt:
            The original task prompt that initiated the pipeline.

        Returns
        -------
        FinalArtifact
            Aggregated result of all phases with overall status.
        """
        # Lazy imports to avoid circular import:
        # phases → pipeline.registry → pipeline.__init__ → pipeline.py → phases
        from ai_3d_modeling_agent.multi_expert.phases import (
            BuildPhase,
            BuilderExecutionPhase,
            DesignPhase,
            PlanPhase,
            SpecPhase,
            ValidatePhase,
        )
        from ai_3d_modeling_agent.schemas.part import PartFamily

        design_phase = DesignPhase()
        spec_phase = SpecPhase()
        plan_phase = PlanPhase()
        build_phase = BuildPhase()
        assemble_phase = BuilderExecutionPhase()
        validate_phase = ValidatePhase()
        # Markdown-first runtime asks AO/Builder for one-step Markdown intent
        # only during AO-backed runs. Python still maps, executes, and validates
        # the resulting Blender actions.
        ao_context = self.context.get("agent_orchestrator") if isinstance(self.context, dict) else None
        action_llm = self.llm if isinstance(ao_context, dict) and ao_context.get("conversation_id") else None

        # Inject event emitter into phases
        for p in (design_phase, spec_phase, plan_phase,
                  build_phase, assemble_phase, validate_phase):
            p._emit_event = self._emit_event  # type: ignore[attr-defined]

        statuses: dict[str, PipelineStatus] = {}
        degraded: list[str] = []
        revision_count: int = 0

        # ------------------------------------------------------------------
        # Phase 1: Design
        # ------------------------------------------------------------------
        self._emit_progress("design", "start")
        self._observe_prompt({
            "event_id": "design_start",
            "stage": "design",
            "label": "design phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            design_result = design_phase.run(
                self.registry, self.context, self.llm,
                task_prompt=task_prompt,
            )
            statuses["design"] = PipelineStatus.SUCCESS
        except Exception as exc:
            logging.getLogger(__name__).exception("Design phase failed")
            statuses["design"] = PipelineStatus.FAILED
            degraded.append("design")
            design_result = DesignArtifact(task_prompt=task_prompt)
        self._emit_progress("design", "end")
        self._flush_events()

        # Ensure design_result is always a DesignArtifact.
        if not isinstance(design_result, DesignArtifact):
            design_result = DesignArtifact(task_prompt=task_prompt)
        logging.getLogger(__name__).info("AAA")
        # ------------------------------------------------------------------
        # Phase 2: Spec
        # ------------------------------------------------------------------
        self._emit_progress("spec", "start")
        self._observe_prompt({
            "event_id": "spec_start",
            "stage": "spec",
            "label": "spec phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            spec_result = spec_phase.run(
                self.registry, self.context, self.llm, design_result
            )
            statuses["spec"] = PipelineStatus.SUCCESS
        except Exception:
            logging.getLogger(__name__).exception("Spec phase failed")
            statuses["spec"] = PipelineStatus.FAILED
            degraded.append("spec")
            spec_result = SpecArtifact()
        self._emit_progress("spec", "end")
        self._flush_events()

        if not isinstance(spec_result, SpecArtifact):
            spec_result = SpecArtifact()
        spec_revision_notes = [str(note) for note in list(getattr(spec_result, "failure_notes", []) or []) if str(note).strip()]
        if spec_revision_notes and action_llm is not None:
            statuses["spec"] = PipelineStatus.FAILED
            statuses.setdefault("plan", PipelineStatus.FAILED)
            statuses.setdefault("build", PipelineStatus.FAILED)
            statuses.setdefault("assemble", PipelineStatus.FAILED)
            statuses.setdefault("validate", PipelineStatus.FAILED)
            degraded.append("spec")
            return FinalArtifact(
                task_prompt=task_prompt,
                design=design_result,
                specs=spec_result,
                plan=PlanArtifact(failure_notes=spec_revision_notes),
                build_results={},
                assembly_results=[],
                validation=ValidationArtifact(passed=False, errors=spec_revision_notes),
                status=PipelineStatus.FAILED,
                degraded_parts=degraded,
                phase_statuses=statuses,
                revision_count=revision_count,
            )

        # ------------------------------------------------------------------
        # Phase 3: Plan
        # ------------------------------------------------------------------
        self._emit_progress("plan", "start")
        self._observe_prompt({
            "event_id": "plan_start",
            "stage": "plan",
            "label": "plan phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            part_families: list[PartFamily] = [
                PartFamily.from_dict(p) for p in (design_result.parts or [])
            ]
            plan_result = plan_phase.run(
                self.registry,
                self.context,
                self.llm,
                spec_result,
                part_families,
            )
            statuses["plan"] = PipelineStatus.SUCCESS
        except Exception as exc:
            logging.getLogger(__name__).exception("Plan phase failed")
            statuses["plan"] = PipelineStatus.FAILED
            degraded.append("plan")
            failure_notes = [f"Plan phase failed: {exc}"]
            plan_result = PlanArtifact(failure_notes=failure_notes)
            self._emit_progress("plan", "end")
            self._flush_events()
            if action_llm is not None:
                statuses.setdefault("build", PipelineStatus.FAILED)
                statuses.setdefault("assemble", PipelineStatus.FAILED)
                statuses.setdefault("validate", PipelineStatus.FAILED)
                return FinalArtifact(
                    task_prompt=task_prompt,
                    design=design_result,
                    specs=spec_result,
                    plan=plan_result,
                    build_results={},
                    assembly_results=[],
                    validation=ValidationArtifact(passed=False, errors=failure_notes),
                    status=PipelineStatus.FAILED,
                    degraded_parts=degraded,
                    phase_statuses=statuses,
                    revision_count=revision_count,
                )
        else:
            self._emit_progress("plan", "end")
            self._flush_events()

        if not isinstance(plan_result, PlanArtifact):
            plan_result = PlanArtifact()
        plan_revision_notes = [str(note) for note in list(getattr(plan_result, "failure_notes", []) or []) if str(note).strip()]
        if plan_revision_notes and action_llm is not None:
            statuses["plan"] = PipelineStatus.FAILED
            statuses.setdefault("build", PipelineStatus.FAILED)
            statuses.setdefault("assemble", PipelineStatus.FAILED)
            statuses.setdefault("validate", PipelineStatus.FAILED)
            degraded.append("plan")
            return FinalArtifact(
                task_prompt=task_prompt,
                design=design_result,
                specs=spec_result,
                plan=plan_result,
                build_results={},
                assembly_results=[],
                validation=ValidationArtifact(passed=False, errors=plan_revision_notes),
                status=PipelineStatus.FAILED,
                degraded_parts=degraded,
                phase_statuses=statuses,
                revision_count=revision_count,
            )

        # ------------------------------------------------------------------
        # Phase 4: Build
        # ------------------------------------------------------------------
        self._emit_progress("build", "start")
        self._observe_prompt({
            "event_id": "build_start",
            "stage": "build",
            "label": "build phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            build_results_list = build_phase.run(
                plan_artifact=plan_result,
                spec_artifact=spec_result,
                context=self.context,
                object_ops=self.object_ops,
                executor=self.executor,
                llm=action_llm,
            )
            statuses["build"] = PipelineStatus.SUCCESS
        except Exception:
            logging.getLogger(__name__).exception("Build phase failed")
            statuses["build"] = PipelineStatus.FAILED
            degraded.append("build")
            build_results_list = []
        self._emit_progress("build", "end")
        self._flush_events()

        if not isinstance(build_results_list, list):
            build_results_list = []

        # Convert list -> dict for the FinalArtifact.
        build_results_dict: dict[str, BuildArtifact] = {
            b.part_name: b for b in build_results_list
        }
        if not build_results_list and action_llm is not None:
            reason = "Build phase produced no Blender artifacts; validation was not run."
            statuses["build"] = PipelineStatus.FAILED
            statuses.setdefault("assemble", PipelineStatus.FAILED)
            statuses.setdefault("validate", PipelineStatus.FAILED)
            if "build" not in degraded:
                degraded.append("build")
            return FinalArtifact(
                task_prompt=task_prompt,
                design=design_result,
                specs=spec_result,
                plan=plan_result,
                build_results={},
                assembly_results=[],
                validation=ValidationArtifact(passed=False, errors=[reason]),
                status=PipelineStatus.FAILED,
                degraded_parts=degraded,
                phase_statuses=statuses,
                revision_count=revision_count,
            )
        blocking_builds = [
            b for b in build_results_list
            if getattr(b, "status", "") in {"blocked", "needs_revision", "failed"}
        ]
        if blocking_builds and action_llm is not None:
            statuses["build"] = PipelineStatus.FAILED
            statuses.setdefault("assemble", PipelineStatus.FAILED)
            statuses.setdefault("validate", PipelineStatus.FAILED)
            degraded.append("build")
            return FinalArtifact(
                task_prompt=task_prompt,
                design=design_result,
                specs=spec_result,
                plan=plan_result,
                build_results=build_results_dict,
                assembly_results=[],
                validation=ValidationArtifact(
                    passed=False,
                    errors=[
                        note
                        for artifact in blocking_builds
                        for note in list(getattr(artifact, "failure_notes", []) or [])
                    ],
                ),
                status=PipelineStatus.FAILED,
                degraded_parts=degraded,
                phase_statuses=statuses,
                revision_count=revision_count,
            )

        # ------------------------------------------------------------------
        # Phase 5: Assemble
        # ------------------------------------------------------------------
        self._emit_progress("assemble", "start")
        self._observe_prompt({
            "event_id": "assemble_start",
            "stage": "assemble",
            "label": "assemble phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            assembly_results = assemble_phase.run(
                build_artifacts=build_results_list,
                plan_artifact=plan_result,
                spec_artifact=spec_result,
                context=self.context,
                object_ops=self.object_ops,
                executor=self.executor,
                llm=action_llm,
            )
            statuses["assemble"] = PipelineStatus.SUCCESS
        except Exception:
            logging.getLogger(__name__).exception("Assemble phase failed")
            statuses["assemble"] = PipelineStatus.FAILED
            degraded.append("assemble")
            assembly_results = []
        self._emit_progress("assemble", "end")
        self._flush_events()

        if not isinstance(assembly_results, list):
            assembly_results = []
        blocking_assembly = [
            artifact for artifact in assembly_results
            if str(getattr(artifact, "review_verdict", "") or "") in {"blocked", "needs_revision", "failed"}
            or bool(getattr(artifact, "failure_notes", []))
        ]
        if blocking_assembly and action_llm is not None:
            statuses["assemble"] = PipelineStatus.FAILED
            statuses.setdefault("validate", PipelineStatus.FAILED)
            degraded.append("assemble")
            return FinalArtifact(
                task_prompt=task_prompt,
                design=design_result,
                specs=spec_result,
                plan=plan_result,
                build_results=build_results_dict,
                assembly_results=assembly_results,
                validation=ValidationArtifact(
                    passed=False,
                    errors=[
                        note
                        for artifact in blocking_assembly
                        for note in list(getattr(artifact, "failure_notes", []) or [])
                    ],
                ),
                status=PipelineStatus.FAILED,
                degraded_parts=degraded,
                phase_statuses=statuses,
                revision_count=revision_count,
            )

        # ------------------------------------------------------------------
        # Phase 6: Validate
        # ------------------------------------------------------------------
        self._emit_progress("validate", "start")
        self._observe_prompt({
            "event_id": "validate_start",
            "stage": "validate",
            "label": "validate phase",
            "prompt_preview": f"Task: {task_prompt[:200]}",
            "response_preview": "",
            "validation_error": "",
            "has_images": False,
            "image_count": 0,
        })
        try:
            build_execution_plan = normalize_build_execution_plan(plan_result, spec_result).to_dict()
            assembly_execution_plan = normalize_assembly_execution_plan(plan_result, spec_result).to_dict()
            validation_result = validate_phase.run(
                self.registry,
                self.context,
                self.llm,
                spec_result,
                assembly_results,
                build_artifacts=build_results_list,
                plan_artifact=plan_result,
                build_execution_plan=build_execution_plan,
                assembly_execution_plan=assembly_execution_plan,
                object_ops=self.object_ops,
            )
            statuses["validate"] = PipelineStatus.SUCCESS
        except Exception:
            logging.getLogger(__name__).exception("Validate phase failed")
            statuses["validate"] = PipelineStatus.FAILED
            degraded.append("validate")
            validation_result = ValidationArtifact()
        self._emit_progress("validate", "end")
        self._flush_events()

        if not isinstance(validation_result, ValidationArtifact):
            validation_result = ValidationArtifact()
        if not bool(getattr(validation_result, "passed", False)):
            statuses["validate"] = PipelineStatus.FAILED
            if "validate" not in degraded:
                degraded.append("validate")

        # ------------------------------------------------------------------
        # Compute overall status
        # ------------------------------------------------------------------
        if all(s == PipelineStatus.SUCCESS for s in statuses.values()):
            overall = PipelineStatus.SUCCESS
        elif any(s == PipelineStatus.FAILED for s in statuses.values()):
            overall = PipelineStatus.DEGRADED
        else:
            overall = PipelineStatus.PARTIAL

        return FinalArtifact(
            task_prompt=task_prompt,
            design=design_result,
            specs=spec_result,
            plan=plan_result,
            build_results=build_results_dict,
            assembly_results=assembly_results,
            validation=validation_result,
            status=overall,
            degraded_parts=degraded,
            phase_statuses=statuses,
            revision_count=revision_count,
        )

    def run_phase(self, phase: Any, **kwargs: Any) -> Any:
        """Run a single phase with error handling.

        Parameters
        ----------
        phase:
            The phase instance to run (e.g. ``self._design_phase``).
        **kwargs:
            Keyword arguments forwarded to the phase's ``run()`` method.

        Returns
        -------
        Any
            The artifact produced by the phase, or ``None`` if the phase
            raised an exception.
        """
        try:
            return phase.run(**kwargs)
        except Exception:
            return None

    def handle_rejection(self, rejection: Rejection) -> CorrectionRequest:
        """Route a rejection to the appropriate expert for correction.

        Routing table (deterministic, no LLM):
        - UNSUPPORTED_PRIMITIVE/OPERATION/MATERIAL/INSTANCE_LIMIT → Designer
        - UNSUPPORTED_TRANSFORM/DIMENSION_OUT_OF_RANGE → Specifier
        - EXECUTION_FAILURE → Retry same executor (transient)

        Parameters
        ----------
        rejection:
            The rejection to route.

        Returns
        -------
        CorrectionRequest
            A correction request with the suggested fix target.
        """
        routing: dict[RejectionReason, str] = {
            RejectionReason.UNSUPPORTED_PRIMITIVE: "designer",
            RejectionReason.UNSUPPORTED_OPERATION: "designer",
            RejectionReason.UNSUPPORTED_MATERIAL: "designer",
            RejectionReason.INSTANCE_LIMIT_EXCEEDED: "designer",
            RejectionReason.UNSUPPORTED_TRANSFORM: "specifier",
            RejectionReason.DIMENSION_OUT_OF_RANGE: "specifier",
            RejectionReason.EXECUTION_FAILURE: "retry",
        }
        target = routing.get(rejection.reason, "designer")
        return CorrectionRequest(
            rejection=rejection,
            current_artifact=None,
            suggested_fix=target,
        )
