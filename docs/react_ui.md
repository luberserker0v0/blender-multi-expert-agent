# React UI

## Purpose

This document describes the TypeScript + React + Tailwind UI workspace for the project.

This is now the primary UI direction for the desktop-style local app experience.

Older `tkinter` prototype notes are archived. The React UI is the active surface.

## Stack

- TypeScript
- React
- Vite
- Tailwind CSS

## Workspace Location

- `ui/`

Important source files:

- `ui/src/App.tsx`
- `ui/src/types.ts`
- `ui/src/data/sampleSession.ts`
- `ui/src/hooks/useLocalStorage.ts`
- `ui/src/components/ErrorBoundary.tsx`

## Start The UI

Start the local bridge from `repo/`:

```powershell
python scripts/run_ui_bridge.py
```

Then start the Vite UI from `repo/ui/`:

```powershell
npm install
npm run dev
```

The Vite dev server is configured to use `127.0.0.1` instead of `::1`.

To build a production bundle:

```powershell
npm run build
```

## Current UI Direction

The current React UI is designed around:

- a left session rail
- a large center conversation and workspace area
- a collapsible settings panel
- lower tabs for progress, history, and captures
- inspector-style history details

## Current Data Model

The UI consumes the existing multi-stage progress schema through a small local bridge.

Current transport model:

- `disk + session runtime files` are the source of truth
- `WebSocket` is the primary real-time push channel for Activity and runtime state
- `HTTP snapshot polling` is the fallback when the socket is disconnected or reconnecting

The bridge currently exposes:

- `GET /api/bootstrap`
- `GET /api/activity/snapshot?session_id=...`
- `GET /api/progress?session_id=...`
- `GET /api/mcp/status`
- `GET /api/mcp/tool-calls?session_id=...`
- `POST /api/session/new`
- `POST /api/session/delete`
- `POST /api/mcp/connect`
- `POST /api/mcp/disconnect`
- `POST /api/settings`
- `POST /api/run/start`
- `POST /api/run/stop`
- `POST /api/run/retry`
- `POST /api/run/retry/stop`

The bridge also serves a WebSocket endpoint:

- `ws://127.0.0.1:8766/ws/activity?session_id=...`

The frontend no longer bootstraps a blank screen from sample task content. Blank sessions remain blank after refresh, and the app normalizes incomplete progress payloads before render.

This keeps the React rewrite aligned with:

- `docs/session_and_progress.md`
- `src/ai_3d_modeling_agent/schemas/session_progress.py`

## Saved Settings

The current React UI persists common settings in browser local storage, including:

- Agent Orchestrator URL
- selected Agent Orchestrator model
- optional Agent Orchestrator debug and timeout options
- Blender MCP toggle
- Blender MCP config JSON
- YOLO validation toggle
- YOLO model path
- session and workspace draft state

The same settings are also saved through the bridge to:

- `data/runtime/gui/saved_settings.json`

Task prompt, reference notes, reference images, and the active session itself are treated as workspace content rather than shared saved settings.

## Current Behavior

The current React UI can now:

- create a new blank session
- delete an existing session through a confirmation modal
- save common environment settings
- start the AO-backed multi-expert workflow through the bridge
- stop the spawned local run
- stream Activity/runtime updates over WebSocket
- fall back to snapshot polling when the socket is unavailable
- reconnect the Activity socket with backoff if the browser loses the live channel while the backend task keeps running
- keep the workspace list timestamp stable while you only browse sessions
- update the workspace list to `just now` when you edit or submit the prompt
- auto-scroll the activity panel to the latest message and provide a `Latest` jump button
- keep the activity stream and workspace content empty for fresh sessions instead of filling sample placeholders
- wrap the app in an error boundary so front-end runtime failures do not collapse into a blank page

## Activity Transport And Recovery

The current Activity design is intentionally resilient to browser refreshes and temporary socket disconnects.

Behavior:

- entering a session first loads a snapshot from disk-backed bridge state
- the UI then opens the Activity WebSocket
- while the socket is connected, the frontend receives pushed snapshots for:
  - progress
  - run status
  - runtime console
  - MCP tool calls
  - pending retry interaction state
- if the socket disconnects, the UI:
  - marks the Activity transport as reconnecting or fallback
  - starts HTTP snapshot polling
  - retries the socket with exponential-style backoff
- when the socket reconnects, the UI immediately refreshes the snapshot again so it catches up with anything the backend wrote while the browser was away

This means:

- a WebSocket disconnect does not imply the modeling task stopped
- the backend may continue running normally
- reopening the frontend later should recover the latest session state from disk

## Pending Interaction And Retry Design

Failure-related user decisions are now treated as session runtime state rather than temporary front-end UI state.

Current behavior:

- when a run fails, the bridge writes a session-scoped pending interaction file
- the React UI receives that state through snapshot/WebSocket payloads
- Activity renders a retry decision card inside the conversation surface
- the user can choose:
  - `Retry 1`
  - `Retry 3`
  - `Do not retry`
- if the bridge is already auto-retrying, Activity also shows an `auto retrying` status card

The retry card currently includes:

- the failure reason
- the current attempt index
- the next attempt index that the retry will start from
- remaining auto-retry budget when applicable

Current runtime storage direction:

- retry and other future human-in-the-loop decisions are persisted per session under:
  - `data/runtime/session_data/<session-id>/pending_interaction.json`

This is meant to support future interactive checkpoints beyond retry decisions.

## Session Runtime Layout

The React bridge now assumes session-scoped runtime storage under:

- `data/runtime/session_data/<session-id>/`

Important files in that directory may include:

- `progress.json`
- `console.log`
- `mcp_tool_calls.jsonl`
- `captures/`
- `pending_interaction.json`

Deleting a session is expected to remove the full session runtime directory, not just the visible session record.

## Prompt Semantics

The prompt area separates two kinds of user input:

- `Task Prompt`: the main object or modeling goal to build
- `Reference Notes`: secondary constraints such as style, material, silhouette, proportion, or other refinement guidance

The UI shows small hover hints next to these labels so the explanation stays available without taking over the layout.

## Composer Collapse

The Composer panel (Task Prompt, Reference Notes, References) can be collapsed to give the Conversation Surface more vertical room during and after a run.

Current behavior:

- the Composer panel is **expanded by default**, showing the three-column input grid (Task Prompt / Reference Notes / References)
- clicking **Start** automatically collapses the input grid — the conversation surface expands to fill the freed space
- a toggle button in the header row switches between expanded (`▲ Collapse`) and collapsed (`▼ Expand Input`) states
- when collapsed, the Composer still shows:
  - session title and status badges (stage, workflow, activity, AO, MCP)
  - all action buttons (Start, Stop, Verify AO, Inspector, Runtime Log, Open Panel)
- the collapse is purely a front-end layout state — it does not affect workspace content, the bridge, or the modeling backend
- expanding the Composer again restores the full input grid with all previously entered content intact

Design rationale: once a task has been submitted, the task prompt, reference notes, and references serve as reference context rather than active editing fields. Collapsing them reclaims approximately 200px of vertical space for the activity stream.

## YOLO Controls

The current YOLO-related behavior is:

- `YOLO Model Path` accepts a manually typed or pasted absolute path
- the browser `Browse...` button is still limited by browser sandbox rules and does not expose a true native desktop path the same way a local desktop app would
- `YOLO Viewpoints` are treated as workflow-driven output rather than something the user decides manually in the UI

## Blender MCP Panel

The settings panel now includes an editable `Blender MCP Config` area where the user can paste or edit `mcp.json`-style content.

Current behavior:

- if `Use Blender MCP` is enabled, the frontend asks the bridge to parse the config and initialize the MCP client
- the UI shows MCP connection state as `idle`, `connecting`, `connected`, or `failed`
- the UI shows the current server message and server name when available
- the Blender MCP section can be expanded to inspect the available tool list returned by the MCP server
- the same section also shows a runtime log of executed Blender MCP tool calls for the active session

Runtime tool-call notes:

- executed tool calls are written under `data/runtime/mcp_logs/<session-id>.jsonl`
- the React UI currently focuses on the executed call history and arguments summary
- this is a runtime log of real MCP client activity, not just a static tool catalog

## History And Inspection

The lower history area is meant to answer two different questions:

- `part rounds`: how a single part was iteratively refined
- `assembly rounds`: how the finished parts were positioned, scaled, rotated, and aligned together

Selecting a round updates the inspector-style detail pane with grouped sections such as:

- round summary
- Blender context
- requested action
- requested action parameters

## Current Limitation

- the bridge is local-only and intended for desktop experimentation
- browser file pickers only expose selected file names, not full native desktop paths
- capture cards currently show paths and workflow state rather than rendering runtime images directly
- the MCP runtime log is currently more detailed than the image preview layer
- if the bridge API changes, restart `python scripts/run_ui_bridge.py` before testing the updated frontend
- the WebSocket server is currently a small custom local implementation rather than a larger framework-backed realtime stack

## Playwright E2E Levels

The UI has multiple e2e levels. They should not be treated as equivalent.

### Mock Bridge E2E

Command:

```powershell
npm run test:e2e
```

This starts the local bridge and Vite UI with mock setup/teardown. It tests
browser-visible UI flows against mock runtime/session state:

- session creation, switching, delete, and batch delete
- settings save/load and AO readiness UI
- composer behavior, status chips, start/stop buttons
- Conversation Surface activity rendering and expansion
- retry cards, Runtime Log, Inspector, and WebSocket resync
- responsive layout checks

This level does not require real AO, a real model, Blender, or Blender MCP.

### Live Bridge Smoke E2E

Command:

```powershell
npm run test:e2e:live-bridge
```

This starts a real `scripts/run_ui_bridge.py` process in smoke mode and drives
the React UI through Playwright. It verifies that UI state stays aligned with a
real bridge process, including reload/reconnect, retry, runtime log, activity
ordering, and multi-session recovery.

This level still does not require real AO or Blender. It is intended as a local
smoke test and is not part of GitHub CI by default.

### Full Live AO / Blender E2E

This level is manual/local for now. It requires:

- Agent Orchestrator running
- selected model/provider working
- Blender running with MCP available
- React UI and bridge started through `make run-dev`

Use this level to verify that a browser-started task actually reaches AO,
produces artifacts, executes Blender MCP operations, and validates the scene.
Because it depends on local services and a graphical Blender session, it is not
safe for normal GitHub CI.
