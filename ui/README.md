# UI Workspace

React + TypeScript + Vite frontend for the Blender 3D modeling GUI.

## Common commands

```bash
npm run dev
npm run dev:mcp-mock
npm run build
npm run test
npm run test:e2e
```

## Playwright MCP browser automation

Use `npm run dev:mcp-mock` when you want Codex + Playwright MCP to exercise the UI without depending on the live bridge or pipeline.

The mock runtime:

- intercepts `/api/*` in the browser
- provides a mock `/ws/activity` socket
- exposes `window.__AI3D_MCP_MOCK__` for driving session, activity, and status changes from browser automation

See [docs/playwright-mcp.md](D:/program/Projects/Blender%203DModel%20Agent/repo/ui/docs/playwright-mcp.md) for the interaction flow and example commands.
