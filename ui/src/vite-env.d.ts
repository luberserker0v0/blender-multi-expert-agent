/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ENABLE_MCP_BROWSER_MOCKS?: string
  readonly VITE_ACTIVITY_SOCKET_URL?: string
  readonly VITE_BRIDGE_HTTP_ORIGIN?: string
  readonly VITE_BRIDGE_WS_ORIGIN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
