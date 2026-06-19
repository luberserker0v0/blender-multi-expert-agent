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
  readCurrentSessionId,
  readRenderedActivityTimeline,
  waitForActivityTimelineLength,
  waitForWorkflowState,
} from './live-bridge-helpers'

test.describe('Live Bridge Reconnect Smoke', () => {
  test('reloads during a real bridge-backed run and rehydrates the same session without drift', async ({ page }) => {
    test.setTimeout(120000)

    await page.goto('/')
    await page.evaluate(() => {
      localStorage.clear()
    })
    await page.reload()
    await expect(page.getByText(/Current Session|Start with a new session/)).toBeVisible()

    await createFreshSessionFromUi(page)

    const taskPrompt = 'Build a reconnect smoke wooden chair'
    const taskTextarea = page.getByPlaceholder(
      'Example: Build a wooden chair with a straight backrest and square seat.',
    )
    await taskTextarea.fill(taskPrompt)

    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Start' })).toBeEnabled()
    await page.getByRole('button', { name: 'Start' }).click()

    await waitForWorkflowState(page, 'running', 20000)
    await waitForActivityTimelineLength(page, 1, 20000)

    const sessionId = await readCurrentSessionId(page)
    expect(sessionId).toBeTruthy()

    const preReloadRenderedTimeline = await readRenderedActivityTimeline(page)
    const preReloadActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(preReloadActivityTruth.snapshot))

    await openRuntimeLog(page)
    const preReloadRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, preReloadRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const preReloadInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, preReloadInspectorTruth)
    await closeTopPanel(page)

    const preReloadCursor = preReloadActivityTruth.server_cursor

    await page.reload()
    await expect(page.getByText('Current Session')).toBeVisible({ timeout: 20000 })
    await expect.poll(async () => await readCurrentSessionId(page), { timeout: 20000 }).toBe(sessionId)
    await expect(taskTextarea).toHaveValue(taskPrompt, { timeout: 20000 })
    await waitForActivityTimelineLength(page, preReloadRenderedTimeline.length, 30000)

    const postReloadActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    const postReloadExpectedTimeline = buildExpectedActivityTimeline(postReloadActivityTruth.snapshot)
    await expectActivityTimelineToMatch(page, postReloadExpectedTimeline)

    const postReloadRenderedTimeline = await readRenderedActivityTimeline(page)
    expect(postReloadRenderedTimeline.length).toBeGreaterThanOrEqual(preReloadRenderedTimeline.length)
    expect(postReloadActivityTruth.activity.length).toBeGreaterThanOrEqual(preReloadActivityTruth.activity.length)
    expect(postReloadActivityTruth.server_cursor).toBeTruthy()

    const truthAdvanced =
      postReloadActivityTruth.activity.length > preReloadActivityTruth.activity.length ||
      postReloadExpectedTimeline.length > preReloadRenderedTimeline.length
    if (!truthAdvanced) {
      expect(postReloadActivityTruth.server_cursor).toBe(preReloadCursor)
    }

    await openRuntimeLog(page)
    const postReloadRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, postReloadRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const postReloadInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, postReloadInspectorTruth)
    await closeTopPanel(page)

    await waitForWorkflowState(page, 'completed', 50000)

    const completedActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(completedActivityTruth.snapshot))
    expect(buildExpectedActivityTimeline(completedActivityTruth.snapshot).at(-1)?.body).not.toBe(
      'idle / waiting_for_prompt',
    )

    await openRuntimeLog(page)
    const completedRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, completedRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const completedInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, completedInspectorTruth)
    await closeTopPanel(page)
  })
})
