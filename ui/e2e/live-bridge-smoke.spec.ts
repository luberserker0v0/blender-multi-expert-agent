import { expect, test } from '@playwright/test'
import {
  buildExpectedActivityTimeline,
  closeTopPanel,
  createFreshSessionFromUi,
  expectActivityTimelineToMatch,
  expectInspectorPanelToMatch,
  expectRuntimePanelToMatch,
  fetchBackendActivityTruth,
  fetchBackendInspectorTruth,
  fetchBackendRuntimeTruth,
  openInspector,
  openRuntimeLog,
  waitForActivityTimelineLength,
  waitForWorkflowState,
} from './live-bridge-helpers'

test.describe('Live Bridge Smoke', () => {
  test('starts a real bridge-backed run and updates activity, runtime log, and inspector', async ({ page }) => {
    test.setTimeout(90000)
    const consoleErrors: string[] = []

    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text())
      }
    })
    page.on('pageerror', (err) => {
      consoleErrors.push(err.message)
    })

    await page.addInitScript(() => {
      localStorage.clear()
    })

    await page.goto('/')
    await expect(page.getByText(/Current Session|Start with a new session/)).toBeVisible()

    await createFreshSessionFromUi(page)
    await expect(page.getByText('Current Session')).toBeVisible()
    await expect(page.getByText('Conversation Surface')).toBeVisible()

    const taskTextarea = page.getByPlaceholder(
      'Example: Build a wooden chair with a straight backrest and square seat.',
    )
    await taskTextarea.fill('Build a simple wooden chair')

    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Start' })).toBeEnabled()
    await page.getByRole('button', { name: 'Start' }).click()

    const initialMessageCountText = await page.getByText(/\d+ messages/).textContent()
    const initialMessageCount = Number(initialMessageCountText?.match(/\d+/)?.[0] ?? '0')
    await waitForWorkflowState(page, 'running', 20000)
    await waitForActivityTimelineLength(page, 1, 20000)
    const runningMessageCountText = await page.getByText(/\d+ messages/).textContent()
    const runningMessageCount = Number(runningMessageCountText?.match(/\d+/)?.[0] ?? '0')
    expect(runningMessageCount).toBeGreaterThanOrEqual(initialMessageCount)
    await expect(
      page.getByText('Modeling completed: approved 2 parts - Seat, Legs. Final assembly and validation finished.'),
    ).not.toBeVisible()

    const activeSessionId = await page.evaluate(() => {
      const raw = window.localStorage.getItem('ai3d-react-ui-store')
      if (!raw) return ''
      const parsed = JSON.parse(raw) as { state?: { currentSessionId?: string } }
      return parsed.state?.currentSessionId ?? ''
    })
    expect(activeSessionId).toBeTruthy()

    const runningTruth = await fetchBackendActivityTruth(page, activeSessionId)
    const runningExpected = buildExpectedActivityTimeline(runningTruth.snapshot)
    await expectActivityTimelineToMatch(page, runningExpected)

    await openRuntimeLog(page)
    const runningRuntimeTruth = await fetchBackendRuntimeTruth(page, activeSessionId)
    await expectRuntimePanelToMatch(page, runningRuntimeTruth)
    await expect(page.getByText('Mock multi-expert run started')).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('Task: Build a simple wooden chair')).toBeVisible({ timeout: 20000 })
    await expect(page.getByText('Workflow', { exact: true })).toBeVisible()
    await expect(page.getByText('Process', { exact: true })).toBeVisible()
    await expect(page.getByText('MCP State', { exact: true })).toBeVisible()
    await closeTopPanel(page)

    await openInspector(page)
    const runningInspectorTruth = await fetchBackendInspectorTruth(page, activeSessionId)
    await expectInspectorPanelToMatch(page, runningInspectorTruth)
    await closeTopPanel(page)

    await waitForWorkflowState(page, 'completed', 40000)
    await expect(page.getByText('Modeling completed: approved 2 parts - Seat, Legs. Final assembly and validation finished.')).toBeVisible({
      timeout: 20000,
    })
    const completedMessageCountText = await page.getByText(/\d+ messages/).textContent()
    const completedMessageCount = Number(completedMessageCountText?.match(/\d+/)?.[0] ?? '0')
    expect(completedMessageCount).toBeGreaterThanOrEqual(runningMessageCount)

    const completedTruth = await fetchBackendActivityTruth(page, activeSessionId)
    const completedExpected = buildExpectedActivityTimeline(completedTruth.snapshot)
    await expectActivityTimelineToMatch(page, completedExpected)
    expect(completedExpected.at(-1)?.body).not.toBe('idle / waiting_for_prompt')

    const completedRuntimeTruth = await fetchBackendRuntimeTruth(page, activeSessionId)
    await expectRuntimePanelToMatch(page, completedRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const completedInspectorTruth = await fetchBackendInspectorTruth(page, activeSessionId)
    await expectInspectorPanelToMatch(page, completedInspectorTruth)
    await closeTopPanel(page)
    await expect(page.getByText(/messages/)).toBeVisible()

    expect(consoleErrors).toEqual([])
  })
})
