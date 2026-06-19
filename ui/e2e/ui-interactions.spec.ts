import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi } from './helpers'

test.describe('UI Interactions', () => {
  test.beforeEach(async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()
  })

  test('composer collapse and expand', async ({ page }) => {
    await page.goto('/')
    const taskPrompt = page.getByPlaceholder('Example: Build a wooden chair with a straight backrest and square seat.')
    await expect(taskPrompt).toBeVisible()

    await page.getByRole('button', { name: /Collapse/i }).click()
    await expect(taskPrompt).not.toBeVisible()

    await page.getByRole('button', { name: /Expand Input/i }).click()
    await expect(taskPrompt).toBeVisible()
  })

  test('settings panel toggles and shows current fields', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByRole('button', { name: 'Settings' }).click()

    await expect(page.getByRole('heading', { name: 'Environment Defaults' })).toBeVisible()
    await expect(page.getByText('Agent Orchestrator URL')).toBeVisible()
    await expect(page.getByText('Agent Orchestrator Model')).toBeVisible()
    await expect(page.getByText(/AO Conversation\s+ID/)).not.toBeVisible()
    await expect(page.getByRole('combobox')).toContainText('openai/gpt-5')
    await expect(page.getByText('Part Rounds')).toBeVisible()
    await expect(page.getByText('Assembly Rounds')).toBeVisible()
    await expect(page.getByText('Use YOLO Validation')).toBeVisible()
    await expect(page.getByText('Blender MCP Status')).toBeVisible()
    await expect(page.getByText('Save Settings')).toBeVisible()
  })

  test('settings save appends system message', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByRole('button', { name: 'Settings' }).click()
    await page.getByText('Save Settings').click()
    await expect(page.getByText('Saved environment settings for the next launch.')).toBeVisible()
  })

  test('settings controls update AO model, debug options, timeout, and info tooltip', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByRole('button', { name: 'Settings' }).click()

    await expect(page.getByRole('combobox')).toContainText('openai/gpt-5')
    await page.getByRole('combobox').selectOption('anthropic/claude-3-5-sonnet')

    await page.getByLabel('AO Timeout').fill('45')
    await page.getByRole('button', { name: /Keep AO Conversation/ }).click()

    const modelInfo = page.getByLabel(
      'Models are loaded from Agent Orchestrator. Select one for new runs; conversation IDs are created and managed by this project.',
    )
    await modelInfo.hover()
    await expect(
      page.getByText('Models are loaded from Agent Orchestrator. Select one for new runs; conversation IDs are created and managed by this project.'),
    ).toBeVisible()

    const settingsRequestPromise = page.waitForRequest((request) =>
      request.url().endsWith('/api/settings') && request.method() === 'POST',
    )
    await page.getByText('Save Settings').click()
    await expect(page.getByText('Saved environment settings for the next launch.')).toBeVisible()

    const payload = settingsRequestPromise.then((request) => request.postDataJSON() as Record<string, unknown>)
    await expect(payload).resolves.toMatchObject({
      agent_orchestrator_model: 'anthropic/claude-3-5-sonnet',
      agent_orchestrator_destroy_on_finish: false,
      agent_orchestrator_timeout_seconds: 45,
    })
  })

  test('composer status chips reflect current ready state', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('stage: idle')).toBeVisible()
    await expect(page.getByText('workflow: idle')).toBeVisible()
    await expect(page.getByText('activity: live')).toBeVisible()
    await expect(page.getByText('sync: live').first()).toBeVisible()
    await expect(page.getByText('AO: ready')).toBeVisible()
    await expect(page.getByText('MCP: connected')).toBeVisible()
  })

  test('delete session modal appears and cancels', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').getByRole('button', { name: 'Delete', exact: true }).first().click()
    await expect(page.getByText('Delete Session')).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByText('Delete Session')).not.toBeVisible()
  })

  test('inspector opens with idle skeleton state', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Inspector' }).click()
    await expect(page.getByRole('heading', { name: 'Progress Inspector' })).toBeVisible()
    await expect(page.getByText('Latest Capture')).not.toBeVisible()
  })

  test('runtime log opens', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Runtime Log' }).click()
    await expect(page.getByRole('heading', { name: 'Runtime Console' })).toBeVisible()
  })

  test('start button becomes enabled after auto verification', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('AO: ready')).toBeVisible()
    await expect(page.getByText('MCP: connected')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start' })).toBeEnabled()
  })

  test('task and reference textareas accept input', async ({ page }) => {
    await page.goto('/')
    const taskTextarea = page.getByPlaceholder('Example: Build a wooden chair with a straight backrest and square seat.')
    const referenceTextarea = page.getByPlaceholder('Example: light wood finish, minimal bevels, clean modern silhouette.')

    await taskTextarea.fill('Build a simple wooden table')
    await referenceTextarea.fill('Dark walnut finish with carved legs')

    await expect(taskTextarea).toHaveValue('Build a simple wooden table')
    await expect(referenceTextarea).toHaveValue('Dark walnut finish with carved legs')
  })

  test('sidebar shows session items and actions', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('aside').getByText('E2E Test Session')).toBeVisible()
    await expect(page.locator('aside').getByRole('button', { name: 'Settings' })).toBeVisible()
    await expect(page.locator('aside').getByRole('button', { name: 'New Session' })).toBeVisible()
  })
})
