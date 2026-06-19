# TODO

Open follow-up work for the single executable multi-expert pipeline.

## Multi-Expert Pipeline Quality

- Verify Markdown-first Design, Spec, Plan, Todo, and Build Log quality end to end with AO.
- Add tests for malformed Builder Markdown intent, unsupported intent, blocked todo handling, and retry routing.
- Wire Builder screenshot capture paths into `BuildArtifact.capture_paths` and placement review records.
- Decide how often Build needs targeted correction meetings after Builder reports blocked or unsupported capability.
- Validate Reviewer challenge / veto behavior and make termination policy respond to explicit blocking feedback.

## Checkpoint / Resume

- Persist enough phase metadata to resume after process interruption.
- Add last completed phase, AO conversation id, last AO message id, current todo, and resumable artifact references to progress/checkpoint state.
- Test resume after interruption at each phase boundary.

## Blender MCP / Runtime

- Keep Blender MCP as the primary live backend for object operations.
- Verify `get_context`, primitive creation, transforms, duplication, visibility, and capture tools against the adapter.
- Handle temporarily unavailable MCP or AO service states without losing session progress.

## UI Progress

- Keep the existing `multi_stage_modeling` wire format stable while the backend runs only multi-expert.
- Ensure `multi_expert_mode` is always true in backend snapshots and frontend normalization.
- Keep Activity, Runtime Log, and Inspector views aligned with meeting events and progress snapshots.
