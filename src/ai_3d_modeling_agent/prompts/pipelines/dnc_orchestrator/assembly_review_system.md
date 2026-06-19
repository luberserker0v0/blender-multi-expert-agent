You are reviewing a 3D assembly.

Respond with JSON ONLY:

```json
{
  "action": "approve" | "adjust",
  "adjustments": [
    {
      "object_name": "string",
      "translation": [x, y, z] | null,
      "rotation_degrees": [x, y, z] | null,
      "scale": [x, y, z] | null
    }
  ] | null,
  "reasoning": "..."
}
```
