# Archived Reference

This document is historical. It may describe removed runtime paths and must not
be used as active implementation guidance.

# Task Object Table

## Purpose

The task object table defines which scene objects belong to the current modeling task.

This prevents unrelated objects from interfering with modeling, perception, and decision logic.

## Current Schema

Each object entry currently stores:

- `name`
- `role`
- `allowed_count`
- `creation_policy`

The current schema is defined in:

- `src/ai_3d_modeling_agent/schemas/task_objects.py`

## Current MVP Example

For the apple MVP, the current table contains one object:

```json
[
  {
    "name": "apple_body",
    "role": "target_body",
    "allowed_count": 1,
    "creation_policy": "create_if_missing"
  }
]
```

## Current Cleanup Rule

Before each loop iteration:

- read all scene object names
- compare them with the task object table
- delete any object not present in the table

## Why This Exists

- old scene leftovers can distort object summaries
- duplicate objects can break active-object assumptions
- perception should focus only on task-relevant geometry

## Planned Extension

This table is expected to grow into a more expressive task state model with:

- object grouping
- parent / child expectations
- object multiplicity
- protected helper objects
- material or topology constraints

The current codebase now includes the first extension fields toward that direction:

- `parent_name`
- `task_id`
- `default_hidden`

These support staged workflows where one part is refined at a time, approved parts are hidden, and all parts are later re-shown for assembly review.
