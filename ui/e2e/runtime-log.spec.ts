import { test, expect } from '@playwright/test'
import type { McpToolCallRecord } from '../src/types'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('Runtime Log Panel', () => {
  test('shows runtime metrics, console content, and MCP tool call cards', async ({ page }, testInfo) => {
    const bridge = await mockBridgeApi(page)
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'running',
      process_status: 'running',
      pid: 4242,
      exit_code: null,
    })
    bridge.setConsoleLog(TEST_SESSION_ID, 'sample stdout line\nanother line\n')
    bridge.setMcpToolCalls(TEST_SESSION_ID, [
      {
        timestamp: '2026-06-01T00:00:00Z',
        session_id: TEST_SESSION_ID,
        tool_name: 'create_cube',
        arguments: { size: 2 },
        is_error: false,
        result: { object_name: 'Cube' },
      },
      {
        timestamp: '2026-06-01T00:00:05Z',
        session_id: TEST_SESSION_ID,
        tool_name: 'move_object',
        arguments: { name: 'Cube', location: [0, 1, 2] },
        is_error: true,
        result: { error: 'Object not found' },
      } satisfies McpToolCallRecord,
    ])

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await page.getByRole('button', { name: /Runtime Log/ }).click()

    await expect(page.getByRole('heading', { name: 'Runtime Console' })).toBeVisible()
    await expect(page.getByText('sample stdout line')).toBeVisible()
    await expect(page.getByText('another line')).toBeVisible()
    await expect(page.getByText('4242')).toBeVisible()
    await expect(page.getByText('running')).toHaveCount(3)
    await expect(page.getByText('create_cube')).toBeVisible()
    await expect(page.getByText('move_object')).toBeVisible()
    await expect(page.getByText('"size": 2')).toBeVisible()
    await expect(page.getByText('"name": "Cube"')).toBeVisible()
    await expect(page.getByText('ok')).toBeVisible()
    await expect(page.getByText('error')).toBeVisible()

    const screenshotPath = testInfo.outputPath('runtime-log-content.png')
    await page.screenshot({ path: screenshotPath })
    await testInfo.attach('runtime-log-content', { path: screenshotPath })
  })

  test('shows empty state when no console or tool calls are available', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'idle',
      process_status: 'not_started',
      pid: null,
      exit_code: null,
    })

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await page.getByRole('button', { name: /Runtime Log/ }).click()

    await expect(page.getByText('No runtime stdout/stderr has been captured for this session yet.')).toBeVisible()
    await expect(page.getByText('No executed Blender MCP tool calls have been recorded for this session yet.')).toBeVisible()
    await expect(page.getByText('N/A')).toHaveCount(2)
  })
})
