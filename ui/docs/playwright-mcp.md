# Playwright MCP Browser Automation

This UI supports a mock-first browser automation mode for Playwright MCP.

## Start the UI

From `repo/ui`:

```bash
npm run dev:mcp-mock
```

This mode enables a browser-side mock runtime instead of relying on the live bridge.

## What gets mocked

- `GET /api/bootstrap`
- `GET /api/session/state`
- `GET /api/activity/snapshot`
- session create/delete/current/workspace APIs
- run start/stop/retry APIs
- MCP status/connect/tool-call APIs
- diagnostics and LLM endpoint verification
- `/ws/activity` via a mock `WebSocket`

## Browser automation loop

Recommended MCP tool sequence:

1. `browser_navigate` to `http://127.0.0.1:5173`
2. `browser_snapshot` to inspect the current accessibility tree
3. `browser_click` / `browser_type` to drive the UI
4. `browser_verify_text_visible` or `browser_verify_element_visible` to assert state
5. `browser_take_screenshot` when you want a saved artifact

## Mock control surface

The mock runtime exposes `window.__AI3D_MCP_MOCK__` for state control from browser automation.

Available methods:

- `reset()`
- `getState()`
- `patchSession(sessionId, patch)`
- `pushMeetingEvent(sessionId, event)`
- `pushActivityItems(sessionId, items)`
- `setMcpStatus(status)`

## Example browser_evaluate calls

Read current mock state:

```js
() => window.__AI3D_MCP_MOCK__?.getState()
```

Push a session snapshot-style state update and force UI resync:

```js
() => {
  window.__AI3D_MCP_MOCK__?.patchSession('mcp-browser-session', {
    progress: {
      workflow_type: 'multi_stage_modeling',
      status: 'running',
      task: 'Build a wooden chair',
      stage: 'design',
      stage_status: 'in_progress',
      active_task_id: '',
      completed_task_ids: [],
      part_tasks: [],
      assembly: {
        status: 'pending',
        current_round: 0,
        approved: false,
        all_parts_visible: false,
        initial_placement_applied: false,
        rounds: [],
      },
      final_validation: {
        status: 'pending',
        capture_path: '',
        viewpoint: 'front',
        detected_parts: [],
        missing_critical_parts: [],
        quantitative_metrics: [],
      },
      stop_reason: '',
    },
    run_status: {
      workflow_status: 'running',
      process_status: 'running',
    },
  })
}
```

Inject a meeting event:

```js
() => {
  window.__AI3D_MCP_MOCK__?.pushMeetingEvent('mcp-browser-session', {
    event_id: 'meeting:1',
    phase: 'design',
    kind: 'phase_start',
    message: 'Design review started',
  })
}
```

Append activity items directly:

```js
() => {
  window.__AI3D_MCP_MOCK__?.pushActivityItems('mcp-browser-session', [
    {
      id: crypto.randomUUID(),
      kind: 'status',
      title: 'Status',
      body: 'workflow / running',
      timestamp: new Date().toISOString(),
    },
  ])
}
```

## Suggested manual scenarios

- Verify initial load: `Current Session`, `Conversation Surface`, stage/workflow/activity chips
- Open `Settings` and confirm `Environment Defaults`
- Create a new session from the sidebar
- Enter a task prompt and confirm `Start` becomes enabled
- Click `Start`, then patch mock progress to verify stage/workflow chip changes
- Open runtime or inspector panels after state changes
