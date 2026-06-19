# Session And Progress

## Session Model

The top-level session model is:

- one chat window corresponds to one `session-id`
- one `session-id` corresponds to one progress file
- repeated runs with the same `session-id` update the same progress file path

## Progress File Location

- `data/runtime/sessions/<session-id>.json`

## Current Stored Fields

The progress file currently stores:

- session id
- task
- current iteration
- max iterations
- required objects
- removed object names
- actions
- final gap report path
- final object scale
- stop reason
- reconnect TODO markers
- MCP TODO markers

For the newer multi-stage modeling workflow, the progress file now uses a more explicit GUI-oriented schema with:

- `workflow_type`
- `status`
- `stage`
- `stage_status`
- `request`
- `required_objects`
- `plan`
- `active_task_id`
- `completed_task_ids`
- `part_tasks`
- `assembly`
- `final_validation`
- `stop_reason`
- `max_part_refinement_rounds`
- `max_assembly_rounds`

### Multi-Stage Schema Intent

- `workflow_type`
  Distinguishes this file from the older MVP iteration loop. Current value: `multi_stage_modeling`.
- `status`
  Top-level run state such as `running`, `completed`, or `failed`.
- `stage`
  Current orchestration step such as `planning`, `part_refinement`, `assembly`, `final_validation`, or `completed`.
- `stage_status`
  Current stage health such as `running`, `completed`, or `failed`.
- `request`
  Original user request, including text and future image reference inputs.
- `plan`
  The structured decomposition returned by the planning layer.
- `part_tasks`
  One entry per modeling task, each with:
  `task_id`, `title`, `object_name`, `status`, `current_round`, `approved`, `hidden_after_approval`, and `rounds`.
- `part_tasks[].rounds`
  Per-round history with:
  `round_index`, `capture_path`, `viewpoint`, `approved`, `feedback_summary`, `context`, and `requested_action`.
- `assembly`
  Assembly-specific progress with:
  `status`, `current_round`, `approved`, `all_parts_visible`, `initial_placement_applied`, and `rounds`.
- `assembly.rounds`
  Per-round assembly review history with:
  `round_index`, `capture_path`, `approved`, `feedback_summary`, `context`, and `requested_actions`.
- `final_validation`
  Final YOLO-facing validation summary with:
  `status`, `capture_path`, `viewpoint`, `detected_parts`, `missing_critical_parts`, and `quantitative_metrics`.

## Stability Rule

The intended boundary is:

- pipelines may change their internal control flow
- GUI and CLI consumers should read the progress file through these stable top-level keys
- new optional fields may be added later, but existing keys should remain backward compatible once the GUI depends on them

## Purpose

This file is intended to support:

- runtime visibility
- session continuity
- future recovery logic
- debugging after a failed run

## Current Limitations

The current implementation does not yet restore a task from this file automatically.

That remains future work.
