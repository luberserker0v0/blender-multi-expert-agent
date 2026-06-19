"""In-process multi-expert pipeline runner coordinated through Agent Orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def run_pipeline(
    task: str,
    session_id: str,
    *,
    use_blender_mcp: bool = False,
    blender_mcp_command: str = "uv",
    blender_mcp_args: list[str] | None = None,
    blender_mcp_cwd: str = "",
    blender_mcp_env: dict[str, str] | None = None,
    agent_orchestrator_base_url: str = "",
    agent_orchestrator_model: str = "",
    agent_orchestrator_conversation_id: str = "",
    agent_orchestrator_destroy_on_finish: bool = True,
    agent_orchestrator_timeout_seconds: int = 120,
    event_callback: Callable | None = None,
    event_buffer: Any | None = None,
) -> Any:
    from ai_3d_modeling_agent.blender.mcp_adapter import BlenderMcpAdapter
    from ai_3d_modeling_agent.blender.object_ops import SimulatedBlenderObjectOps
    from ai_3d_modeling_agent.execution.action_executor import ActionExecutor
    from ai_3d_modeling_agent.memory.session_paths import (
        ensure_session_runtime_dir,
        session_capture_dir,
        session_mcp_log_path,
    )
    from ai_3d_modeling_agent.memory.session_progress import SessionProgressStore
    from ai_3d_modeling_agent.multi_expert.pipeline.adapter import final_artifact_to_snapshot
    from ai_3d_modeling_agent.multi_expert.experts import (
        Builder,
        Designer,
        Inspector,
        Planner,
        Reviewer,
        Specifier,
    )
    from ai_3d_modeling_agent.multi_expert.pipeline.pipeline import Pipeline
    from ai_3d_modeling_agent.multi_expert.pipeline.registry import ExpertRegistry
    from ai_3d_modeling_agent.services.agent_orchestrator import (
        AgentOrchestratorClient,
        AgentOrchestratorConfig,
        AgentOrchestratorLlmAdapter,
        provision_agent_orchestrator,
    )
    from ai_3d_modeling_agent.schemas.modeling_plan import ModelingRequest
    from ai_3d_modeling_agent.schemas.session_progress import (
        LlmPromptEventRecord,
        MultiStageProgressSnapshot,
    )

    if not str(agent_orchestrator_base_url or "").strip():
        raise ValueError("agent_orchestrator_base_url is required for multi-expert pipeline runs")

    runtime_root = Path(__file__).resolve().parents[3] / "data" / "runtime"
    ensure_session_runtime_dir(runtime_root, session_id)
    progress_store = SessionProgressStore(runtime_root)
    llm_prompt_events: list[LlmPromptEventRecord] = []

    progress_snapshot = MultiStageProgressSnapshot(
        workflow_type="multi_stage_modeling",
        status="running",
        task=task,
        stage="design",
        stage_status="running",
        request=ModelingRequest(task_prompt=task, references=[]),
        required_objects=[],
        multi_expert_mode=True,
        llm_prompt_events=list(llm_prompt_events),
        stop_reason="",
        dnc_mode=False,
    )
    progress_store.write_multi_stage_snapshot(session_id, progress_snapshot)

    def prompt_observer(payload: dict[str, Any]) -> None:
        llm_prompt_events.append(
            LlmPromptEventRecord(
                event_id=f"me_llm_{len(llm_prompt_events) + 1:04d}",
                stage=str(payload.get("stage", "")),
                label=str(payload.get("label", "")),
                prompt_preview=str(payload.get("prompt_preview", "")),
                response_preview=str(payload.get("response_preview", "")),
                validation_error=str(payload.get("validation_error", "")),
                has_images=bool(payload.get("has_images", False)),
                image_count=int(payload.get("image_count", 0)),
            )
        )
        progress_snapshot.llm_prompt_events = list(llm_prompt_events)
        progress_store.write_multi_stage_snapshot(session_id, progress_snapshot)

    def progress_callback(phase: str, checkpoint: object) -> None:
        progress_snapshot.stage = phase
        progress_snapshot.stage_status = "running" if checkpoint == "start" else "completed"
        progress_snapshot.llm_prompt_events = list(llm_prompt_events)
        progress_store.write_multi_stage_snapshot(session_id, progress_snapshot)

    if use_blender_mcp and blender_mcp_command:
        from ai_3d_modeling_agent.services.mcp_client import McpClientConfig, SdkMCPClient

        client = SdkMCPClient(
            McpClientConfig(
                command=blender_mcp_command,
                args=blender_mcp_args or [],
                cwd=blender_mcp_cwd,
                env=blender_mcp_env or {},
                session_id=session_id,
                tool_call_log_path=str(session_mcp_log_path(runtime_root, session_id)),
            )
        )
        object_ops = BlenderMcpAdapter(
            client=client,
            session_id=session_id,
            capture_output_dir=session_capture_dir(runtime_root, session_id),
        )
    else:
        object_ops = SimulatedBlenderObjectOps()

    executor = ActionExecutor(object_ops)

    ao_client = AgentOrchestratorClient(
        AgentOrchestratorConfig(
            base_url=agent_orchestrator_base_url,
            model=agent_orchestrator_model,
            conversation_id=agent_orchestrator_conversation_id,
            destroy_on_finish=agent_orchestrator_destroy_on_finish,
            timeout_seconds=agent_orchestrator_timeout_seconds,
        )
    )
    ao_session = provision_agent_orchestrator(
        ao_client,
        repo_root=Path(__file__).resolve().parents[3],
    )
    llm_client = AgentOrchestratorLlmAdapter(
        ao_client,
        model=agent_orchestrator_model,
        prompt_observer=prompt_observer,
    )

    registry = ExpertRegistry()
    for cls in (Designer, Specifier, Planner, Reviewer, Builder, Inspector):
        registry.register(cls())

    try:
        pipeline = Pipeline(
            registry=registry,
            llm=llm_client,
            context={
                "session_id": session_id,
                "runtime_root": str(runtime_root),
                "task_prompt": task,
                "agent_orchestrator": {
                    "conversation_id": ao_session.conversation_id,
                    "skill_hashes": {},
                },
            },
            progress_callback=progress_callback,
            prompt_observer=prompt_observer,
            object_ops=object_ops,
            executor=executor,
            event_callback=event_callback,
            event_buffer=event_buffer,
        )

        final_artifact = pipeline.run(task)
        final_snapshot = final_artifact_to_snapshot(
            final_artifact,
            task_prompt=task,
            session_id=session_id,
        )
        final_snapshot.llm_prompt_events = list(llm_prompt_events)
        progress_store.write_multi_stage_snapshot(session_id, final_snapshot)
        return final_artifact
    finally:
        ao_client.close()
        if agent_orchestrator_destroy_on_finish:
            try:
                ao_client.delete(ao_session.conversation_id)
            except Exception:
                pass


def run_pipeline_from_settings(
    settings_path: str | Path,
    *,
    task: str | None = None,
    session_id: str | None = None,
    event_callback: Callable | None = None,
) -> Any:
    from ai_3d_modeling_agent.io.settings_loader import load_settings, settings_to_run_pipeline_kwargs

    settings = load_settings(settings_path)
    if task is not None:
        settings["task"] = task
    if session_id is not None:
        settings["session_id"] = session_id
    if event_callback is not None:
        settings["event_callback"] = event_callback

    kwargs = settings_to_run_pipeline_kwargs(settings)
    if not kwargs.get("task"):
        raise ValueError("task is required; provide it via --task or in the settings file")
    if not kwargs.get("session_id"):
        import time

        kwargs["session_id"] = f"cli-{int(time.time())}"

    return run_pipeline(**kwargs)
