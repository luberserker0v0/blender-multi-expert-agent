import { defineConfig, devices } from '@playwright/test'

const uiPort = process.env.AI3D_E2E_UI_PORT || '6173'
const bridgeHttpPort = process.env.AI3D_E2E_BRIDGE_HTTP_PORT || '8875'
const bridgeWsPort = process.env.AI3D_E2E_BRIDGE_WS_PORT || '8876'
const uiBaseUrl = `http://127.0.0.1:${uiPort}`
const bridgeHttpOrigin = `http://127.0.0.1:${bridgeHttpPort}`
const bridgeWsOrigin = `ws://127.0.0.1:${bridgeWsPort}`

export default defineConfig({
  testDir: './e2e',
  testMatch: /live-bridge-.*\.spec\.ts/,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  globalSetup: './e2e/global-setup.live-bridge.ts',
  globalTeardown: './e2e/global-teardown.live-bridge.ts',
  use: {
    baseURL: uiBaseUrl,
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: `powershell -NoProfile -Command "$env:AI3D_E2E_LIVE_BRIDGE_SMOKE='1'; $env:AI3D_UI_BRIDGE_HTTP_PORT='${bridgeHttpPort}'; $env:AI3D_UI_BRIDGE_WS_PORT='${bridgeWsPort}'; & 'C:/Users/berserker/anaconda3/python.exe' 'scripts/run_ui_bridge.py'"`,
      cwd: '../',
      url: `${bridgeHttpOrigin}/api/bootstrap`,
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: `powershell -NoProfile -Command "$env:VITE_BRIDGE_HTTP_ORIGIN='${bridgeHttpOrigin}'; $env:VITE_BRIDGE_WS_ORIGIN='${bridgeWsOrigin}'; $env:VITE_ACTIVITY_SOCKET_URL='${bridgeWsOrigin}/ws/activity'; npm run dev -- --host 127.0.0.1 --port ${uiPort}"`,
      cwd: './',
      url: uiBaseUrl,
      reuseExistingServer: false,
      timeout: 30000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
