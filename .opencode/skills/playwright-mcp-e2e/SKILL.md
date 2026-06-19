---
name: playwright-mcp-e2e
description: Use when manually testing the React frontend with Playwright MCP browser tools. Covers AO readiness, UI interactions, mock/live bridge behavior, screenshots, console checks, and selector patterns. Do not use for backend-only testing.
---

# Playwright MCP E2E Testing

Use this skill when manually validating the React UI in a browser. Automated CI uses `ui/e2e/*.spec.ts`; this skill is the human/agent operating guide for exploratory UI checks.

## Standard Dev Environment

```powershell
conda activate ai3d-stage2
make run-dev
```

Expected local services:

- Frontend: `http://localhost:5173`
- GUI bridge REST: `http://127.0.0.1:8765`
- GUI bridge WebSocket: `ws://127.0.0.1:8766`
- Agent Orchestrator: user-provided URL in Settings

## Current AO UI Contract

- Composer readiness uses `AO: ready/not verified` plus `MCP: connected/idle/failed`.
- Settings shows Agent Orchestrator URL, model selector, keep conversation toggle, and timeout.
- The project owns AO conversation IDs; users should not type one manually.
- Start should require AO readiness and Blender MCP readiness for real runs.
- Conversation Surface shows a short summary by default and the full AO response when expanded.
- `kind: "llm"` may remain as wire compatibility, but visible copy should say AO/agent turn rather than LLM endpoint.

## Manual Browser Workflow

1. Navigate to `http://localhost:5173`.
2. Check browser console for runtime errors.
3. Open Settings and verify AO URL/model controls.
4. Verify AO readiness.
5. Confirm Composer chips show AO and MCP state.
6. Create a new session.
7. Enter a simple task such as `Build a simple red cube`.
8. Start the run and watch Design, Spec, Plan, Build, Assemble, and Validate activity.
9. Expand one Conversation Surface item and confirm the short summary and full content differ.
10. Open Runtime Log and Inspector.
11. Test session batch delete mode and the confirmation modal.

## Stable Selector Preference

Prefer accessible selectors:

- `getByRole("button", { name: "Settings" })`
- `getByRole("button", { name: "Start" })`
- `getByRole("button", { name: "Runtime Log" })`
- `getByRole("button", { name: "Inspector" })`
- `getByText("AO: ready")`
- `getByText("MCP: connected")`

If text is duplicated, scope to the visible panel or use existing `data-testid` selectors when available.

## Evidence To Capture

- Screenshot after first page load.
- Screenshot of Settings with AO model list.
- Screenshot of Conversation Surface during a run.
- Screenshot of expanded full AO response.
- Screenshot of Runtime Log when a failure occurs.
- Console log summary for any runtime error.

Do not commit generated screenshots or Playwright reports; they are ignored by git.
