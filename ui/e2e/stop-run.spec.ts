import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('Stop Run', () => {
  test('stop is enabled for a running workflow and appends a system activity', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'running',
      process_status: 'running',
    })
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)

    const stopButton = page.getByRole('button', { name: 'Stop' })
    await expect(stopButton).toBeEnabled()
    await stopButton.click()

    await expect(page.getByText(`Stop requested for session ${TEST_SESSION_ID}.`)).toBeVisible()
  })
})
