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
  readMessageCount,
  selectSessionFromSidebar,
  waitForActivityTimelineLength,
  waitForWorkflowState,
} from './live-bridge-helpers'

test.describe('Live Bridge Multi-Session Reconnect Smoke', () => {
  test('keeps the current session pinned across reload and recovers a background session on demand', async ({ page }) => {
    test.setTimeout(150000)

    await page.goto('/')
    await page.evaluate(() => {
      localStorage.clear()
    })
    await page.reload()
    await expect(page.getByText(/Current Session|Start with a new session/)).toBeVisible()

    const sessionATask = 'Build a multi session smoke chair'
    const sessionBTask = 'Review a background recovery lamp'
    const taskTextarea = page.getByPlaceholder(
      'Example: Build a wooden chair with a straight backrest and square seat.',
    )

    await createFreshSessionFromUi(page)
    await taskTextarea.fill(sessionATask)
    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await page.getByRole('button', { name: 'Start' }).click()
    await waitForWorkflowState(page, 'running', 20000)
    await waitForActivityTimelineLength(page, 1, 20000)

    const sessionAId = await readCurrentSessionId(page)
    expect(sessionAId).toBeTruthy()
    const sessionAPreReloadTruth = await fetchBackendActivityTruth(page, sessionAId)
    const sessionAPreReloadExpectedLength = buildExpectedActivityTimeline(sessionAPreReloadTruth.snapshot).length

    await createFreshSessionFromUi(page)
    await expect.poll(async () => await readCurrentSessionId(page), { timeout: 20000 }).not.toBe(sessionAId)
    const expandButton = page.getByTitle('Expand input fields')
    if (await expandButton.isVisible().catch(() => false)) {
      await expandButton.click()
    }
    await taskTextarea.fill(sessionBTask)
    const sessionBId = await readCurrentSessionId(page)
    expect(sessionBId).toBeTruthy()
    expect(sessionBId).not.toBe(sessionAId)

    await expect(page.getByRole('heading', { name: sessionBTask })).toBeVisible({ timeout: 10000 })
    await expect(taskTextarea).toHaveValue(sessionBTask)

    const sessionBTruthBeforeReload = await fetchBackendActivityTruth(page, sessionBId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(sessionBTruthBeforeReload.snapshot))
    const sessionBMessageCountBeforeReload = await readMessageCount(page)
    const sessionALatestBody = sessionAPreReloadTruth.activity.at(-1)?.body?.trim()
    if (sessionALatestBody) {
      await expect(page.getByTestId('activity-item-body').filter({ hasText: sessionALatestBody })).toHaveCount(0)
    }

    await page.reload()
    await expect(page.getByText('Current Session')).toBeVisible({ timeout: 20000 })
    await expect.poll(async () => await readCurrentSessionId(page), { timeout: 20000 }).toBe(sessionBId)
    await expect(page.getByRole('heading', { name: sessionBTask })).toBeVisible({ timeout: 20000 })
    await expect(taskTextarea).toHaveValue(sessionBTask, { timeout: 20000 })

    const sessionBTruthAfterReload = await fetchBackendActivityTruth(page, sessionBId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(sessionBTruthAfterReload.snapshot))
    const sessionBMessageCountAfterReload = await readMessageCount(page)
    expect(sessionBMessageCountAfterReload).toBe(sessionBMessageCountBeforeReload)
    if (sessionALatestBody) {
      await expect(page.getByTestId('activity-item-body').filter({ hasText: sessionALatestBody })).toHaveCount(0)
    }

    await openRuntimeLog(page)
    const sessionBRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionBId)
    await expectRuntimePanelToMatch(page, sessionBRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const sessionBInspectorTruth = await fetchBackendInspectorTruth(page, sessionBId)
    expect(sessionBInspectorTruth.progress.status).toBe('idle')
    await expectInspectorPanelToMatch(page, sessionBInspectorTruth)
    await closeTopPanel(page)

    const sessionATruthAfterReload = await fetchBackendActivityTruth(page, sessionAId)
    expect(sessionATruthAfterReload.server_cursor).toBeTruthy()
    const sessionARuntimeTruthAfterReload = await fetchBackendRuntimeTruth(page, sessionAId)

    await selectSessionFromSidebar(page, sessionATask)
    await expect.poll(async () => await readCurrentSessionId(page), { timeout: 20000 }).toBe(sessionAId)
    await expect(page.getByRole('heading', { name: sessionATask })).toBeVisible({ timeout: 20000 })

    const sessionATruthOnReturn = await fetchBackendActivityTruth(page, sessionAId)
    await waitForActivityTimelineLength(page, buildExpectedActivityTimeline(sessionATruthOnReturn.snapshot).length, 30000)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(sessionATruthOnReturn.snapshot))
    const sessionAMessageCountOnReturn = await readMessageCount(page)
    expect(sessionAMessageCountOnReturn).toBeGreaterThanOrEqual(sessionAPreReloadExpectedLength)

    await openRuntimeLog(page)
    await expectRuntimePanelToMatch(page, sessionARuntimeTruthAfterReload)
    await closeTopPanel(page)

    await openInspector(page)
    const sessionAInspectorTruth = await fetchBackendInspectorTruth(page, sessionAId)
    await expectInspectorPanelToMatch(page, sessionAInspectorTruth)
    await closeTopPanel(page)

    await waitForWorkflowState(page, 'completed', 50000)

    const sessionAFinalTruth = await fetchBackendActivityTruth(page, sessionAId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(sessionAFinalTruth.snapshot))
    expect(buildExpectedActivityTimeline(sessionAFinalTruth.snapshot).at(-1)?.body).not.toBe('idle / waiting_for_prompt')

    await openRuntimeLog(page)
    const sessionAFinalRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionAId)
    await expectRuntimePanelToMatch(page, sessionAFinalRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const sessionAFinalInspectorTruth = await fetchBackendInspectorTruth(page, sessionAId)
    await expectInspectorPanelToMatch(page, sessionAFinalInspectorTruth)
    await closeTopPanel(page)
  })
})
