# Archived Reference

This document is historical. It may describe removed runtime paths and must not
be used as active implementation guidance.

# Multimodal Review And Multiplicity Design

## Goal

This document defines the next-stage design for two missing capabilities in the current multi-stage modeling workflow:

- process screenshots must be reviewed by the LLM as real image inputs, not only as file paths
- one modeling task must be able to produce multiple physical instances, such as four chair legs

The intended boundary remains:

- intermediate part and assembly screenshots go to the LLM
- final product screenshots go to YOLO for validation

## Current Gap

The current implementation has these limitations:

- `review_part()` and `review_assembly()` only pass `capture_path` as text to the endpoint-backed coordinator
- the OpenAI-compatible endpoint client currently sends text-only chat completion payloads
- a `ModelingTask` still maps to one `object_name`, which means one task produces one mesh instance
- `TaskObjectSpec.allowed_count` exists but is not enforced by the multi-stage pipeline
- assembly is now step-by-step, but still assumes one object per task

In practice, this means:

- the LLM is not really seeing the screenshots yet
- the LLM cannot reliably reason about view direction from image pixels
- a task like `chair_leg` still yields one leg instead of four

## Target Design

### Review Responsibility Split

- `LLM`
  Reviews in-progress screenshots during:
  - part refinement
  - step-by-step assembly
- `YOLO`
  Reviews final assembled product screenshots after LLM assembly approval

### New Modeling Concepts

- `part task`
  Describes one logical part family such as `chair_leg`
- `instance plan`
  Describes how many physical instances of that part family must exist
- `capture bundle`
  Describes one or more screenshots plus viewpoint metadata sent to the LLM

## Proposed Schema Changes

### ModelingTask

Add the following fields to `ModelingTask`:

- `instance_count: int`
  Number of physical instances required for this task
- `instance_naming_pattern: str`
  Example: `chair_leg_{index}`
- `instance_generation_mode: str`
  One of:
  - `independent`
  - `duplicate_after_approval`
- `review_viewpoints: List[str]`
  Example:
  - part: `["front", "side", "top"]`
  - assembly: inherited from assembly review bundle

Expected behavior:

- `independent`
  Use when each instance may differ materially
- `duplicate_after_approval`
  Use when one approved source mesh can be copied into multiple instances, such as repeated legs

### TaskObjectSpec

Keep `allowed_count`, but make it operationally meaningful:

- `allowed_count` must match or exceed `instance_count`
- `creation_policy=duplicate_from_source` becomes the preferred mode for repeated parts

### Session Progress

Extend progress with instance-level visibility:

- per part task:
  - `instance_count`
  - `approved_source_object_name`
  - `instance_object_names`
- per assembly round:
  - `assembly_step_index`
  - `instance_name`
  - `viewpoints`
  - `capture_paths`

## Screenshot Design

### Naming Convention

All captures should use one stable format.

#### Part Review

```text
{session}__part__{task_id}__instance_{nn}__round_{nn}__{viewpoint}.png
```

Example:

```text
chair_demo__part__chair_leg__instance_01__round_02__side.png
```

#### Assembly Review

```text
{session}__assembly__step_{nn}__{task_id}__instance_{nn}__round_{nn}__{viewpoint}.png
```

Example:

```text
chair_demo__assembly__step_03__chair_leg__instance_02__round_01__front.png
```

#### Final Validation

```text
{session}__final__validation__{viewpoint}.png
```

### Capture Bundle

Each review request to the LLM should send:

- one or more image inputs
- explicit viewpoint labels
- explicit review purpose

Example part review bundle:

- `front`
- `side`
- `top`

Example assembly review bundle:

- `front`
- `side`
- `top`

## Multimodal LLM Review Design

### Service Layer

The endpoint client should gain a multimodal request path in addition to text-only chat:

- `create_multimodal_chat_completion(...)`

Each user message item should be able to include:

- text
- image reference

For local files, the client should support one of these strategies:

1. base64 `data:` URL image input
2. OpenAI-compatible `image_url` content item with `data:` payload

The exact wire format depends on the local endpoint, but the internal client interface should not.

### Coordinator API

Replace single-image path prompts with structured review bundles:

- `review_part(..., review_bundle, object_state)`
- `review_assembly(..., review_bundle, object_states, assembly_state)`

Where `review_bundle` contains:

- `captures`
  - `path`
  - `viewpoint`
  - `stage`
  - `task_id`
  - `instance_name`

### Prompt Contract

Every review prompt should explicitly say:

- what the target object or instance is
- what each image viewpoint represents
- whether the review is for a single part or an assembly step
- what actions are legal

Example review framing:

- `Image 1 is the front orthographic view of chair_leg_02`
- `Image 2 is the side orthographic view of chair_leg_02`
- `Image 3 is the top orthographic view of chair_leg_02`

This removes ambiguity that currently exists when only a file path is passed.

## Multiplicity Design

### Source-Mesh Then Duplicate

For repeated parts such as chair legs, the preferred workflow is:

1. LLM creates one logical task for the repeated family
   Example:
   - `chair_leg`
2. LLM sets:
   - `instance_count=4`
   - `instance_generation_mode=duplicate_after_approval`
3. Agent models and refines one source mesh
4. Once approved, Agent duplicates the source mesh into:
   - `chair_leg_01`
   - `chair_leg_02`
   - `chair_leg_03`
   - `chair_leg_04`
5. Agent assembles each duplicate one step at a time

This design is better than making the LLM refine four legs independently because:

- geometry consistency is higher
- refinement cost is lower
- assembly debugging becomes clearer

### Assembly Sequence

Assembly should proceed in deterministic steps:

1. reveal base/root part
   Example:
   - `chair_seat`
2. capture and optionally confirm base placement
3. reveal and place first dependent instance
   Example:
   - `chair_leg_01`
4. capture bundle and ask LLM for feedback
5. apply edits until approved
6. continue with next instance

For a chair, one likely order is:

1. `chair_seat`
2. `chair_leg_01`
3. `chair_leg_02`
4. `chair_leg_03`
5. `chair_leg_04`
6. `chair_backrest`

The order should be computed from:

- `structural_spec.parent_task_id`
- root-part priority
- optional explicit `assembly_order`

## Anchor-Based Assembly Direction

Multiplicity becomes much easier once assembly is anchor-based.

Each instance should be placeable by:

- source object anchor
- parent object anchor
- optional offset

Example:

- `chair_leg_01.top_anchor -> chair_seat.front_left_leg_anchor`

This is a better long-term design than absolute transforms because:

- repeated parts become naturally expressible
- changes to seat size propagate more cleanly
- LLM can reason in semantic placement language instead of raw XYZ guesses

## Implementation Phases

### Phase 1

- add multimodal client path for LLM review
- send part review images as real image content
- send explicit viewpoint labels

### Phase 2

- add `instance_count`
- add source-mesh duplication workflow
- make `allowed_count` operational

### Phase 3

- add multi-view capture bundles for assembly review
- review assembly with `front + side + top`

### Phase 4

- replace absolute duplicate placement with anchor-based assembly solver

## Non-Goals For This Phase

- replacing YOLO with LLM for final validation
- letting YOLO drive part refinement
- full Blender rigging or articulated constraints

## Suggested First Implementation Order

1. real multimodal LLM screenshot review
2. repeated-part source mesh duplication
3. instance-aware progress schema
4. anchor-based assembly
