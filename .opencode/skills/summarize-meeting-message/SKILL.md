# summarize-meeting-message

Condense one multi-expert meeting message for the Conversation Surface.

## Input

You will receive a JSON-like Markdown prompt with:

- `phase`
- `turn_kind`
- `speaker`
- `role`
- `task`
- `message_markdown`
- optional `context_summary`

## Output

Return only a short Traditional Chinese Markdown summary for the user interface.

Required style:

- Start with `結論：`
- Add `重點：` only when one extra detail improves readability.
- Add `下一步：` only when the message implies a concrete next action.
- Add `風險：` only for blocking or important unresolved issues.

Rules:

- Keep the result 1 to 3 lines when possible, 5 lines maximum.
- Do not output JSON.
- Do not mention Agent Orchestrator, routing, Task Tool, delegated agents, prompts, sessions, or internal reasoning.
- Do not change the decision, add new facts, or reinterpret the source message.
- Do not summarize Python-owned todo status as complete unless the source explicitly says so.
- Preserve concrete object/part names from the source when they matter.
