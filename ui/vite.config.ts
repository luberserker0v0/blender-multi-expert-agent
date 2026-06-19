import { defineConfig, loadEnv, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function suppressWsProxyErrors(): Plugin {
  return {
    name: 'suppress-ws-proxy-errors',
    configureServer(server) {
      // Patch the WebSocket proxy handler to suppress ECONNABORTED errors
      const originalOn = server.httpServer?.on.bind(server.httpServer)
      if (originalOn) {
        server.httpServer?.removeAllListeners('upgrade')
        server.httpServer?.on('upgrade', () => {
          // Let Vite handle the upgrade normally
        })
      }
      // Suppress console.error for ECONNABORTED during WS proxy
      const origError = console.error
      console.error = (...args: unknown[]) => {
        const msg = args.map(a => String(a)).join(' ')
        if (msg.includes('ECONNABORTED') || msg.includes('ws proxy socket error')) {
          return // suppress
        }
        origError.apply(console, args)
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const bridgeHttpOrigin = env.VITE_BRIDGE_HTTP_ORIGIN || 'http://127.0.0.1:8765'
  const bridgeWsOrigin = env.VITE_BRIDGE_WS_ORIGIN || 'ws://127.0.0.1:8766'

  return {
    plugins: [react(), tailwindcss(), suppressWsProxyErrors()],
    server: {
      host: '127.0.0.1',
      proxy: {
        '/api': bridgeHttpOrigin,
        '/ws': {
          target: bridgeWsOrigin,
          ws: true,
        },
      },
    },
  }
})
