# System Architecture

## Current High-Level Architecture

The system is currently organized into these major layers:

- `tasks`
  Loads task-specific checklist data and builds the task object table.
- `schemas`
  Defines structured state contracts such as actions, gap reports, target checklist data, and task object specs.
- `blender`
  Contains Blender-facing object operations, simulated backend, context reader, and MCP-backed adapter.
- `perception`
  Defines perception interfaces plus mock and YOLO integration paths.
- `analysis`
  Builds the gap report from Blender context and perception results.
- `decision`
  Chooses the next action using rule-based or endpoint-backed LLM logic.
- `execution`
  Applies actions through the selected Blender object operations backend.
- `memory`
  Persists session progress.
- `output`
  Streams Agent progress back to the user.
- `services`
  Contains infrastructure clients such as the LLM endpoint client and MCP client.
- `pipelines`
  Orchestrates the full runtime loop.

## Current Runtime Backends

There are currently two Blender execution backends:

- simulated backend
  Uses in-memory object state for fast MVP validation and automated tests.
- MCP-backed backend
  Uses `SdkClient` plus `BlenderAdapter` to drive a live Blender instance.

The Blender operation layer now also exposes higher-level object controls needed by the staged modeling loop:

- primitive creation by primitive type
- active-object selection
- object hiding / unhiding
- absolute move and rotation controls
- targeted part capture before final assembly

## Current Decision Backends

- `RuleDecisionEngine`
  Default path for the MVP.
- `EndpointLlmDecisionEngine`
  Experimental path using an OpenAI-compatible endpoint such as `llama-server`.

## Current Perception Backends

- `MockPerceptionProvider`
  Default path for the MVP loop.
- `YoloPerceptionProvider`
  Real perception path using a local YOLO model and captured image input.

The current YOLO-backed perception can preserve:

- detected part names
- detection confidence
- bounding boxes
- normalized detection centers
- coarse bbox-derived size metrics

## Planned Extension

The current architecture will be extended with two new runtime responsibilities:

- multimodal LLM review transport for in-progress Blender screenshots
- repeated-part instance orchestration for tasks that require more than one physical mesh instance

This design is documented in:

- `multimodal_review_and_multiplicity_design.md`

## Design Boundaries

- the Agent is the orchestration layer
- Blender hosts the first  server
- the Agent acts as the MCP client
- LLM access remains endpoint-based for now
- perception and decision are intentionally abstracted so they can evolve independently
- part planning, part review, and assembly review are now separated from the older single-step decision loop

## Source Files

- `src/ai_3d_modeling_agent/pipelines/mvp_loop.py`
- `src/ai_3d_modeling_agent/blender/mcp_adapter.py`
- `src/ai_3d_modeling_agent/services/mcp_client.py`
- `src/ai_3d_modeling_agent/services/llm_endpoint.py`
