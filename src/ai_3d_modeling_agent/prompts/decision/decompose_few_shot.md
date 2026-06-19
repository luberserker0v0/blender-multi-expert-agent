## User
Input: "build an apple"

## Assistant
```json
{"part_families":[{"name":"apple_body","description":"main rounded body of the apple","instance_count":1,"parent_name":null,"symmetry_group":"NONE"},{"name":"stem","description":"small stem on top of the apple","instance_count":1,"parent_name":"apple_body","symmetry_group":"NONE"},{"name":"leaf","description":"leaf attached near the stem","instance_count":2,"parent_name":"apple_body","symmetry_group":"LEFT_RIGHT_X"}]}
```

---

## User
Input: "build a wooden chair with four legs"

## Assistant
```json
{"part_families":[{"name":"seat","description":"flat horizontal surface to sit on","instance_count":1,"parent_name":null,"symmetry_group":"NONE"},{"name":"leg","description":"straight vertical support column","instance_count":4,"parent_name":"seat","symmetry_group":"QUADRANT_Z"},{"name":"backrest","description":"curved vertical back support","instance_count":1,"parent_name":"seat","symmetry_group":"NONE"}]}
```
