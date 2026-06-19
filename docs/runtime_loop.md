# Runtime Loop

## Current Loop Sequence

The current MVP loop performs these steps:

1. load the target checklist
2. build the task object table
3. remove unrelated objects from the scene
4. read current Blender context
5. run perception
6. build the gap report
7. persist the gap report
8. persist session progress
9. decide the next action
10. execute the action
11. repeat until `finish` or max iterations

## Scene Cleanup

Before each iteration, the loop removes objects that are not listed in the task object table.

This is important because:

- unrelated scene objects can pollute perception
- object summaries can confuse decision logic
- duplicate or leftover objects can cause wrong active-object assumptions

## Perception Notes

The default MVP still uses mock perception in the main loop.

However, the project now also has a YOLO-backed perception path that is designed to consume captured Blender images and return:

- detected local parts
- confidence values
- bounding boxes
- normalized part positions

Before live capture can safely become the default perception path, the loop will also need a framing step that makes sure the target object is actually centered and reasonably contained inside the viewport.

Otherwise, the loop may confuse a camera-framing problem with a modeling problem.

Current preferred direction for that step:

- adjust the viewport viewpoint through `execute_blender_code`
- use Blender-side viewport fitting such as `bpy.ops.view3d.view_selected(...)`
- avoid depending on `jump_to_view3d_object_by_name` as the main framing strategy

## Current Stopping Rules

The loop currently stops when:

- the decision engine returns `finish`
- the previous action failed and the rule engine decides to stop
- the maximum iteration limit is reached

## Current Files

- loop orchestration:
  `src/ai_3d_modeling_agent/pipelines/mvp_loop.py`
- action execution:
  `src/ai_3d_modeling_agent/execution/action_executor.py`
- gap report creation:
  `src/ai_3d_modeling_agent/analysis/gap_report_builder.py`

## Multi-Stage Modeling Direction

The repo now also includes a second orchestration path for part-by-part modeling:

1. accept a user request that may include text plus image references
2. ask an LLM-style coordinator to decompose the target into modeling tasks
3. for each task:
   - choose an initial primitive
   - let the Agent build the part through Blender operations
   - capture a screenshot of that part
   - ask the coordinator for structured feedback
   - apply the requested edit action
   - repeat until the coordinator approves the part
   - hide the approved mesh before moving to the next task
4. unhide all approved meshes
5. move and rotate them into their planned assembly positions
6. capture the assembled object and ask for structured assembly feedback
7. apply assembly edits until the coordinator approves
8. capture the final result and run YOLO validation on that image

This path is implemented in:

- `src/ai_3d_modeling_agent/pipelines/runners.py`
- `src/ai_3d_modeling_agent/decision/modeling_coordinator.py`
- `src/ai_3d_modeling_agent/schemas/modeling_plan.py`

## Next Design Direction

The next planned upgrade for the multi-stage path is:

- process screenshots will be passed to the LLM as real multimodal image inputs
- final assembled screenshots will remain YOLO-only validation inputs
- repeated parts such as multiple chair legs will use an instance-aware workflow instead of one-task-one-mesh

See:

- `multimodal_review_and_multiplicity_design.md`
