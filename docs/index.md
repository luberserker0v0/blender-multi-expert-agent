# Documentation Index

This index is the entry point for the current project design and implementation notes.

Read this file first. It is intended to reduce unnecessary context loading by pointing readers only to the documents they need.

## Recommended Read Order

1. `readme_index.md`
   Use this when you want to know which README to open for each workspace area.
2. `engineering/srs.md`
   Use this when you want the current product scope, assumptions, and system requirements.
3. `system_architecture.md`
   Use this when you want the current runtime architecture and module boundaries.
4. `agent_orchestrator_multi_expert.md`
   Use this when you want the current AO-backed multi-expert runtime, role set, provisioning sequence, and source-of-truth assets.
5. `react_ui.md`
   Use this when you want the browser UI, bridge, and activity streaming flow.

## By Topic

### Product / Scope

- `engineering/srs.md`
  Current software requirements specification.
- `product_overview.md`
  Short project summary, current status, and terminology.

### Architecture / Runtime

- `system_architecture.md`
  Main system architecture, module responsibilities, and current design choices.
- `agent_orchestrator_multi_expert.md`
  Current Agent Orchestrator-backed multi-expert runtime and provisioning flow.
- `blender_build_capabilities.md`
  Manual capability manifest used by the builder agent and build-action validator.
- `blender_assembly_capabilities.md`
  Manual capability manifest used by Builder placement execution and validation.
- `runtime_loop.md`
  Historical runtime notes; use current code as source of truth.
- `multimodal_review_and_multiplicity_design.md`
  Design for LLM-reviewed process screenshots, repeated part instances such as multiple chair legs, and the future anchor-based assembly path.
- `modeling_orchestration_prompt_design.md`
  Design for improving task dispatch, geometry intent, screenshot review rubric, and modeling prompts for better Blender execution quality.
- `perception_and_yolo.md`
  Current perception design, YOLO output structure, and what the system can infer from it.
- `session_and_progress.md`
  Session model, progress file contract, and recovery-related TODO boundaries.
- `gui_prototype.md`
  Older `tkinter` GUI helper notes.
- `react_ui.md`
  Primary React + TypeScript + Tailwind CSS UI workspace, bridge flow, WebSocket Activity transport, reconnect behavior, and pending interaction UX.

### Blender / MCP

- `blender_mcp_integration.md`
  Actual MCP integration path, currently based on Blender-hosted stdio MCP plus socket-connected add-on execution.
- `blender_adapter.md`
  Agent-side `BlenderMcpAdapter` design and current method-to-tool mapping.
- `blender_mcp_api_draft.md`
  Earlier idealized API draft. Keep this for reference only; it is not the source of truth for current implementation.

### Task / Modeling State

- `task_object_table.md`
  Task-scoped object table design, cleanup policy, and why unrelated objects are deleted before modeling.

### Engineering / Process

- `readme_index.md`
  Index of README files and their intended scope.
- `engineering/tdd.md`
  Test strategy, current automated coverage, and near-term testing plan.
- `testing_strategy.md`
  Lightweight test inventory by layer and runtime target.
- `TODO.md`
  Open follow-up work that is not yet captured as implemented behavior.

## Source Of Truth Notes

- If a document conflicts with current code, the implementation under `src/` is the source of truth.
- `blender_mcp_api_draft.md` is explicitly a draft.
- `README.md` is for quick start and environment setup, not for full architecture detail.
