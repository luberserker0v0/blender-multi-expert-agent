# Modeling Orchestration And Prompt Design

## Goal

This document defines the next design pass for improving modeling quality.

The current runtime is now more robust against malformed LLM payloads and now supports:

- multimodal screenshot review for process images
- multi-view screenshot bundles
- step-by-step assembly review

However, the quality of Blender task execution is still weaker than the image quality of the screenshots.

The main issue is no longer just transport reliability. The next issue is orchestration quality:

- task decomposition is still too coarse
- repeated-part quantities are not yet operational
- prompt structure does not force enough geometric reasoning
- screenshot review instructions are not yet specific enough about what the LLM must judge

## Current Weaknesses

### 1. Task Dispatch Is Too Thin

The Agent currently asks the LLM to:

- split the object into parts
- define per-part primitive choice
- define target bbox, anchors, and structural notes

This is better than the earlier direct-transform workflow, but still leaves too much ambiguity in:

- quantity
- symmetry
- duplicated instances
- parent-child attachment sequence

Example problem:

- `chair_leg` may be planned as one logical part
- but the workflow does not yet guarantee `4` physical leg instances

### 2. Geometry Intent Is Not Explicit Enough

The LLM is still allowed to infer too much from sparse wording.

What the Agent really needs is not only:

- `preferred_primitive`
- `target_bbox`

It also needs:

- quantity
- symmetry class
- repetition policy
- parent attachment rule
- assembly anchors
- tolerance for deviation

### 3. Screenshot Review Is Better, But Still Generic

The LLM now receives real images plus viewpoint labels.

That solves the earlier problem where only `capture_path` was sent.

But the prompt still does not strongly separate:

- shape correctness
- size correctness
- attachment correctness
- duplicate consistency

In other words, the LLM can see more now, but the review rubric is still under-specified.

## Target Direction

### Principle 1

The Agent should ask the LLM for *structural intent* before asking for *execution actions*.

### Principle 2

The Agent should turn as much of the geometry plan as possible into deterministic execution logic.

### Principle 3

The LLM should review against explicit criteria, not vague "looks good" standards.

## Proposed Planning Stages

### Stage A: Object Decomposition

Input:

- task prompt
- user references

Output:

- logical part families
- repeated-part counts
- high-level assembly order

Required fields:

- `task_id`
- `title`
- `object_name`
- `description`
- `instance_count`
- `instance_generation_mode`

Example:

- `chair_seat`, `instance_count=1`
- `chair_leg`, `instance_count=4`
- `chair_backrest`, `instance_count=1`

### Stage B: Structural Spec

For each part family, request:

- `preferred_primitive`
- `target_bbox`
- `anchor_points`
- `structural_spec`
- `symmetry_group`
- `parent_task_id`
- `attach_to`
- `placement_notes`

The output should describe the intended geometry in a way the Agent can apply deterministically.

### Stage C: Execution Spec

Only after structural spec is stable should the Agent ask for:

- source mesh refinement viewpoint set
- repeated-part duplication policy
- assembly step ordering

This stage should not redefine shape semantics. It should only describe how to execute the plan.

## Proposed Part Review Rubric

Part review prompts should ask the LLM to judge in this order:

1. Is the silhouette correct for this part family
2. Is the current bounding box close to the target bbox
3. Are the visible anchors plausibly located
4. If this part will be duplicated, is it a good source mesh

The prompt should explicitly say:

- this review is for a single logical part family
- this mesh may become the source for duplicated instances
- prioritize geometric correctness over micro-detail

## Proposed Assembly Review Rubric

Assembly review prompts should ask the LLM to judge in this order:

1. Is the current step instance attached to the correct parent
2. Is the placement correct relative to the already assembled structure
3. Is the scale consistent with the other visible instances
4. If the instance belongs to a repeated family, is it symmetric or consistent with previous siblings

The prompt should explicitly mention:

- current step index
- current task id
- already assembled task ids
- remaining task ids
- all provided viewpoints

## Prompt Additions

### Planning Prompt Additions

Planning prompts should now require:

- explicit quantity
- whether a part is a repeated family
- whether one approved source mesh can be duplicated

Example:

- `Do not collapse repeated families into one unnamed mesh.`
- `If the object has four identical legs, return one logical task with instance_count=4 and duplicate_after_approval.`

### Review Prompt Additions

Review prompts should now require:

- explicit acknowledgement of provided viewpoints
- reasoning about bbox fit
- reasoning about role in assembly
- reasoning about duplication suitability

Example:

- `Image 1 is front view, image 2 is side view, image 3 is top view.`
- `This part will become the source mesh for repeated duplication.`
- `Use target_bbox and current_dimensions as first-class review criteria.`

## Agent Execution Improvements

### 1. Source Mesh Approval For Repeated Parts

For repeated families:

1. refine one source mesh
2. approve source mesh
3. duplicate after approval
4. assemble each instance separately

### 2. Deterministic Scale Recovery

When the LLM omits scale, the Agent should continue using:

- `current_dimensions`
- `target_bbox`

to recover deterministic scaling.

This is already partly implemented and should remain a core design rule.

### 3. Assembly State Should Stay Small But Specific

Each assembly review should include:

- current step metadata
- visible object states only
- current image bundle

It should not include unnecessary hidden future instances unless explicitly needed.

## Screenshot Requirements

### Part Review

Default bundle:

- primary viewpoint
- side
- top

### Assembly Review

Default bundle:

- front
- side
- top

### Future Extension

If a shape category needs it, the Agent may dynamically add:

- back
- left
- right

but the default prompt contract should stay stable.

## Recommended Next Implementation Order

1. make `instance_count` operational in the workflow
2. add `duplicate_after_approval` execution path
3. upgrade planning prompts to require quantity and duplication intent
4. add instance-aware assembly ordering
5. evolve from transform-only assembly to anchor-based placement

## Non-Goal

This design does not attempt to solve:

- high-fidelity mesh sculpting
- curved detail modeling
- material authoring

Its purpose is to improve:

- decomposition quality
- instance correctness
- prompt clarity
- screenshot review quality
