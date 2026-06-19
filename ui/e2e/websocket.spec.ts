import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('WebSocket', () => {
  test('WebSocket connection is established', async ({ page }, testInfo) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByText('activity: live')).toBeVisible()

    const screenshotPath = testInfo.outputPath('01-websocket-connected.png')
    await page.screenshot({ path: screenshotPath })
    await testInfo.attach('websocket-connected', { path: screenshotPath })
  })

  test('snapshot_required refreshes workflow chip from the latest snapshot', async ({ page }, testInfo) => {
    const bridge = await mockBridgeApi(page)
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'running',
      process_status: 'running',
    })
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)
    await expect(page.getByText('workflow: running')).toBeVisible()

    const screenshotPath = testInfo.outputPath('03-workflow-running.png')
    await page.screenshot({ path: screenshotPath })
    await testInfo.attach('workflow-running', { path: screenshotPath })
  })
})
