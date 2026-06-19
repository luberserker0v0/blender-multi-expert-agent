# React UI Workspace

React + TypeScript + Vite frontend for the Blender multi-expert modeling GUI.
The UI talks to the local Python bridge, which in turn coordinates Agent
Orchestrator readiness, Blender MCP readiness, run/session state, and activity
streaming.

## Common Commands

```powershell
npm run dev
npm run dev:mcp-mock
npm run build
npm run test
npm run ci
npm run test:e2e
npm run test:e2e:live-bridge
```

## Runtime Shape

- Settings expose Agent Orchestrator URL/model/debug options, not legacy LLM endpoint settings.
- Composer readiness is based on AO readiness and Blender MCP status.
- Conversation Surface displays short meeting summaries by default and keeps the full AO response in expandable detail.
- The UI keeps the `MultiStageProgressSnapshot` wire name for compatibility; `multi_expert_mode` is always `true`.

## Playwright MCP Browser Automation

Use `npm run dev:mcp-mock` when you want Codex + Playwright MCP to exercise the
UI without depending on the live bridge or pipeline.

The mock runtime:

- intercepts `/api/*` in the browser
- provides a mock `/ws/activity` socket
- exposes `window.__AI3D_MCP_MOCK__` for driving session, activity, and status changes from browser automation

See [docs/playwright-mcp.md](docs/playwright-mcp.md) and
[`../.opencode/skills/playwright-mcp-e2e/SKILL.md`](../.opencode/skills/playwright-mcp-e2e/SKILL.md)
for the interaction flow and example commands.
