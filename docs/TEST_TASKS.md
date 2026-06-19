# Test Task Corpus

Tasks used for regression testing after each fix.
Each task has a **gold standard** defining what "correct" looks like.

---

## T1: "build an apple"

### Gold Standard

```yaml
task: "build an apple"

structure:
  - part: apple_body
    primitive: uv_sphere
    instance_count: 1
    parent: null
    symmetry: NONE
    attachment: top_center [0, 0, +0.09]
    # children (stem, leaves) connect at top_center

  - part: stem
    primitive: cylinder
    instance_count: 1
    parent: apple_body
    symmetry: NONE
    attachment: bottom_center [0, 0, -0.025]
    # bottom faces the apple's top

  - part: leaf
    primitive: plane
    instance_count: 2
    parent: apple_body
    symmetry: LEFT_RIGHT_X
    attachment: center_base [0, 0, 0]
    # base faces the apple's top

spatial:
  apple_body:
    position: [0, 0, 0]
    scale: [0.075, 0.06, 0.09]       # bbox/2 normalization
    top_surface_z: 0.09               # height/2

  stem:
    position_z_expected: 0.1025       # 0.09 + 0.025/2 (top of apple + half stem height)
    scale: [0.01, 0.01, 0.025]       # bbox/2

  leaf_left:                           # instance 1
    position_x_expected: -0.03
    position_z_expected: ~0.09

  leaf_right:                          # instance 2
    position_x_expected: +0.03
    position_z_expected: ~0.09

rules:
  - stem bottom must NOT penetrate apple (stem.z - stem.h/2 >= apple.top_surface_z)
  - leaf[1].x == -leaf[2].x           # symmetric across X
  - all parts: z >= 0                  # nothing below ground
```

### Validation Checklist

```
[STRUCTURE]   1 body + 1 stem + 2 leaves?            __/__
[STRUCTURE]   All primitives correct?                 __/__
[POSITION]    Stem on top of body?                    __/__
[POSITION]   Leaves left+right of stem?               __/__
[SCALE]       Body largest, stem thin, leaf flat?     __/__
[SPATIAL]     Symmetric leaf positions?                __/__
[SPATIAL]     No parts intersecting ground (z<0)?     __/__
[APPEARANCE]  Overall recognizable as apple?          __/__
```

---

## T2: "build a wooden chair with four legs, a seat, a backrest, and cross stretchers"

(TBD — add when you first run this task)

## T3: (add more as you encounter new tasks)

### Template for adding a new task

```yaml
task: "<task description>"
structure:
  - part: <name>
    primitive: <cube/uv_sphere/cylinder/plane>
    instance_count: <N>
    parent: <parent name or null>
    symmetry: <group>
    attachment: <name> [<x>, <y>, <z>]
spatial:
  <part>: {position: [x,y,z], scale: [sx,sy,sz]}
rules:
  - <specific rule to check>
```
